from datetime import date, timedelta

from .database import PlanStore
from .models import Meal, PlanMeta, Recipe, Settings, SlotConfig, UserRecipe, WeekPlan
from .prompt_builder import MEAL_SLOTS
from .recipes import PlannerAI


class PlanService:
    def __init__(self, store: PlanStore, planner: PlannerAI) -> None:
        self._store = store
        self._planner = planner

    # ── Settings ──────────────────────────────────────────────────

    async def get_settings(self) -> Settings:
        return Settings(**(await self._store.get_settings() or {}))

    async def update_settings(self, settings: Settings) -> Settings:
        await self._store.save_settings(settings)
        return settings

    # ── Plans ─────────────────────────────────────────────────────

    async def list_plans(self) -> list[PlanMeta]:
        return [PlanMeta(**m) for m in await self._store.get_all_plan_metas()]

    async def get_plan(self, plan_id: int | None = None) -> WeekPlan | None:
        if plan_id is not None:
            return await self._store.get_plan_by_id(plan_id)
        return await self._store.get_current_plan()

    async def confirm_plan(self, plan_id: int) -> None:
        await self._store.confirm_plan(plan_id)

    async def delete_plan(self, plan_id: int) -> bool:
        return await self._store.delete_plan_by_id(plan_id)

    async def add_recipe_to_plan(self, plan_id: int, day: str, meal_type: str, recipe: Recipe) -> Meal:
        meal = Meal(day=day, meal_type=meal_type, recipe=recipe)
        return await self._store.add_meal_to_plan(plan_id, meal)

    # ── Ratings ───────────────────────────────────────────────────

    async def rate(self, recipe_name: str, score: int) -> None:
        await self._store.save_rating(recipe_name, score)

    async def ratings(self) -> dict[str, int]:
        return await self._store.get_ratings()

    # ── AI ────────────────────────────────────────────────────────

    async def handle_chat(self, message: str) -> tuple[str, WeekPlan | None]:
        settings = await self.get_settings()
        recent_swaps = await self._store.get_recent_swaps()
        current_plan = await self._store.get_current_plan()
        reply, wants_plan = await self._planner.chat(message, settings, current_plan, recent_swaps)
        if not wants_plan:
            return reply, None
        return await self._generate_and_save_plan()

    async def generate_plan(self, slot_configs: list[SlotConfig] | None = None) -> tuple[str, WeekPlan]:
        return await self._generate_and_save_plan(slot_configs)

    async def _generate_and_save_plan(self, slot_configs: list[SlotConfig] | None = None) -> tuple[str, WeekPlan]:
        settings = await self.get_settings()
        recent_swaps = await self._store.get_recent_swaps()
        ratings = await self._store.get_ratings()
        recent_names = await self._store.get_recent_recipe_names()

        if slot_configs:
            slot_modes = {(s.day, s.meal_type): s.mode for s in slot_configs}
            normal_slots = [(s.day, s.meal_type) for s in slot_configs if s.mode == "normal"]
        else:
            slot_modes = {}
            normal_slots = list(MEAL_SLOTS)

        new_plan = await self._planner.generate_plan(
            settings, recent_swaps, ratings, recent_names,
            slots=normal_slots if slot_configs else None,
        )

        # Insert leftovers meals after normal slot meals
        recipe_by_slot = {(m.day, m.meal_type): m.recipe for m in new_plan.meals}
        for i, slot in enumerate(MEAL_SLOTS):
            if slot_modes.get(slot, "normal") != "leftovers":
                continue
            source_recipe = None
            for prev in reversed(MEAL_SLOTS[:i]):
                if slot_modes.get(prev, "normal") == "normal":
                    source_recipe = recipe_by_slot.get(prev)
                    break
            if source_recipe is None:
                continue
            day, meal_type = slot
            new_plan.meals.append(Meal(
                day=day, meal_type=meal_type, recipe=source_recipe,
                is_leftovers=True, source_recipe_name=source_recipe.name,
            ))

        # Sort by MEAL_SLOTS order
        slot_order = {slot: i for i, slot in enumerate(MEAL_SLOTS)}
        new_plan.meals.sort(key=lambda m: slot_order.get((m.day, m.meal_type), 99))

        today = date.today()
        this_monday = today - timedelta(days=today.weekday())
        existing = await self._store.get_all_plan_metas()
        if existing:
            latest = max(date.fromisoformat(m["week_start"]) for m in existing)
            new_plan.week_start = max(latest + timedelta(weeks=1), this_monday).isoformat()
        else:
            new_plan.week_start = this_monday.isoformat()

        new_plan = await self._store.save_new_plan(new_plan)

        normal_meals = [m for m in new_plan.meals if not m.is_leftovers]
        highlights = ", ".join(m.recipe.name for m in normal_meals[:3])
        extra = len(normal_meals) - 3
        reply = (
            f"Dein Wochenplan steht! "
            f"Highlights: {highlights}"
            + (f" – und {extra} weitere Gerichte." if extra > 0 else ".")
            + f' Im Tab "Wochenplan" kannst du alles einsehen und einzelne Mahlzeiten tauschen.'
        )
        return reply, new_plan

    async def generate_single_recipe(self) -> Recipe:
        settings = await self.get_settings()
        recent_swaps = await self._store.get_recent_swaps()
        ratings = await self._store.get_ratings()
        recent_names = await self._store.get_recent_recipe_names()
        return await self._planner.generate_single_recipe(settings, recent_swaps, ratings, recent_names)

    async def swap_meal_with_recipe(self, meal_id: int, recipe_id: int) -> Meal:
        meal = await self._store.get_meal_by_id(meal_id)
        if not meal:
            raise LookupError("Mahlzeit nicht gefunden")
        user_recipe = await self._store.get_user_recipe_by_id(recipe_id)
        if not user_recipe:
            raise LookupError("Eigenes Rezept nicht gefunden")
        return await self._store.apply_swap(meal_id, user_recipe.recipe, "eigenes_rezept")

    async def swap_meal(self, meal_id: int, reason: str) -> Meal:
        meal = await self._store.get_meal_by_id(meal_id)
        if not meal:
            raise LookupError("Mahlzeit nicht gefunden")
        current_plan = await self._store.get_current_plan()
        current_names = [
            m.recipe.name for m in (current_plan.meals if current_plan else [])
            if m.id != meal_id and not m.is_leftovers
        ]
        settings = await self.get_settings()
        recent_swaps = await self._store.get_recent_swaps()
        ratings = await self._store.get_ratings()
        new_recipe = await self._planner.replace_meal(
            old_recipe_name=meal.recipe.name,
            reason=reason,
            day=meal.day,
            meal_type=meal.meal_type,
            settings=settings,
            recent_swaps=recent_swaps,
            ratings=ratings,
            current_recipe_names=current_names or None,
        )
        return await self._store.apply_swap(meal_id, new_recipe, reason)

    # ── User Recipes ──────────────────────────────────────────────

    async def list_user_recipes(self) -> list[UserRecipe]:
        return await self._store.get_user_recipes()

    async def create_user_recipe(self, recipe: Recipe) -> UserRecipe:
        return await self._store.save_user_recipe(recipe)

    async def edit_user_recipe(self, recipe_id: int, recipe: Recipe) -> UserRecipe:
        result = await self._store.update_user_recipe(recipe_id, recipe)
        if not result:
            raise LookupError("Rezept nicht gefunden")
        return result

    async def delete_user_recipe(self, recipe_id: int) -> bool:
        if not await self._store.delete_user_recipe(recipe_id):
            raise LookupError("Rezept nicht gefunden")
        return True
