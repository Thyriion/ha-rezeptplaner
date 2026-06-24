import logging

import httpx

from .models import NutritionInfo, Recipe

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


def _to_grams(amount: float, unit: str) -> float | None:
    factor = _UNIT_TO_G.get(unit.lower().strip())
    return amount * factor if factor is not None else None


class NutritionClient:
    def __init__(self, api_key: str = "DEMO_KEY", http: httpx.AsyncClient | None = None) -> None:
        self._api_key = api_key
        self._http = http or httpx.AsyncClient(timeout=6.0)
        self._cache: dict[str, dict | None] = {}

    async def enrich(self, recipe: Recipe) -> NutritionInfo | None:
        """Return NutritionInfo from USDA data, or None if insufficient data found."""
        totals = {"calories": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}
        found_any = False

        for ing in recipe.ingredients:
            if not ing.name_en:
                continue
            grams = _to_grams(ing.amount, ing.unit)
            if grams is None:
                continue
            per_100g = await self._per_100g(ing.name_en)
            if per_100g is None:
                continue
            found_any = True
            factor = grams / 100
            for k in totals:
                totals[k] += per_100g[k] * factor

        if not found_any:
            return None

        s = max(recipe.servings, 1)
        return NutritionInfo(
            calories=round(totals["calories"] / s),
            protein_g=round(totals["protein_g"] / s, 1),
            carbs_g=round(totals["carbs_g"] / s, 1),
            fat_g=round(totals["fat_g"] / s, 1),
        )

    async def _per_100g(self, name_en: str) -> dict | None:
        if name_en in self._cache:
            return self._cache[name_en]
        try:
            resp = await self._http.get(
                USDA_SEARCH,
                params={
                    "query": name_en,
                    "api_key": self._api_key,
                    "dataType": "Foundation,SR Legacy",
                    "pageSize": 1,
                },
            )
            foods = resp.json().get("foods", [])
            if not foods:
                self._cache[name_en] = None
                return None
            nutrients = {n["nutrientName"]: n["value"] for n in foods[0]["foodNutrients"]}
            protein = nutrients.get("Protein") or 0
            carbs = nutrients.get("Carbohydrate, by difference") or 0
            fat = nutrients.get("Total lipid (fat)") or 0
            result = {
                "calories": protein * 4 + carbs * 4 + fat * 9,
                "protein_g": protein,
                "carbs_g": carbs,
                "fat_g": fat,
            }
            self._cache[name_en] = result
            return result
        except Exception:
            logger.warning("USDA lookup failed for %r", name_en)
            self._cache[name_en] = None
            return None
