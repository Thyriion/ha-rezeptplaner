import pytest

from ..database import MemoryPlanStore
from ..models import Recipe, Ingredient, NutritionInfo
from ..service import PlanService
from .conftest import FakePlannerAI


async def _make_service() -> PlanService:
    store = await MemoryPlanStore.init()
    return PlanService(store, FakePlannerAI())


@pytest.mark.asyncio
async def test_generate_plan_assigns_ids_and_saves():
    svc = await _make_service()
    _, plan = await svc.generate_plan()

    assert plan.id is not None
    assert len(plan.meals) > 0
    for meal in plan.meals:
        assert meal.id is not None

    fetched = await svc.get_plan(plan.id)
    assert fetched is not None
    assert fetched.id == plan.id
    assert len(fetched.meals) == len(plan.meals)


@pytest.mark.asyncio
async def test_user_recipe_round_trips_through_service():
    svc = await _make_service()

    recipe = Recipe(
        name="Hausgemachte Pizza",
        cooking_time_minutes=45,
        servings=4,
        ingredients=[
            Ingredient(name="Mehl", amount=500, unit="g", category="Getreide & Backwaren"),
        ],
        steps=["Teig kneten.", "30 Minuten backen."],
        nutrition_per_serving=NutritionInfo(calories=600, protein_g=18.0, carbs_g=90.0, fat_g=10.0),
    )

    created = await svc.create_user_recipe(recipe)
    assert created.id is not None
    assert created.recipe.name == "Hausgemachte Pizza"

    listed = await svc.list_user_recipes()
    assert any(ur.id == created.id for ur in listed)

    updated_recipe = Recipe(
        name="Pizza Margherita",
        cooking_time_minutes=40,
        servings=4,
        ingredients=recipe.ingredients,
        steps=recipe.steps,
        nutrition_per_serving=recipe.nutrition_per_serving,
    )
    edited = await svc.edit_user_recipe(created.id, updated_recipe)
    assert edited.recipe.name == "Pizza Margherita"

    deleted = await svc.delete_user_recipe(created.id)
    assert deleted is True

    listed_after = await svc.list_user_recipes()
    assert not any(ur.id == created.id for ur in listed_after)
