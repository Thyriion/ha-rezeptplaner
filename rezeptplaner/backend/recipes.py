import asyncio
import json
import logging
from datetime import date, timedelta

from .ai_client import get_client
from .config import AppConfig, load
from .models import Meal, Recipe, Settings, WeekPlan
from .nutrition import enrich_nutrition
from .prompt_builder import MEAL_SLOTS, PromptBuilder

logger = logging.getLogger(__name__)


class PlannerAI:
    def __init__(self, cfg: AppConfig | None = None) -> None:
        self._cfg = cfg or load()
        self._prompts = PromptBuilder()

    def _client(self) -> tuple:
        return get_client(self._cfg)

    async def generate_plan(
        self,
        settings: Settings,
        recent_swaps: list[dict],
        ratings: dict[str, int] | None = None,
        recent_recipe_names: list[str] | None = None,
    ) -> WeekPlan:
        client, model = self._client()
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": self._prompts.system(settings, recent_swaps, ratings, recent_recipe_names)},
                {"role": "user", "content": self._prompts.plan(MEAL_SLOTS, settings.persons)},
            ],
            response_format={"type": "json_object"},
            temperature=0.95,
        )
        data = json.loads(response.choices[0].message.content)
        meals = [
            Meal(day=m["day"], meal_type=m["meal_type"], recipe=Recipe.model_validate(m["recipe"]))
            for m in data["meals"]
        ]
        await asyncio.gather(*[enrich_nutrition(m.recipe) for m in meals])
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        return WeekPlan(week_start=monday.isoformat(), meals=meals)

    async def generate_single_recipe(
        self,
        settings: Settings,
        recent_swaps: list[dict],
        ratings: dict[str, int] | None = None,
        recent_recipe_names: list[str] | None = None,
    ) -> Recipe:
        client, model = self._client()
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": self._prompts.system(settings, recent_swaps, ratings, recent_recipe_names)},
                {"role": "user", "content": self._prompts.single_recipe(settings.persons)},
            ],
            response_format={"type": "json_object"},
            temperature=0.95,
        )
        recipe = Recipe.model_validate(json.loads(response.choices[0].message.content))
        await enrich_nutrition(recipe)
        return recipe

    async def replace_meal(
        self,
        old_recipe_name: str,
        reason: str,
        day: str,
        meal_type: str,
        settings: Settings,
        recent_swaps: list[dict],
        ratings: dict[str, int] | None = None,
    ) -> Recipe:
        client, model = self._client()
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": self._prompts.system(settings, recent_swaps, ratings)},
                {"role": "user", "content": self._prompts.swap(old_recipe_name, reason, day, meal_type, settings.persons)},
            ],
            response_format={"type": "json_object"},
            temperature=0.95,
        )
        recipe = Recipe.model_validate(json.loads(response.choices[0].message.content))
        await enrich_nutrition(recipe)
        return recipe

    async def chat(
        self,
        message: str,
        settings: Settings,
        current_plan: WeekPlan | None,
        recent_swaps: list[dict],
    ) -> tuple[str, bool]:
        client, model = self._client()
        system = self._prompts.system(settings, recent_swaps)
        if current_plan:
            from .prompt_builder import _DAY_DE, _MEAL_DE
            lines = [f"Aktueller Wochenplan (ab {current_plan.week_start}):"]
            for meal in current_plan.meals:
                lines.append(f"  {_DAY_DE[meal.day]} {_MEAL_DE[meal.meal_type]}: {meal.recipe.name}")
            system += "\n\n" + "\n".join(lines)

        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": self._prompts.chat(message)},
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
        )
        data = json.loads(response.choices[0].message.content)
        return data.get("reply", ""), bool(data.get("wants_plan", False))
