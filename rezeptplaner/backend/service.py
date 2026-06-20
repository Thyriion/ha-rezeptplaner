from .database import (
    create_plan,
    get_current_plan,
    get_recent_swaps,
    get_settings,
    record_swap,
    save_meals,
    update_meal,
)
from .models import Meal, Settings, WeekPlan
from .recipes import PlannerAI


class PlanService:
    def __init__(self, planner: PlannerAI) -> None:
        self._planner = planner

    async def _settings(self) -> Settings:
        data = await get_settings()
        return Settings(**(data or {}))

    async def handle_chat(self, message: str) -> tuple[str, WeekPlan | None]:
        settings = await self._settings()
        recent_swaps = await get_recent_swaps()
        current_plan = await get_current_plan()

        reply, wants_plan = await self._planner.chat(message, settings, current_plan, recent_swaps)

        if not wants_plan:
            return reply, None

        new_plan = await self._planner.generate_plan(settings, recent_swaps)
        plan_id = await create_plan(new_plan.week_start)
        meal_ids = await save_meals(plan_id, new_plan.meals)
        for meal, mid in zip(new_plan.meals, meal_ids):
            meal.id = mid
        new_plan.id = plan_id

        highlights = ", ".join(m.recipe.name for m in new_plan.meals[:3])
        reply = (
            f"Dein Wochenplan für die komplette Woche steht! "
            f"Highlights: {highlights} – und 6 weitere Gerichte. "
            f'Im Tab "Wochenplan" kannst du alles einsehen, Rezepte aufklappen und einzelne Mahlzeiten tauschen.'
        )
        return reply, new_plan

    async def swap_meal(self, meal_id: int, reason: str) -> Meal:
        plan = await get_current_plan()
        if not plan:
            raise LookupError("Kein aktiver Wochenplan")

        meal = next((m for m in plan.meals if m.id == meal_id), None)
        if not meal:
            raise LookupError("Mahlzeit nicht gefunden")

        settings = await self._settings()
        recent_swaps = await get_recent_swaps()

        new_recipe = await self._planner.replace_meal(
            old_recipe_name=meal.recipe.name,
            reason=reason,
            day=meal.day,
            meal_type=meal.meal_type,
            settings=settings,
            recent_swaps=recent_swaps,
        )
        await record_swap(meal_id, meal.recipe.name, reason)
        await update_meal(meal_id, new_recipe)
        meal.recipe = new_recipe
        return meal
