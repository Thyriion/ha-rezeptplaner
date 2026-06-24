import json
import logging
from datetime import date, timedelta

from .ai_client import get_client
from .config import AppConfig, load
from .models import Meal, Recipe, Settings, WeekPlan
from .nutrition import NutritionClient
from .prompt_builder import MEAL_SLOTS, PromptBuilder

logger = logging.getLogger(__name__)


class PlannerAI:
    def __init__(self, cfg: AppConfig | None = None, nutrition: NutritionClient | None = None) -> None:
        self._cfg = cfg or load()
        self._prompts = PromptBuilder()
        self._nutrition = nutrition or NutritionClient(api_key=self._cfg.usda_api_key)

    def _client(self) -> tuple:
        return get_client(self._cfg)

    async def _enrich(self, recipe: Recipe) -> None:
        nutrition = await self._nutrition.enrich(recipe)
        if nutrition:
            recipe.nutrition_per_serving = nutrition

    async def generate_plan(
        self,
        settings: Settings,
        recent_swaps: list[dict],
        ratings: dict[str, int] | None = None,
        recent_recipe_names: list[str] | None = None,
        slots: list[tuple[str, str]] | None = None,
    ) -> WeekPlan:
        effective_slots = slots if slots is not None else MEAL_SLOTS
        client, model = self._client()
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": self._prompts.system(settings, recent_swaps, ratings, recent_recipe_names)},
                {"role": "user", "content": self._prompts.plan(effective_slots, settings.persons)},
            ],
            response_format={"type": "json_object"},
            temperature=0.95,
        )
        data = json.loads(response.choices[0].message.content)
        meals = [
            Meal(day=m["day"], meal_type=m["meal_type"], recipe=Recipe.model_validate(m["recipe"]))
            for m in data["meals"]
        ]
        for m in meals:
            await self._enrich(m.recipe)
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
        await self._enrich(recipe)
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
        current_recipe_names: list[str] | None = None,
    ) -> Recipe:
        client, model = self._client()
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": self._prompts.system(settings, recent_swaps, ratings)},
                {"role": "user", "content": self._prompts.swap(
                    old_recipe_name, reason, day, meal_type, settings.persons,
                    current_recipe_names=current_recipe_names,
                )},
            ],
            response_format={"type": "json_object"},
            temperature=0.95,
        )
        recipe = Recipe.model_validate(json.loads(response.choices[0].message.content))
        await self._enrich(recipe)
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
