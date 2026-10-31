import logging
import random
import re
from datetime import date, timedelta

from .catalog import classify, ingredients_text, scale_recipe
from .database import PlanStore
from .devices import normalize_device
from .models import Meal, PlanMeta, Recipe, Settings, SkippedSlot, UserRecipe, WeekPlan
from .selector import Candidate, pick_recipes
from .slots import MEAL_SLOTS

logger = logging.getLogger(__name__)

_PLAN_INTENT_RE = re.compile(r"wochenplan|\bplan\b|\bwoche\b", re.IGNORECASE)
_STOPWORDS = {"ich", "mir", "mit", "und", "oder", "etwas", "was", "für", "ein", "eine", "einen", "mal",
              "gern", "gerne", "hab", "habe", "lust", "auf", "rezept", "gericht", "kochen", "essen", "das", "den"}


class CatalogEmpty(Exception):
    """No recipes available yet — the catalog has not been imported."""


class NoMatchingRecipes(Exception):
    """The household's settings exclude every available recipe."""


class PlanService:
    def __init__(self, store: PlanStore, rng: random.Random | None = None) -> None:
        self._store = store
        self._rng = rng or random.Random()

    @staticmethod
    def _eligible_user_recipes(
        user_recipes: list[UserRecipe], ratings: dict[str, int]
    ) -> list[UserRecipe]:
        return [ur for ur in user_recipes if ratings.get(ur.recipe.name, 5) >= 3]

    async def catalog_count(self) -> int:
        return await self._store.catalog_count()

    # ── Recipe selection ──────────────────────────────────────────

    async def _candidates(self, user_recipes: list[UserRecipe]) -> list[Candidate]:
        candidates = await self._store.catalog_candidates()
        for ur in user_recipes:
            r = ur.recipe
            candidates.append(Candidate(
                key=f"u:{ur.id}", name=r.name, cooking_time=r.cooking_time_minutes,
                ingredients_text=ingredients_text(r), devices=list(r.suggested_devices),
                protein_g=r.nutrition_per_serving.protein_g, carbs_g=r.nutrition_per_serving.carbs_g,
                is_user=True, **classify(r),
            ))
        return candidates

    async def _pick(self, count: int, *, hard_avoid: list[str] | None = None,
                    extra_swaps: list[dict] | None = None, only: "callable | None" = None) -> list[Recipe]:
        """Pick `count` recipes for the household, scaled to the configured person count."""
        settings = await self.get_settings()
        ratings = await self._store.get_ratings()
        user_recipes = self._eligible_user_recipes(await self._store.get_user_recipes(), ratings)
        candidates = await self._candidates(user_recipes)
        if not candidates:
            raise CatalogEmpty("Der Rezeptkatalog ist noch leer. Bitte zuerst den Import starten.")
        if only is not None:
            candidates = [c for c in candidates if only(c)]

        swaps = await self._store.get_recent_swaps() + (extra_swaps or [])
        soft_avoid = [s["recipe"] for s in swaps]
        soft_avoid += await self._store.get_recent_recipe_names()
        picks = pick_recipes(candidates, count, settings, ratings, soft_avoid, hard_avoid, swaps, self._rng)
        if not picks:
            raise NoMatchingRecipes(
                "Keine Rezepte passen zu deinen Einstellungen. Lockere Ernährungsform, Kochzeit oder Abneigungen."
            )

        user_by_id = {f"u:{ur.id}": ur.recipe for ur in user_recipes}
        catalog = await self._store.catalog_get_recipes(
            [int(c.key[2:]) for c in picks if c.key.startswith("c:")]
        )
        recipes = [
            user_by_id[c.key] if c.is_user else catalog[int(c.key[2:])]
            for c in picks
        ]
        return [scale_recipe(r, settings.persons) for r in recipes]

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

        current_names = [m.recipe.name for m in plan.meals if not m.is_leftovers]
        [new_recipe] = await self._pick(1, hard_avoid=current_names)
        return await self.add_recipe_to_plan(plan_id, day, meal_type, new_recipe)

    # ── Ratings ───────────────────────────────────────────────────

    async def rate(self, recipe_name: str, score: int) -> None:
        await self._store.save_rating(recipe_name, score)

    async def ratings(self) -> dict[str, int]:
        return await self._store.get_ratings()

    # ── Selection ─────────────────────────────────────────────────

    async def handle_chat(self, message: str) -> tuple[str, WeekPlan | None, Recipe | None]:
        """Keyword-driven chat: a plan request builds a plan, anything else searches the catalog."""
        if _PLAN_INTENT_RE.search(message):
            reply, plan = await self._generate_and_save_plan()
            return reply, plan, None

        terms = [t for t in re.findall(r"[\wäöüß]{3,}", message.lower()) if t not in _STOPWORDS]
        if not terms:
            return ("Schreib mir z. B. \"Hähnchen\" oder \"Pasta\" und ich suche ein passendes Rezept — "
                    "oder sag \"Wochenplan\", dann stelle ich dir eine Woche zusammen."), None, None
        # Prefer recipes matching every keyword; fall back to any keyword for natural sentences.
        for matcher in (all, any):
            try:
                [recipe] = await self._pick(
                    1, only=lambda c: matcher(t in f"{c.name.lower()} {c.ingredients_text}" for t in terms)
                )
                break
            except NoMatchingRecipes:
                continue
        else:
            return "Dazu habe ich kein passendes Rezept gefunden. Versuch es mit einem anderen Stichwort.", None, None
        return f"Wie wäre es mit „{recipe.name}“?", None, recipe

    async def generate_plan(self) -> tuple[str, WeekPlan]:
        return await self._generate_and_save_plan()

    async def _generate_and_save_plan(self) -> tuple[str, WeekPlan]:
        recipes = await self._pick(len(MEAL_SLOTS))
        meals = [
            Meal(day=day, meal_type=meal_type, recipe=recipe)
            for (day, meal_type), recipe in zip(MEAL_SLOTS, recipes)
        ]

        today = date.today()
        this_monday = today - timedelta(days=today.weekday())
        existing = await self._store.get_all_plan_metas()
        if existing:
            latest = max(date.fromisoformat(m["week_start"]) for m in existing)
            week_start = max(latest + timedelta(weeks=1), this_monday)
        else:
            week_start = this_monday
        new_plan = await self._store.save_new_plan(WeekPlan(week_start=week_start.isoformat(), meals=meals))

        highlights = ", ".join(m.recipe.name for m in meals[:3])
        extra = len(meals) - 3
        reply = (
            f"Dein Wochenplan steht! "
            f"Highlights: {highlights}"
            + (f" – und {extra} weitere Gerichte." if extra > 0 else ".")
            + ' Im Tab "Wochenplan" kannst du alles einsehen, Mahlzeiten tauschen, auslassen oder verdoppeln.'
        )
        if len(meals) < len(MEAL_SLOTS):
            reply += f" (Nur {len(meals)} von {len(MEAL_SLOTS)} Slots konnten mit passenden Rezepten gefüllt werden.)"
        return reply, new_plan

    async def generate_single_recipe(self) -> Recipe:
        [recipe] = await self._pick(1)
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
            if not m.is_leftovers
        ]
        [new_recipe] = await self._pick(
            1, hard_avoid=current_names + [meal.recipe.name],
            extra_swaps=[{"recipe": meal.recipe.name, "reason": reason}],
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
