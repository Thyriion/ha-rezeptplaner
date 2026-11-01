import re
from collections import defaultdict

from .categories import CATEGORIES as CATEGORY_ORDER
from .ha_client import HAClient
from .models import ShoppingItem, ShoppingList, WeekPlan

_UNIT_ALIASES: dict[str, str] = {
    "stk": "stück", "stk.": "stück", "st": "stück", "st.": "stück", "stück": "stück",
    "el": "el", "esslöffel": "el", "tbsp": "el",
    "tl": "tl", "teelöffel": "tl", "tsp": "tl",
    "g": "g", "gr": "g", "gram": "g", "gramm": "g",
    "kg": "kg", "kilogramm": "kg",
    "ml": "ml", "milliliter": "ml", "millilitre": "ml",
    "l": "l", "liter": "l", "litre": "l",
    "prise": "prise", "pinch": "prise",
    "zehe": "zehe", "zehen": "zehe",
    "bund": "bund", "scheibe": "scheibe", "scheiben": "scheibe",
    "dose": "dose", "dosen": "dose", "glas": "glas",
}


def _norm_unit(unit: str) -> str:
    return _UNIT_ALIASES.get(unit.lower().strip(), unit.lower().strip())


PANTRY_CATEGORY = "Vorrat"
_PANTRY_RE = re.compile(r"\b(salz|pfeffer|zucker|öl|olivenöl|rapsöl|sonnenblumenöl|essig|balsamico)\b")
_NO_COST_RE = re.compile(r"^(leitungs|heißes |kaltes |warmes )?wasser\b|eiswürfel")


def _is_pantry(item: ShoppingItem) -> bool:
    """Staples most households own (salt, oil, ...) and 'to taste' items; not branded spice mixes."""
    name = item.name.lower()
    return not item.amount or (bool(_PANTRY_RE.search(name)) and "mischung" not in name and "hello" not in name)


def _merge_pantry(items: list[ShoppingItem]) -> list[ShoppingItem]:
    """One line per staple: amounts add up when units match, otherwise just 'nach Bedarf'."""
    merged: dict[str, ShoppingItem] = {}
    for item in items:
        key = item.name.lower()
        if key not in merged:
            merged[key] = item.model_copy()
        elif _norm_unit(merged[key].unit) == _norm_unit(item.unit):
            merged[key].amount += item.amount
        else:
            merged[key].amount, merged[key].unit = 0, "nach Bedarf"
    return list(merged.values())


def _fmt(amount: float, unit: str) -> str:
    if not amount:
        return unit
    n = int(amount) if amount == int(amount) else amount
    return f"{n} {unit}".strip() if unit else str(n)


def build_shopping_list(plan: WeekPlan | None) -> ShoppingList:
    if not plan:
        return ShoppingList(items_by_category={})

    aggregated: dict[tuple[str, str], ShoppingItem] = {}
    for meal in plan.meals:
        if meal.is_leftovers:
            continue
        multiplier = meal.portion_multiplier or 1
        for ing in meal.recipe.ingredients:
            key = (ing.name.lower(), _norm_unit(ing.unit))
            amount = ing.amount * multiplier
            if key in aggregated:
                aggregated[key].amount += amount
            else:
                aggregated[key] = ShoppingItem(
                    name=ing.name,
                    amount=amount,
                    unit=ing.unit,
                    category=ing.category if ing.category in CATEGORY_ORDER else "Sonstiges",
                )

    by_cat: dict[str, list[ShoppingItem]] = defaultdict(list)
    for item in aggregated.values():
        if _NO_COST_RE.search(item.name.lower()):
            continue
        by_cat[PANTRY_CATEGORY if _is_pantry(item) else item.category].append(item)

    if PANTRY_CATEGORY in by_cat:
        by_cat[PANTRY_CATEGORY] = _merge_pantry(by_cat[PANTRY_CATEGORY])

    return ShoppingList(items_by_category={
        cat: sorted(by_cat[cat], key=lambda x: x.name)
        for cat in [*CATEGORY_ORDER, PANTRY_CATEGORY]
        if cat in by_cat
    })


async def push_items(shopping_list: ShoppingList, client: HAClient) -> dict:
    pushed, failed = 0, 0
    for category, items in shopping_list.items_by_category.items():
        if category == PANTRY_CATEGORY:
            continue  # staples are assumed to be at home
        for item in items:
            label = f"{_fmt(item.amount, item.unit)} {item.name}"
            if await client.add_item(label):
                pushed += 1
            else:
                failed += 1
    return {"ok": failed == 0, "pushed": pushed, "failed": failed}
