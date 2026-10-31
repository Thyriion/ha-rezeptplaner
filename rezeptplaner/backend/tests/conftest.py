import random

from ..catalog import CatalogEntry, classify, ingredients_text
from ..database import MemoryPlanStore
from ..models import Ingredient, NutritionInfo, Recipe
from ..service import PlanService


def make_recipe(name: str = "Testnudeln", servings: int = 2, ingredient: str = "Nudeln") -> Recipe:
    return Recipe(
        name=name,
        cooking_time_minutes=20,
        servings=servings,
        ingredients=[Ingredient(name=ingredient, amount=200, unit="g", category="Getreide & Backwaren")],
        steps=["Wasser kochen.", "Nudeln 8 Minuten kochen."],
        nutrition_per_serving=NutritionInfo(calories=350, protein_g=12.0, carbs_g=60.0, fat_g=4.0),
    )


def make_entry(name: str, ingredient: str = "Nudeln", **recipe_overrides) -> CatalogEntry:
    recipe = make_recipe(name, ingredient=ingredient).model_copy(update=recipe_overrides)
    return CatalogEntry(
        source_url=f"https://example.test/recipes/{name}",
        recipe=recipe,
        ingredients_text=ingredients_text(recipe),
        **classify(recipe),
    )


async def make_service(catalog_size: int = 20) -> PlanService:
    store = await MemoryPlanStore.init()
    for i in range(catalog_size):
        await store.catalog_add(make_entry(f"Katalogrezept {i}"))
    return PlanService(store, rng=random.Random(42))
