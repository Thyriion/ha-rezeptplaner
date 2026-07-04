import pytest

from ..database import MemoryPlanStore
from ..models import Ingredient, NutritionInfo, Recipe, Settings, UserRecipe
from ..normalize import normalize_recipe_name
from ..prompt_builder import PromptBuilder
from ..recipes import _build_user_recipe_lookup, _replace_with_user_recipe
from ..service import PlanService


def _make_recipe(name: str = "Testnudeln") -> Recipe:
    return Recipe(
        name=name,
        cooking_time_minutes=20,
        servings=4,
        ingredients=[
            Ingredient(name="Nudeln", amount=200, unit="g", category="Getreide & Backwaren")
        ],
        steps=["Wasser kochen.", "Nudeln kochen."],
        nutrition_per_serving=NutritionInfo(calories=350, protein_g=12.0, carbs_g=60.0, fat_g=4.0),
    )


class UserRecipeMatchingPlannerAI:
    """Fake that returns a recipe whose name collides with a stored UserRecipe."""

    def _maybe_substitute(self, recipe, user_recipes):
        if not user_recipes:
            return recipe
        lookup = _build_user_recipe_lookup(user_recipes)
        return _replace_with_user_recipe(recipe, lookup)

    async def generate_plan(self, settings, recent_swaps, ratings=None,
                            recent_recipe_names=None, slots=None,
                            user_recipes=None):
        from datetime import date, timedelta
        from ..models import Meal, WeekPlan
        from ..prompt_builder import MEAL_SLOTS

        effective_slots = slots if slots is not None else list(MEAL_SLOTS)
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        # First slot collides with a user recipe (slightly different spelling).
        meals = [
            Meal(day=day, meal_type=mtype, recipe=_make_recipe(f"{day}-{mtype}"))
            for day, mtype in effective_slots
        ]
        if user_recipes:
            meals[0].recipe.name = "One Pot-Pasta"  # collides with "One-Pot Pasta"
            meals[0].recipe = self._maybe_substitute(meals[0].recipe, user_recipes)
        return WeekPlan(week_start=monday.isoformat(), meals=meals)

    async def generate_single_recipe(self, settings, recent_swaps,
                                     ratings=None, recent_recipe_names=None,
                                     user_recipes=None):
        recipe = _make_recipe("Einzelrezept")
        if user_recipes:
            recipe.name = "One Pot-Pasta"
        return self._maybe_substitute(recipe, user_recipes)

    async def replace_meal(self, old_recipe_name, reason, day, meal_type,
                           settings, recent_swaps, ratings=None,
                           current_recipe_names=None, user_recipes=None):
        recipe = _make_recipe(f"Ersatz für {old_recipe_name}")
        if user_recipes:
            recipe.name = "One Pot-Pasta"
        return self._maybe_substitute(recipe, user_recipes)

    async def chat(self, message, settings, current_plan, recent_swaps,
                   user_recipes=None):
        return "Kein Problem!", False


# ── normalize_recipe_name ───────────────────────────────────────────

@pytest.mark.parametrize("name,expected", [
    ("One-Pot Pasta", "onepotpasta"),
    ("One Pot-Pasta", "onepotpasta"),
    ("Cremiges Kürbis-Risotto", "cremigeskuerbisrisotto"),
    ("SPÄTZLE", "spaetzle"),
    ("Schweinebraten (Bayrisch)", "schweinebratenbayrisch"),
    ("  Pizza Margherita  ", "pizzamargherita"),
])
def test_normalize_recipe_name(name, expected):
    assert normalize_recipe_name(name) == expected


# ── prompt builder ──────────────────────────────────────────────────

def test_plan_prompt_lists_user_recipes():
    builder = PromptBuilder()
    prompt = builder.plan([("monday", "dinner")], 2, user_recipe_names=["One-Pot Pasta", "Kürbisrisotto"])
    assert "One-Pot Pasta" in prompt
    assert "Kürbisrisotto" in prompt
    assert "EXAKT das gespeicherte Rezept" in prompt


def test_plan_prompt_omits_empty_user_recipe_list():
    builder = PromptBuilder()
    prompt = builder.plan([("monday", "dinner")], 2)
    assert "Eigene Rezepte" not in prompt


# ── recipe lookup / substitution helpers ────────────────────────────

def test_replace_with_user_recipe_replaces_on_normalized_match():
    user_recipe = _make_recipe("One-Pot Pasta")
    lookup = _build_user_recipe_lookup([UserRecipe(recipe=user_recipe)])
    generated = _make_recipe("One Pot-Pasta")
    result = _replace_with_user_recipe(generated, lookup)
    assert result.name == "One-Pot Pasta"


def test_replace_with_user_recipe_keeps_unmatched_recipe():
    user_recipe = _make_recipe("One-Pot Pasta")
    lookup = _build_user_recipe_lookup([UserRecipe(recipe=user_recipe)])
    generated = _make_recipe("Spätzle")
    result = _replace_with_user_recipe(generated, lookup)
    assert result.name == "Spätzle"


# ── PlanService integration ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_plan_substitutes_user_recipe():
    store = await MemoryPlanStore.init()
    svc = PlanService(store, UserRecipeMatchingPlannerAI())

    await svc.create_user_recipe(_make_recipe("One-Pot Pasta"))

    _, plan = await svc.generate_plan()
    assert plan.meals[0].recipe.name == "One-Pot Pasta"


@pytest.mark.asyncio
async def test_generate_single_recipe_substitutes_user_recipe():
    store = await MemoryPlanStore.init()
    svc = PlanService(store, UserRecipeMatchingPlannerAI())

    await svc.create_user_recipe(_make_recipe("One-Pot Pasta"))

    recipe = await svc.generate_single_recipe()
    assert recipe.name == "One-Pot Pasta"


@pytest.mark.asyncio
async def test_swap_meal_substitutes_user_recipe():
    store = await MemoryPlanStore.init()
    svc = PlanService(store, UserRecipeMatchingPlannerAI())

    await svc.create_user_recipe(_make_recipe("One-Pot Pasta"))
    _, plan = await svc.generate_plan()
    meal = plan.meals[0]

    updated = await svc.swap_meal(meal.id, "sonstiges")
    assert updated.recipe.name == "One-Pot Pasta"


@pytest.mark.asyncio
async def test_low_rated_user_recipe_is_excluded_from_substitution():
    store = await MemoryPlanStore.init()
    svc = PlanService(store, UserRecipeMatchingPlannerAI())

    await svc.create_user_recipe(_make_recipe("One-Pot Pasta"))
    await svc.rate("One-Pot Pasta", 2)

    _, plan = await svc.generate_plan()
    # Because the user recipe is rated 2, it is not passed to the AI, so the
    # AI cannot substitute it even if the normalized name would match.
    assert plan.meals[0].recipe.name != "One-Pot Pasta"


# ── duplicate name guard ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cannot_save_user_recipe_with_duplicate_normalized_name():
    store = await MemoryPlanStore.init()
    svc = PlanService(store, UserRecipeMatchingPlannerAI())

    await svc.create_user_recipe(_make_recipe("One-Pot Pasta"))

    with pytest.raises(ValueError):
        await svc.create_user_recipe(_make_recipe("One Pot-Pasta"))


@pytest.mark.asyncio
async def test_cannot_update_user_recipe_to_duplicate_normalized_name():
    store = await MemoryPlanStore.init()
    svc = PlanService(store, UserRecipeMatchingPlannerAI())

    created = await svc.create_user_recipe(_make_recipe("One-Pot Pasta"))
    await svc.create_user_recipe(_make_recipe("Kürbisrisotto"))

    with pytest.raises(ValueError):
        await svc.edit_user_recipe(created.id, _make_recipe("Kürbis-Risotto"))
