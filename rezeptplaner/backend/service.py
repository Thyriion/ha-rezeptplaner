import asyncio
import logging
from datetime import date, timedelta

from .database import PlanStore
from .devices import normalize_device
from .models import Meal, PlanMeta, Recipe, Settings, SkippedSlot, UserRecipe, WeekPlan
from .normalize import normalize_recipe_name
from .nutrition import NutritionClient
from .prompt_builder import MEAL_SLOTS
from .recipes import PlannerAI

logger = logging.getLogger(__name__)


class PlanService:
    def __init__(self, store: PlanStore, planner: PlannerAI, nutrition: NutritionClient | None = None) -> None:
        self._store = store
        self._planner = planner
        self._nutrition = nutrition or NutritionClient(
            api_key="DEMO_KEY",
            cache_get=store.get_usda_cache,
            cache_set=store.save_usda_cache,
        )

    @staticmethod
    def _eligible_user_recipes(
        user_recipes: list[UserRecipe], ratings: dict[str, int]
    ) -> list[UserRecipe]:
        return [ur for ur in user_recipes if ratings.get(ur.recipe.name, 5) >= 3]

    # ── Settings ──────────────────────────────────────────────────

    async def get_settings(self) -> Settings:
        return Settings(**(await self._store.get_settings() or {}))

    async def update_settings(self, settings: Settings) -> Settings:
        seen = set()
        normalized = []
        for device in (settings.available_devices or []):
            canonical = normalize_device(device)
            key = canonical.lower()
            if key and key not in seen:
                seen.add(key)
                normalized.append(canonical)
        settings.available_devices = normalized
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
        meal = await self._store.add_meal_to_plan(plan_id, meal)
        # If this slot was previously skipped, remove the skipped marker.
        await self._store.remove_skipped_slot(plan_id, day, meal_type)
        return meal

    async def skip_slot(self, plan_id: int, day: str, meal_type: str) -> SkippedSlot:
        plan = await self._store.get_plan_by_id(plan_id)
        if not plan:
            raise LookupError("Plan nicht gefunden")
        if plan.meals and all(m.confirmed for m in plan.meals):
            raise ValueError("Plan ist bereits bestätigt")

        target = next((m for m in plan.meals if m.day == day and m.meal_type == meal_type), None)
        if target and target.id:
            # If target is a leftovers meal, reset its source meal's multiplier first.
            if target.is_leftovers and target.source_meal_id:
                source = await self._store.get_meal_by_id(target.source_meal_id)
                if source:
                    await self._store.update_meal_portion_multiplier(source.id, 1)
            await self._store.delete_meal_by_id(target.id)

        # Avoid duplicate skipped slots.
        already_skipped = any(s.day == day and s.meal_type == meal_type for s in plan.skipped_slots)
        if already_skipped:
            return next(s for s in plan.skipped_slots if s.day == day and s.meal_type == meal_type)

        return await self._store.add_skipped_slot(plan_id, day, meal_type)

    async def double_slot(self, plan_id: int, day: str, meal_type: str) -> Meal:
        plan = await self._store.get_plan_by_id(plan_id)
        if not plan:
            raise LookupError("Plan nicht gefunden")
        if plan.meals and all(m.confirmed for m in plan.meals):
            raise ValueError("Plan ist bereits bestätigt")

        slot_order = {slot: i for i, slot in enumerate(MEAL_SLOTS)}
        target_key = (day, meal_type)
        if target_key not in slot_order:
            raise ValueError("Ungültiger Slot")

        target_idx = slot_order[target_key]
        if target_idx == 0:
            raise ValueError("Kein vorheriger Slot vorhanden")

        prev_key = MEAL_SLOTS[target_idx - 1]
        prev_meal = next((m for m in plan.meals if m.day == prev_key[0] and m.meal_type == prev_key[1] and not m.is_leftovers), None)
        if not prev_meal:
            raise ValueError("Vorheriger Slot ist kein normales Meal")

        # Remove any existing meal or skipped marker at the target slot.
        existing_target = next((m for m in plan.meals if m.day == day and m.meal_type == meal_type and m.id), None)
        if existing_target:
            await self._store.delete_meal_by_id(existing_target.id)
        await self._store.remove_skipped_slot(plan_id, day, meal_type)

        await self._store.update_meal_portion_multiplier(prev_meal.id, 2)
        return await self._store.add_leftovers_meal(plan_id, day, meal_type, prev_meal)

    async def undo_double(self, leftovers_meal_id: int) -> None:
        leftovers = await self._store.get_meal_by_id(leftovers_meal_id)
        if not leftovers or not leftovers.is_leftovers:
            raise LookupError("Leftovers-Meal nicht gefunden")
        if leftovers.source_meal_id:
            source = await self._store.get_meal_by_id(leftovers.source_meal_id)
            if source:
                await self._store.update_meal_portion_multiplier(source.id, 1)
        await self._store.delete_meal_by_id(leftovers_meal_id)

    async def fill_skipped_slot(self, plan_id: int, day: str, meal_type: str, *, reason: str | None = None, recipe_id: int | None = None) -> Meal:
        plan = await self._store.get_plan_by_id(plan_id)
        if not plan:
            raise LookupError("Plan nicht gefunden")
        if plan.meals and all(m.confirmed for m in plan.meals):
            raise ValueError("Plan ist bereits bestätigt")
        if not any(s.day == day and s.meal_type == meal_type for s in plan.skipped_slots):
            raise ValueError("Slot ist nicht ausgelassen")

        if recipe_id is not None:
            user_recipe = await self._store.get_user_recipe_by_id(recipe_id)
            if not user_recipe:
                raise LookupError("Eigenes Rezept nicht gefunden")
            return await self.add_recipe_to_plan(plan_id, day, meal_type, user_recipe.recipe)

        # AI suggestion
        current_names = [m.recipe.name for m in plan.meals if not m.is_leftovers]
        settings = await self.get_settings()
        recent_swaps = await self._store.get_recent_swaps()
        ratings = await self._store.get_ratings()
        user_recipes = self._eligible_user_recipes(
            await self._store.get_user_recipes(), ratings
        )
        new_recipe = await self._planner.replace_meal(
            old_recipe_name="",
            reason=reason or "sonstiges",
            day=day,
            meal_type=meal_type,
            settings=settings,
            recent_swaps=recent_swaps,
            ratings=ratings,
            current_recipe_names=current_names or None,
            user_recipes=user_recipes,
        )
        added = await self.add_recipe_to_plan(plan_id, day, meal_type, new_recipe)
        self._enqueue_enrich(added.recipe, meal_id=added.id)
        return added

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
        ratings = await self._store.get_ratings()
        user_recipes = self._eligible_user_recipes(
            await self._store.get_user_recipes(), ratings
        )
        reply, wants_plan = await self._planner.chat(
            message, settings, current_plan, recent_swaps, user_recipes=user_recipes
        )
        if not wants_plan:
            return reply, None
        return await self._generate_and_save_plan()

    async def generate_plan(self) -> tuple[str, WeekPlan]:
        return await self._generate_and_save_plan()

    async def _generate_and_save_plan(self) -> tuple[str, WeekPlan]:
        settings = await self.get_settings()
        recent_swaps = await self._store.get_recent_swaps()
        ratings = await self._store.get_ratings()
        recent_names = await self._store.get_recent_recipe_names()
        user_recipes = self._eligible_user_recipes(
            await self._store.get_user_recipes(), ratings
        )

        new_plan = await self._planner.generate_plan(
            settings, recent_swaps, ratings, recent_names,
            slots=list(MEAL_SLOTS),
            user_recipes=user_recipes,
        )

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

        new_plan.skipped_slots = []
        new_plan = await self._store.save_new_plan(new_plan)

        for meal in new_plan.meals:
            if not meal.is_leftovers and meal.id:
                self._enqueue_enrich(meal.recipe, meal_id=meal.id)

        normal_meals = [m for m in new_plan.meals if not m.is_leftovers]
        highlights = ", ".join(m.recipe.name for m in normal_meals[:3])
        extra = len(normal_meals) - 3
        reply = (
            f"Dein Wochenplan steht! "
            f"Highlights: {highlights}"
            + (f" – und {extra} weitere Gerichte." if extra > 0 else ".")
            + f' Im Tab "Wochenplan" kannst du alles einsehen, Mahlzeiten tauschen, auslassen oder verdoppeln.'
        )
        return reply, new_plan

    async def generate_single_recipe(self) -> Recipe:
        settings = await self.get_settings()
        recent_swaps = await self._store.get_recent_swaps()
        ratings = await self._store.get_ratings()
        recent_names = await self._store.get_recent_recipe_names()
        user_recipes = self._eligible_user_recipes(
            await self._store.get_user_recipes(), ratings
        )
        recipe = await self._planner.generate_single_recipe(
            settings, recent_swaps, ratings, recent_names, user_recipes=user_recipes
        )
        self._enqueue_enrich(recipe)
        return recipe

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
        user_recipes = self._eligible_user_recipes(
            await self._store.get_user_recipes(), ratings
        )
        new_recipe = await self._planner.replace_meal(
            old_recipe_name=meal.recipe.name,
            reason=reason,
            day=meal.day,
            meal_type=meal.meal_type,
            settings=settings,
            recent_swaps=recent_swaps,
            ratings=ratings,
            current_recipe_names=current_names or None,
            user_recipes=user_recipes,
        )
        updated = await self._store.apply_swap(meal_id, new_recipe, reason)
        self._enqueue_enrich(updated.recipe, meal_id=updated.id)
        return updated

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

    # ── Nutrition enrichment ────────────────────────────────────────

    def _enqueue_enrich(self, recipe: Recipe, meal_id: int | None = None) -> None:
        """Start background USDA enrichment for a recipe.

        If meal_id is provided, the enriched nutrition is persisted back to the
        meal's recipe_json once it becomes available.
        """
        asyncio.create_task(self._enrich_and_persist(recipe, meal_id))

    async def _enrich_and_persist(self, recipe: Recipe, meal_id: int | None) -> None:
        try:
            nutrition = await self._nutrition.enrich(recipe)
            if nutrition is None:
                return
            recipe.nutrition_per_serving = nutrition
            recipe.nutrition_enriched = True
            if meal_id is not None:
                await self._store.update_meal_recipe(meal_id, recipe)
        except Exception:
            logger.exception("Background nutrition enrichment failed")

    async def wait_for_nutrition(self, plan_id: int, timeout: float = 30.0) -> WeekPlan | None:
        """Long-polling helper: return the plan as soon as all meals have enriched nutrition."""
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            plan = await self._store.get_plan_by_id(plan_id)
            if plan is None:
                return None
            if all(
                m.recipe.nutrition_enriched or m.is_leftovers
                for m in plan.meals
            ):
                return plan
            await asyncio.sleep(1.0)
        return await self._store.get_plan_by_id(plan_id)
