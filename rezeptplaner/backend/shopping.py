from collections import defaultdict

from .categories import CATEGORIES as CATEGORY_ORDER
from .database import get_current_plan, get_plan_by_id
from .ha_client import HAClient
from .models import ShoppingItem, ShoppingList


def _fmt(amount: float, unit: str) -> str:
    n = int(amount) if amount == int(amount) else amount
    return f"{n} {unit}".strip() if unit else str(n)


async def build_shopping_list(plan_id: int | None = None) -> ShoppingList:
    plan = await get_plan_by_id(plan_id) if plan_id else await get_current_plan()
    if not plan:
        return ShoppingList(items_by_category={})

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

    return ShoppingList(items_by_category={
        cat: sorted(by_cat[cat], key=lambda x: x.name)
        for cat in CATEGORY_ORDER
        if cat in by_cat
    })


async def push_items(shopping_list: ShoppingList, client: HAClient) -> dict:
    pushed, failed = 0, 0
    for items in shopping_list.items_by_category.values():
        for item in items:
            label = f"{_fmt(item.amount, item.unit)} {item.name}"
            if await client.add_item(label):
                pushed += 1
            else:
                failed += 1
    return {"ok": failed == 0, "pushed": pushed, "failed": failed}
