import pytest

from ..models import Ingredient, Meal, NutritionInfo, Recipe, WeekPlan
from ..shopping import PANTRY_CATEGORY, build_shopping_list, push_items


def _plan(*ingredients: tuple[str, float, str, str]) -> WeekPlan:
    recipe = Recipe(
        name="Test", cooking_time_minutes=10, servings=2, steps=["x"],
        ingredients=[Ingredient(name=n, amount=a, unit=u, category=c) for n, a, u, c in ingredients],
        nutrition_per_serving=NutritionInfo(calories=1, protein_g=1, carbs_g=1, fat_g=1),
    )
    return WeekPlan(week_start="2026-01-05", meals=[Meal(day="monday", meal_type="dinner", recipe=recipe)])


def test_staples_and_to_taste_items_go_to_pantry_and_water_is_dropped():
    plan = _plan(
        ("Nudeln", 200, "g", "Getreide & Backwaren"),
        ("Salz", 0, "nach Geschmack", "Gewürze & Öle"),
        ("Olivenöl", 1, "EL", "Gewürze & Öle"),
        ("Zucker", 1, "TL", "Gewürze & Öle"),
        ("Gewürzmischung „Hello Cajun“", 4, "g", "Gewürze & Öle"),
        ("Wasser", 100, "ml", "Sonstiges"),
    )
    cats = build_shopping_list(plan).items_by_category
    assert [i.name for i in cats["Getreide & Backwaren"]] == ["Nudeln"]
    assert [i.name for i in cats["Gewürze & Öle"]] == ["Gewürzmischung „Hello Cajun“"]
    assert sorted(i.name for i in cats[PANTRY_CATEGORY]) == ["Olivenöl", "Salz", "Zucker"]
    assert list(cats)[-1] == PANTRY_CATEGORY
    assert not any(i.name == "Wasser" for items in cats.values() for i in items)


class _FakeHA:
    def __init__(self):
        self.labels = []

    async def add_item(self, label):
        self.labels.append(label)
        return True


@pytest.mark.asyncio
async def test_pantry_items_are_not_pushed_to_home_assistant():
    plan = _plan(("Nudeln", 200, "g", "Getreide & Backwaren"), ("Salz", 0, "nach Geschmack", "Gewürze & Öle"))
    ha = _FakeHA()
    result = await push_items(build_shopping_list(plan), ha)
    assert result["pushed"] == 1 and ha.labels == ["200 g Nudeln"]


def test_pantry_lines_are_merged_per_item():
    plan = _plan(
        ("Salz", 0, "nach Geschmack", "Gewürze & Öle"),
        ("Salz", 1, "Prise", "Gewürze & Öle"),
        ("Öl", 1, "EL", "Gewürze & Öle"),
        ("Öl", 2, "EL", "Gewürze & Öle"),
    )
    pantry = {i.name: i for i in build_shopping_list(plan).items_by_category[PANTRY_CATEGORY]}
    assert set(pantry) == {"Salz", "Öl"}
    assert pantry["Öl"].amount == 3 and pantry["Salz"].unit == "nach Bedarf"
