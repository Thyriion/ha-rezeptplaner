from .categories import CATEGORIES
from .models import Settings

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

_REASON_DE = {
    "mag_ich_nicht": "mag ich nicht",
    "zu_teuer": "zu teuer",
    "zu_aufwendig": "zu aufwendig",
    "schon_gegessen": "haben wir letzte Woche schon gegessen",
    "sonstiges": "sonstiger Grund",
}

def _recipe_schema(persons: int) -> str:
    return f"""{{
  "name": "Rezeptname",
  "cooking_time_minutes": 25,
  "servings": {persons},
  "ingredients": [
    {{"name": "Zutat", "name_en": "ingredient in English", "amount": 200, "unit": "g",
     "category": "Fleisch & Fisch"}}
  ],
  "steps": ["Schritt 1", "Schritt 2", "Schritt 3"],
  "nutrition_per_serving": {{
    "calories": 520, "protein_g": 38, "carbs_g": 22, "fat_g": 18
  }}
}}"""


class PromptBuilder:
    """Builds all AI prompt strings. No orchestration — pure string construction."""

    def system(
        self,
        settings: Settings,
        recent_swaps: list[dict],
        ratings: dict[str, int] | None = None,
        recent_recipe_names: list[str] | None = None,
    ) -> str:
        diet = ", ".join(settings.diet_types) or "Standard"
        dislikes = ", ".join(settings.disliked_foods) or "keine"
        favorites = ", ".join(settings.favorite_foods) or "keine Angabe"
        lines = [
            f"Du bist ein freundlicher Kochassistent für einen deutschen Haushalt mit {settings.persons} Personen.",
            f"Ernährungsform: {diet}",
            f"Nicht gemochte Lebensmittel: {dislikes}",
            f"Lieblingsgerichte/-zutaten: {favorites} — diese sollen höchstens 1× pro Woche vorkommen und als Inspiration dienen, nicht zwingend wörtlich umgesetzt werden.",
            f"Maximale Kochzeit pro Mahlzeit: {settings.max_cooking_time} Minuten",
            f"Budget: {settings.budget}",
        ]
        if settings.likes_spicy:
            lines.append(
                "Schärfe-Tipp: Füge bei jedem Rezept als allerletzten Schritt folgenden Hinweis hinzu: "
                "'Schärfe-Tipp: Wer es schärfer mag, kann Chiliflocken, Sriracha oder frische Chili dazugeben.'"
            )
        else:
            lines.append("Scharf: Nein — bitte keine scharfen Gerichte und keine Schärfe-Hinweise.")
        if recent_swaps:
            lines.append("\nZuletzt abgelehnte Gerichte — bitte nicht wiederholen:")
            for s in recent_swaps[:10]:
                lines.append(f"  - {s['recipe']} (Grund: {s['reason']})")
        if recent_recipe_names:
            lines.append("\nIn den letzten Wochen bereits gekocht — bitte weitgehend vermeiden:")
            for name in recent_recipe_names[:20]:
                lines.append(f"  - {name}")
        if ratings:
            excluded = [n for n, s in ratings.items() if s < 3]
            preferred = [n for n, s in ratings.items() if s >= 8]
            if excluded:
                lines.append("\nDiese Gerichte wurden schlecht bewertet und sollen NICHT vorgeschlagen werden:")
                for name in excluded:
                    lines.append(f"  - {name}")
            if preferred:
                lines.append("\nDiese Gerichte wurden sehr gut bewertet — gerne öfter einplanen:")
                for name in preferred:
                    lines.append(f"  - {name}")
        return "\n".join(lines)

    def plan(self, slots: list[tuple[str, str]], persons: int) -> str:
        slot_list = "\n".join(
            f"- {_DAY_DE[day]}, {_MEAL_DE[mtype]}" for day, mtype in slots
        )
        cat_list = ", ".join(CATEGORIES)
        return f"""Erstelle einen Wochenplan mit genau {len(slots)} Mahlzeiten für diese Slots:
{slot_list}

Antworte ausschließlich mit folgendem JSON-Format (kein Text drumherum):
{{
  "meals": [
    {{
      "day": "monday",
      "meal_type": "dinner",
      "recipe": {_recipe_schema(persons)}
    }}
  ]
}}

Regeln:
- "day": monday/tuesday/wednesday/thursday/friday/saturday/sunday
- "meal_type": lunch oder dinner
- "category" bei Zutaten: {cat_list}
- Alle Texte auf Deutsch
- Genau {len(slots)} Einträge entsprechend der Slot-Liste oben
- VIELFALT: Abwechslung bei Fleisch, Fisch, vegetarisch — nicht alles vom gleichen Typ
- Lieblingsgerichte/-zutaten höchstens 1× einbauen und zufällig auf verschiedene Wochentage verteilen
"""

    def single_recipe(self, persons: int) -> str:
        cat_list = ", ".join(CATEGORIES)
        return f"""Schlage ein einzelnes Rezept vor.

Antworte ausschließlich mit einem JSON-Objekt in diesem Format:
{_recipe_schema(persons)}

Regeln:
- "category" bei Zutaten: {cat_list}
- Alle Texte auf Deutsch
- Berücksichtige die Präferenzen aus dem System-Prompt
"""

    def swap(self, old_name: str, reason: str, day: str, meal_type: str, persons: int) -> str:
        reason_de = _REASON_DE.get(reason, reason)
        cat_list = ", ".join(CATEGORIES)
        return f"""Ersetze das Gericht "{old_name}" für {_DAY_DE[day]} ({_MEAL_DE[meal_type]}).
Grund: {reason_de}

Antworte ausschließlich mit einem JSON-Objekt in diesem Format:
{_recipe_schema(persons)}

Regeln:
- Wähle etwas komplett anderes als "{old_name}" — anderer Küchenstil, andere Hauptzutat
- "category" bei Zutaten: {cat_list}
- Beachte die Ernährungsform und die Präferenzen aus dem System-Prompt
- Alle Texte auf Deutsch
- Der "name" darf KEINE Klammern, Ersatz-Hinweise oder Bezüge auf das Originalgericht enthalten — nur der saubere Rezeptname
"""

    def chat(self, message: str) -> str:
        return f"""Nutzernachricht: "{message}"

Antworte mit JSON:
{{
  "reply": "deine freundliche, kurze Antwort auf Deutsch",
  "wants_plan": true oder false (true wenn der Nutzer einen neuen Wochenplan haben möchte)
}}"""
