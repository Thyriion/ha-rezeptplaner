import pytest

from ..models import Ingredient, NutritionInfo, Recipe, Settings
from ..service import CatalogEmpty
from ..shopping import build_shopping_list
from .conftest import make_entry, make_service


@pytest.mark.asyncio
async def test_generate_plan_assigns_ids_and_saves():
    svc = await make_service()
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
    svc = await make_service()

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


@pytest.mark.asyncio
async def test_skip_slot_removes_meal_and_creates_skipped_slot():
    svc = await make_service()
    _, plan = await svc.generate_plan()
    target = plan.meals[0]

    skipped = await svc.skip_slot(plan.id, target.day, target.meal_type)
    assert skipped.day == target.day
    assert skipped.meal_type == target.meal_type

    fetched = await svc.get_plan(plan.id)
    assert not any(m.day == target.day and m.meal_type == target.meal_type for m in fetched.meals)
    assert any(s.day == target.day and s.meal_type == target.meal_type for s in fetched.skipped_slots)


@pytest.mark.asyncio
async def test_double_slot_creates_leftovers_and_doubles_multiplier():
    svc = await make_service()
    _, plan = await svc.generate_plan()
    # The plan fills all MEAL_SLOTS, so we can double the second slot.
    target_slot = ("tuesday", "dinner")

    leftovers = await svc.double_slot(plan.id, target_slot[0], target_slot[1])
    assert leftovers.is_leftovers
    assert leftovers.source_meal_id is not None

    fetched = await svc.get_plan(plan.id)
    source = next(m for m in fetched.meals if m.day == "monday" and m.meal_type == "dinner")
    assert source.portion_multiplier == 2

    # The target slot is now a leftovers meal, the source cooks for double portions.
    target = next(m for m in fetched.meals if m.day == target_slot[0] and m.meal_type == target_slot[1])
    assert target.is_leftovers


@pytest.mark.asyncio
async def test_undo_double_resets_multiplier_and_removes_leftovers():
    svc = await make_service()
    _, plan = await svc.generate_plan()
    target_slot = ("tuesday", "dinner")

    leftovers = await svc.double_slot(plan.id, target_slot[0], target_slot[1])
    await svc.undo_double(leftovers.id)

    fetched = await svc.get_plan(plan.id)
    source = next(m for m in fetched.meals if m.day == "monday" and m.meal_type == "dinner")
    assert source.portion_multiplier == 1
    assert not any(m.id == leftovers.id for m in fetched.meals)


@pytest.mark.asyncio
async def test_double_slot_fails_without_preceding_normal_meal():
    svc = await make_service()
    _, plan = await svc.generate_plan()
    # First slot has no preceding normal meal.
    first = plan.meals[0]
    with pytest.raises(ValueError):
        await svc.double_slot(plan.id, first.day, first.meal_type)


@pytest.mark.asyncio
async def test_fill_skipped_slot_replaces_skipped_marker():
    svc = await make_service()
    _, plan = await svc.generate_plan()
    target = plan.meals[0]
    await svc.skip_slot(plan.id, target.day, target.meal_type)

    meal = await svc.fill_skipped_slot(plan.id, target.day, target.meal_type, reason="sonstiges")
    assert meal.day == target.day
    assert meal.meal_type == target.meal_type

    fetched = await svc.get_plan(plan.id)
    assert any(m.day == target.day and m.meal_type == target.meal_type for m in fetched.meals)
    assert not any(s.day == target.day and s.meal_type == target.meal_type for s in fetched.skipped_slots)


@pytest.mark.asyncio
async def test_settings_round_trips_available_devices():
    svc = await make_service()
    settings = Settings(available_devices=["Airfryer", "Reiskocher"])
    saved = await svc.update_settings(settings)
    assert saved.available_devices == ["Airfryer", "Reiskocher"]

    loaded = await svc.get_settings()
    assert loaded.available_devices == ["Airfryer", "Reiskocher"]


@pytest.mark.asyncio
async def test_settings_normalizes_available_devices():
    svc = await make_service()
    settings = Settings(available_devices=["airfryer", "AIRFRYER", "Reiskocher", ""])
    saved = await svc.update_settings(settings)
    assert saved.available_devices == ["Airfryer", "Reiskocher"]


@pytest.mark.asyncio
async def test_generate_plan_requires_catalog():
    svc = await make_service(catalog_size=0)
    with pytest.raises(CatalogEmpty):
        await svc.generate_plan()


@pytest.mark.asyncio
async def test_plan_has_distinct_recipes_scaled_to_persons():
    svc = await make_service()
    await svc.update_settings(Settings(persons=4))
    _, plan = await svc.generate_plan()

    names = [m.recipe.name for m in plan.meals]
    assert len(names) == len(set(names)) == 9
    assert all(m.recipe.servings == 4 for m in plan.meals)
    assert all(m.recipe.ingredients[0].amount == 400 for m in plan.meals)


@pytest.mark.asyncio
async def test_swap_meal_picks_a_different_recipe_not_in_plan():
    svc = await make_service()
    _, plan = await svc.generate_plan()
    meal = plan.meals[0]
    in_plan = {m.recipe.name for m in plan.meals}

    swapped = await svc.swap_meal(meal.id, "mag_ich_nicht")
    assert swapped.recipe.name not in in_plan


@pytest.mark.asyncio
async def test_chat_plan_intent_builds_plan_and_search_returns_recipe():
    svc = await make_service()
    reply, plan, recipe = await svc.handle_chat("Mach mir einen Wochenplan")
    assert plan is not None and recipe is None

    await svc._store.catalog_add(make_entry("Curry-Topf", ingredient="Hähnchenbrust"))
    reply, plan, recipe = await svc.handle_chat("Ich hätte Lust auf Hähnchen")
    assert plan is None and recipe.name == "Curry-Topf"

    reply, plan, recipe = await svc.handle_chat("Sushi")
    assert plan is None and recipe is None and "kein passendes" in reply
