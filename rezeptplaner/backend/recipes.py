import json
import logging
from datetime import date, timedelta

from .ai_client import get_client
from .models import Meal, Recipe, WeekPlan

logger = logging.getLogger(__name__)

# Mo–Fr: Abendessen | Sa–So: Mittag + Abendessen
MEAL_SLOTS = [
    ("monday",    "dinner"),
    ("tuesday",   "dinner"),
    ("wednesday", "dinner"),
    ("thursday",  "dinner"),
    ("friday",    "dinner"),
    ("saturday",  "lunch"),
    ("saturday",  "dinner"),
    ("sunday",    "lunch"),
    ("sunday",    "dinner"),
]

_DAY_DE = {
    "monday": "Montag", "tuesday": "Dienstag", "wednesday": "Mittwoch",
    "thursday": "Donnerstag", "friday": "Freitag",
    "saturday": "Samstag", "sunday": "Sonntag",
}
_MEAL_DE = {"lunch": "Mittagessen", "dinner": "Abendessen"}

INGREDIENT_CATEGORIES = [
    "Gemüse & Obst",
    "Fleisch & Fisch",
    "Milchprodukte & Eier",
    "Getreide & Backwaren",
    "Konserven & Trockenwaren",
    "Gewürze & Öle",
    "Sonstiges",
]

_RECIPE_SCHEMA = """{
  "name": "Rezeptname",
  "cooking_time_minutes": 25,
  "servings": 2,
  "ingredients": [
    {"name": "Zutat", "amount": 200, "unit": "g",
     "category": "Fleisch & Fisch"}
  ],
  "steps": ["Schritt 1", "Schritt 2", "Schritt 3"],
  "nutrition_per_serving": {
    "calories": 520, "protein_g": 38, "carbs_g": 22, "fat_g": 18
  }
}"""


def _build_system_prompt(settings: dict, recent_swaps: list[dict]) -> str:
    diet = ", ".join(settings.get("diet_types", [])) or "Standard"
    dislikes = ", ".join(settings.get("disliked_foods", [])) or "keine"
    favorites = ", ".join(settings.get("favorite_foods", [])) or "keine Angabe"
    time_limit = settings.get("max_cooking_time", 30)
    budget = settings.get("budget", "mittel")
    persons = settings.get("persons", 2)

    lines = [
        f"Du bist ein freundlicher Kochassistent für einen deutschen Haushalt mit {persons} Personen.",
        f"Ernährungsform: {diet}",
        f"Nicht gemochte Lebensmittel: {dislikes}",
        f"Lieblingsgerichte/-zutaten: {favorites}",
        f"Maximale Kochzeit pro Mahlzeit: {time_limit} Minuten",
        f"Budget: {budget}",
    ]
    if recent_swaps:
        lines.append("\nZuletzt abgelehnte Gerichte — bitte nicht wiederholen:")
        for s in recent_swaps[:10]:
            lines.append(f"  - {s['recipe']} (Grund: {s['reason']})")
    return "\n".join(lines)


async def generate_week_plan(settings: dict, recent_swaps: list[dict]) -> WeekPlan:
    client, model = get_client()

    slot_list = "\n".join(
        f"- {_DAY_DE[day]}, {_MEAL_DE[mtype]}" for day, mtype in MEAL_SLOTS
    )
    cat_list = ", ".join(INGREDIENT_CATEGORIES)

    prompt = f"""Erstelle einen Wochenplan mit genau 9 Mahlzeiten für diese Slots:
{slot_list}

Antworte ausschließlich mit folgendem JSON-Format (kein Text drumherum):
{{
  "meals": [
    {{
      "day": "monday",
      "meal_type": "dinner",
      "recipe": {_RECIPE_SCHEMA}
    }}
  ]
}}

Regeln:
- "day": monday/tuesday/wednesday/thursday/friday/saturday/sunday
- "meal_type": lunch oder dinner
- "category" bei Zutaten: {cat_list}
- Alle Texte auf Deutsch
- Genau 9 Einträge entsprechend der Slot-Liste oben
- Lieblingsgerichte gelegentlich einbauen
"""

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _build_system_prompt(settings, recent_swaps)},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.85,
    )

    data = json.loads(response.choices[0].message.content)
    meals = [
        Meal(
            day=m["day"],
            meal_type=m["meal_type"],
            recipe=Recipe.model_validate(m["recipe"]),
        )
        for m in data["meals"]
    ]

    today = date.today()
    monday = today - timedelta(days=today.weekday())
    return WeekPlan(week_start=monday.isoformat(), meals=meals)


async def generate_replacement(
    old_recipe_name: str,
    reason: str,
    day: str,
    meal_type: str,
    settings: dict,
    recent_swaps: list[dict],
) -> Recipe:
    client, model = get_client()

    reason_de = {
        "mag_ich_nicht": "mag ich nicht",
        "zu_teuer": "zu teuer",
        "zu_aufwendig": "zu aufwendig",
        "schon_gegessen": "haben wir letzte Woche schon gegessen",
        "sonstiges": "sonstiger Grund",
    }.get(reason, reason)

    prompt = f"""Ersetze das Gericht "{old_recipe_name}" für {_DAY_DE[day]} ({_MEAL_DE[meal_type]}).
Grund: {reason_de}

Antworte ausschließlich mit einem JSON-Objekt in diesem Format:
{_RECIPE_SCHEMA}

Regeln:
- Wähle etwas komplett anderes als "{old_recipe_name}"
- Beachte die Ernährungsform und die Präferenzen aus dem System-Prompt
- Alle Texte auf Deutsch
"""

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _build_system_prompt(settings, recent_swaps)},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.9,
    )

    data = json.loads(response.choices[0].message.content)
    return Recipe.model_validate(data)


async def chat(
    message: str,
    settings: dict,
    current_plan: WeekPlan | None,
    recent_swaps: list[dict],
) -> tuple[str, bool]:
    """Returns (reply_text, wants_new_plan)."""
    client, model = get_client()

    plan_summary = ""
    if current_plan:
        lines = [f"Aktueller Wochenplan (ab {current_plan.week_start}):"]
        for meal in current_plan.meals:
            lines.append(
                f"  {_DAY_DE[meal.day]} {_MEAL_DE[meal.meal_type]}: {meal.recipe.name}"
            )
        plan_summary = "\n".join(lines)

    system = _build_system_prompt(settings, recent_swaps)
    if plan_summary:
        system += f"\n\n{plan_summary}"

    intent_prompt = f"""Nutzernachricht: "{message}"

Antworte mit JSON:
{{
  "reply": "deine freundliche Antwort auf Deutsch",
  "wants_plan": true oder false (true wenn der Nutzer einen neuen Wochenplan haben möchte)
}}"""

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": intent_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.7,
    )

    data = json.loads(response.choices[0].message.content)
    return data.get("reply", ""), bool(data.get("wants_plan", False))
