from datetime import date, timedelta

from ..models import Ingredient, Meal, NutritionInfo, Recipe, Settings, WeekPlan
from ..prompt_builder import MEAL_SLOTS


def _make_recipe(name: str = "Testnudeln") -> Recipe:
    return Recipe(
        name=name,
        cooking_time_minutes=20,
        servings=2,
        ingredients=[
            Ingredient(name="Nudeln", amount=200, unit="g", category="Getreide & Backwaren")
        ],
        steps=["Wasser kochen.", "Nudeln 8 Minuten kochen."],
        nutrition_per_serving=NutritionInfo(calories=350, protein_g=12.0, carbs_g=60.0, fat_g=4.0),
    )


class FakePlannerAI:
    """Deterministic stand-in for PlannerAI — never calls the AI API."""

    async def generate_plan(self, settings, recent_swaps, ratings=None,
                            recent_recipe_names=None, slots=None) -> WeekPlan:
        effective_slots = slots if slots is not None else list(MEAL_SLOTS)
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        meals = [
            Meal(day=day, meal_type=mtype, recipe=_make_recipe(f"{day}-{mtype}"))
            for day, mtype in effective_slots
        ]
        return WeekPlan(week_start=monday.isoformat(), meals=meals)

    async def generate_single_recipe(self, settings, recent_swaps,
                                     ratings=None, recent_recipe_names=None) -> Recipe:
        return _make_recipe("Einzelrezept")

    async def replace_meal(self, old_recipe_name, reason, day, meal_type,
                           settings, recent_swaps, ratings=None,
                           current_recipe_names=None) -> Recipe:
        return _make_recipe(f"Ersatz für {old_recipe_name}")

    async def chat(self, message, settings, current_plan, recent_swaps):
        return "Kein Problem!", False
