import os
from collections import defaultdict

import httpx

from .categories import CATEGORIES as CATEGORY_ORDER
from .database import get_current_plan
from .models import ShoppingItem, ShoppingList

_HA_API = "http://supervisor/core/api"


def _fmt(amount: float, unit: str) -> str:
    n = int(amount) if amount == int(amount) else amount
    return f"{n} {unit}".strip() if unit else str(n)


async def build_shopping_list() -> ShoppingList:
    plan = await get_current_plan()
    if not plan:
        return ShoppingList(items_by_category={})

    # (name_lower, unit_lower) → ShoppingItem
    aggregated: dict[tuple[str, str], ShoppingItem] = {}

    for meal in plan.meals:
        for ing in meal.recipe.ingredients:
            key = (ing.name.lower(), ing.unit.lower())
            if key in aggregated:
                aggregated[key].amount += ing.amount
            else:
                aggregated[key] = ShoppingItem(
                    name=ing.name,
                    amount=ing.amount,
                    unit=ing.unit,
                    category=ing.category if ing.category in CATEGORY_ORDER else "Sonstiges",
                )

    by_cat: dict[str, list[ShoppingItem]] = defaultdict(list)
    for item in aggregated.values():
        by_cat[item.category].append(item)

    ordered = {
        cat: sorted(by_cat[cat], key=lambda x: x.name)
        for cat in CATEGORY_ORDER
        if cat in by_cat
    }

    return ShoppingList(items_by_category=ordered)


async def push_to_ha(shopping_list: ShoppingList) -> dict:
    token = os.environ.get("SUPERVISOR_TOKEN", "")
    if not token:
        return {"ok": False, "error": "SUPERVISOR_TOKEN nicht verfügbar — läuft die App außerhalb von Home Assistant?"}

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    pushed, failed = 0, 0
    async with httpx.AsyncClient(timeout=10.0) as client:
        for items in shopping_list.items_by_category.values():
            for item in items:
                label = f"{_fmt(item.amount, item.unit)} {item.name}"
                try:
                    resp = await client.post(
                        f"{_HA_API}/services/shopping_list/add_item",
                        json={"name": label},
                        headers=headers,
                    )
                    resp.raise_for_status()
                    pushed += 1
                except Exception:
                    failed += 1

    return {"ok": failed == 0, "pushed": pushed, "failed": failed}
