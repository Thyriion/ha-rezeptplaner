import json

import pytest

from ..catalog import classify, parse_ingredient, parse_recipe_page, scale_recipe
from ..database import MemoryPlanStore
from ..importer import CatalogImporter
from ..prices import estimate_price_per_serving
from .conftest import make_recipe


def _page(**overrides) -> str:
    node = {
        "@type": "Recipe",
        "name": "Cajun Pasta mit Bacon",
        "totalTime": "PT40M",
        "recipeYield": "2",
        "recipeIngredient": ["270 g Penne", "125 g Bacon (Scheiben)", "1 Stück Knoblauchzehe",
                             "1 Teelöffel Zucker", "nach Geschmack Salz"],
        "recipeInstructions": [{"@type": "HowToStep", "text": "<p>Wasser* kochen.</p>\n<p>Penne garen.</p>"}],
        "nutrition": {"calories": "868 kcal", "proteinContent": "31.5 g",
                      "carbohydrateContent": "109.6 g", "fatContent": "32.2 g"},
    }
    node.update(overrides)
    return f'<html><script type="application/ld+json">{json.dumps(node)}</script></html>'


def test_parse_recipe_page_extracts_recipe():
    entry = parse_recipe_page(_page(), "https://www.hellofresh.de/recipes/x-1")
    r = entry.recipe
    assert r.name == "Cajun Pasta mit Bacon"
    assert r.cooking_time_minutes == 40 and r.servings == 2
    assert r.steps == ["Wasser kochen. Penne garen."]
    assert r.nutrition_per_serving.calories == 868
    assert r.nutrition_per_serving.protein_g == 31.5
    assert r.source_url == "https://www.hellofresh.de/recipes/x-1"
    assert entry.protein_type == "fleisch" and not entry.is_vegetarian


def test_parse_recipe_page_rejects_incomplete_data():
    assert parse_recipe_page(_page(recipeIngredient=[]), "u") is None
    assert parse_recipe_page(_page(nutrition={"calories": None}), "u") is None
    assert parse_recipe_page("<html></html>", "u") is None


@pytest.mark.parametrize("line,amount,unit,name,category", [
    ("270 g Penne", 270, "g", "Penne", "Getreide & Backwaren"),
    ("1 Stück Knoblauchzehe", 1, "Stück", "Knoblauchzehe", "Gemüse & Obst"),
    ("1 Teelöffel Zucker", 1, "TL", "Zucker", "Gewürze & Öle"),
    ("nach Geschmack Salz", 0, "nach Geschmack", "Salz", "Gewürze & Öle"),
    ("2,5 EL Olivenöl", 2.5, "EL", "Olivenöl", "Gewürze & Öle"),
])
def test_parse_ingredient(line, amount, unit, name, category):
    ing = parse_ingredient(line)
    assert (ing.amount, ing.unit, ing.name, ing.category) == (amount, unit, name, category)


def test_classify_diet_flags():
    veg = make_recipe("Veggie", ingredient="Feta")
    assert classify(veg)["is_vegetarian"] and not classify(veg)["is_vegan"]
    vegan = make_recipe("Vegan", ingredient="Kokosmilch")
    assert classify(vegan)["is_vegan"]
    fish = make_recipe("Fisch", ingredient="Lachsfilet")
    assert classify(fish)["protein_type"] == "fisch" and not classify(fish)["is_vegetarian"]


def test_vegan_meat_substitutes_are_not_meat():
    recipe = make_recipe("Chili", ingredient="Veganes Hack")
    assert classify(recipe)["is_vegan"] and classify(recipe)["protein_type"] == "vegetarisch"


def test_scale_recipe_scales_amounts_and_servings():
    scaled = scale_recipe(make_recipe(servings=2), 3)
    assert scaled.servings == 3 and scaled.ingredients[0].amount == 300


@pytest.mark.asyncio
async def test_importer_imports_new_first_and_resumes():
    pages = {
        "https://www.hellofresh.de/recipes/old-5252b0fa301bbff2428b46a5": _page(name="Alt"),
        "https://www.hellofresh.de/recipes/new-68efa7d1a267a0000000000": _page(name="Neu"),
        "https://www.hellofresh.de/recipes/empty-68efa7d2a267a0000000000": _page(recipeIngredient=[]),
    }
    sitemap = "".join(f"<loc>{u}</loc>" for u in pages)

    async def fetch(url: str) -> str:
        return sitemap if url.endswith("sitemap_recipe_pages.xml") else pages[url]

    store = await MemoryPlanStore.init()
    importer = CatalogImporter(store, fetch=fetch, delay=0)
    status = await importer.run_to_completion(limit=2)
    assert status["imported"] == 1 and status["skipped"] == 1  # newest two: "empty" skipped, "Neu" imported

    status = await importer.run_to_completion()
    assert status["total"] == 1 and status["imported"] == 1  # only "Alt" is left
    assert await store.catalog_count() == 2


def test_price_estimate_is_plausible_and_ranks_ingredients():
    from ..models import Ingredient
    def recipe(*ings):
        return make_recipe().model_copy(update={"servings": 2, "ingredients": [
            Ingredient(name=n, amount=a, unit=u, category="Sonstiges") for n, a, u in ings]})
    pasta = estimate_price_per_serving(recipe(("Penne", 270, "g"), ("Tomatenmark", 20, "g"), ("Salz", 0, "nach Geschmack")))
    lachs = estimate_price_per_serving(recipe(("Lachsfilet", 300, "g"), ("Reis", 200, "g")))
    assert 0.3 < pasta < 1.5 and lachs > 3 * pasta
    assert parse_recipe_page(_page(), "u").recipe.price_per_serving > 0


@pytest.mark.asyncio
async def test_store_backfills_missing_prices():
    import aiosqlite
    from .conftest import make_entry
    store = await MemoryPlanStore.init()
    await store.catalog_add(make_entry("Alt", ingredient="Lachsfilet"))
    async with aiosqlite.connect(store._db_path) as db:
        await db.execute("UPDATE catalog_recipes SET price_per_serving = NULL")
        await db.commit()
    await store._backfill_prices()
    [cand] = await store.catalog_candidates()
    assert cand.price and cand.price > 0 and cand.protein_type == "fisch"
