import logging

import httpx

from .models import Ingredient, NutritionInfo, Recipe

logger = logging.getLogger(__name__)

USDA_SEARCH = "https://api.nal.usda.gov/fdc/v1/foods/search"

_UNIT_TO_G: dict[str, float] = {
    "g": 1.0, "gr": 1.0, "gram": 1.0, "gramm": 1.0,
    "kg": 1000.0, "kilogramm": 1000.0,
    "ml": 1.0, "milliliter": 1.0, "millilitre": 1.0,
    "l": 1000.0, "liter": 1000.0, "litre": 1000.0,
    "el": 15.0, "esslöffel": 15.0, "tbsp": 15.0,
    "tl": 5.0, "teelöffel": 5.0, "tsp": 5.0,
    "prise": 0.5, "pinch": 0.5,
}

# In-process cache: ingredient name_en → nutrients per 100g (or None if not found)
_cache: dict[str, dict | None] = {}


def _to_grams(amount: float, unit: str) -> float | None:
    factor = _UNIT_TO_G.get(unit.lower().strip())
    return amount * factor if factor is not None else None


async def _usda_per_100g(name_en: str, api_key: str) -> dict | None:
    if name_en in _cache:
        return _cache[name_en]
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.get(
                USDA_SEARCH,
                params={
                    "query": name_en,
                    "api_key": api_key,
                    "dataType": "Foundation,SR Legacy",
                    "pageSize": 1,
                },
            )
            foods = resp.json().get("foods", [])
            if not foods:
                _cache[name_en] = None
                return None
            nutrients = {n["nutrientName"]: n["value"] for n in foods[0]["foodNutrients"]}
            result = {
                "calories": (
                    nutrients.get("Energy (Atwater General Factors)")
                    or nutrients.get("Energy (Atwater Specific Factors)")
                    or nutrients.get("Energy")
                    or 0
                ),
                "protein_g": nutrients.get("Protein") or 0,
                "carbs_g": nutrients.get("Carbohydrate, by difference") or 0,
                "fat_g": nutrients.get("Total lipid (fat)") or 0,
            }
            _cache[name_en] = result
            return result
    except Exception:
        logger.warning("USDA lookup failed for %r", name_en)
        _cache[name_en] = None
        return None


async def enrich_nutrition(recipe: Recipe, api_key: str = "DEMO_KEY") -> None:
    """Replace recipe.nutrition_per_serving with USDA-based values in-place.
    Processes ingredients sequentially to respect API rate limits.
    Falls back silently if data is insufficient."""
    totals = {"calories": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}
    found_any = False

    for ing in recipe.ingredients:
        if not ing.name_en:
            continue
        grams = _to_grams(ing.amount, ing.unit)
        if grams is None:
            continue
        per_100g = await _usda_per_100g(ing.name_en, api_key)
        if per_100g is None:
            continue
        found_any = True
        factor = grams / 100
        for k in totals:
            totals[k] += per_100g[k] * factor

    if not found_any:
        return

    s = max(recipe.servings, 1)
    recipe.nutrition_per_serving = NutritionInfo(
        calories=round(totals["calories"] / s),
        protein_g=round(totals["protein_g"] / s, 1),
        carbs_g=round(totals["carbs_g"] / s, 1),
        fat_g=round(totals["fat_g"] / s, 1),
    )
