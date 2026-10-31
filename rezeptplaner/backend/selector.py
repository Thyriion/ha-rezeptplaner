"""Rule-based recipe selection from the local catalog — no AI involved."""
import random
import re
from dataclasses import dataclass, field

from .catalog import has_gluten, has_lactose, matches_term
from .models import Settings
from .normalize import normalize_recipe_name

# Penalty applied per already-picked recipe of the same protein type, for variety.
_VARIETY_PENALTY = 0.35
_LOW_CARB_MAX_G = 50
_HIGH_PROTEIN_MIN_G = 30


@dataclass
class Candidate:
    key: str  # "c:<id>" for catalog recipes, "u:<id>" for user recipes
    name: str
    cooking_time: int
    protein_type: str
    is_vegetarian: bool
    is_vegan: bool
    is_spicy: bool
    ingredients_text: str
    protein_g: float = 0.0
    carbs_g: float = 0.0
    devices: list[str] = field(default_factory=list)
    is_user: bool = False

    @property
    def name_key(self) -> str:
        return normalize_recipe_name(self.name)


def _eligible(c: Candidate, settings: Settings, ratings: dict[str, int],
              excluded: set[str], time_factor: float) -> bool:
    if c.name_key in excluded or ratings.get(c.name, 5) < 3:
        return False
    diets = set(settings.diet_types)
    if "Vegan" in diets and not c.is_vegan:
        return False
    if "Vegetarisch" in diets and not c.is_vegetarian:
        return False
    if "Glutenfrei" in diets and has_gluten(c.ingredients_text):
        return False
    if "Laktosefrei" in diets and has_lactose(c.ingredients_text):
        return False
    if "Low Carb" in diets and c.carbs_g > _LOW_CARB_MAX_G:
        return False
    if not settings.likes_spicy and c.is_spicy:
        return False
    if settings.max_cooking_time < 60 and c.cooking_time > settings.max_cooking_time * time_factor:
        return False
    haystack = f"{c.name.lower()} {c.ingredients_text}"
    return not any(matches_term(d, haystack) for d in settings.disliked_foods)


_NAME_TOKEN_RE = re.compile(r"[A-ZÄÖÜ][a-zäöüß]{4,}")
_GENERIC_NAME_TOKENS = {"doppe", "feine", "dazu"}
_MANY_INGREDIENTS = 14


def _name_tokens(name: str) -> set[str]:
    """Noun-ish prefixes of a recipe name ("Lachs", "Pilze" -> "lachs", "pilze")."""
    return {t[:5].lower() for t in _NAME_TOKEN_RE.findall(name)} - _GENERIC_NAME_TOKENS


def _swap_factor(c: Candidate, swaps: list[dict], by_name: dict[str, Candidate]) -> float:
    """Down-weight candidates that resemble recently swapped-out recipes, depending on the reason."""
    factor = 1.0
    c_tokens = _name_tokens(c.name)
    for swap in swaps:
        reason = swap.get("reason")
        old = by_name.get(normalize_recipe_name(swap["recipe"]))
        if reason == "mag_ich_nicht" and c_tokens & _name_tokens(swap["recipe"]):
            factor *= 0.3
        elif reason == "zu_aufwendig" and old and c.cooking_time >= old.cooking_time:
            factor *= 0.4
        elif reason == "zu_teuer":
            if c.protein_type in ("fleisch", "fisch"):
                factor *= 0.6
            if c.ingredients_text.count(" | ") + 1 > _MANY_INGREDIENTS:
                factor *= 0.7
    return max(factor, 0.05)


_PREMIUM_RE = re.compile(
    r"lachs|garnele|scampi|lamm|rind|steak|filet|burrata|parmesan|hummer|thunfisch|forelle|kabeljau|"
    r"avocado|pinienkern|cashew|\bente\b|serrano|prosciutto"
)


def _cost_score(c: Candidate) -> int:
    """Rough price proxy: ingredient count, premium ingredients and protein type."""
    score = c.ingredients_text.count(" | ") + 1
    score += 3 * len(_PREMIUM_RE.findall(c.ingredients_text))
    return score + {"fisch": 4, "fleisch": 2}.get(c.protein_type, 0)


def _budget_factor(c: Candidate, budget: str) -> float:
    cost = _cost_score(c)
    if budget == "günstig":
        factor = max(0.9 ** max(0, cost - 12), 0.1)
        return factor * (1.3 if c.protein_type == "vegetarisch" else 1.0)
    if budget == "mittel":
        return max(0.95 ** max(0, cost - 18), 0.4)
    return 1.0


def _weight(c: Candidate, settings: Settings, ratings: dict[str, int]) -> float:
    weight = _budget_factor(c, settings.budget)
    if ratings.get(c.name, 5) >= 8:
        weight *= 3
    if c.is_user:
        weight *= 2
    haystack = f"{c.name.lower()} {c.ingredients_text}"
    if any(matches_term(f, haystack) for f in settings.favorite_foods):
        weight *= 2
    owned = {d.lower() for d in settings.available_devices}
    if any(d.lower() in owned for d in c.devices):
        weight *= 1.5
    if "High Protein" in settings.diet_types and c.protein_g >= _HIGH_PROTEIN_MIN_G:
        weight *= 2
    return weight


def pick_recipes(
    candidates: list[Candidate],
    count: int,
    settings: Settings,
    ratings: dict[str, int] | None = None,
    avoid_names: list[str] | None = None,
    hard_avoid_names: list[str] | None = None,
    swaps: list[dict] | None = None,
    rng: random.Random | None = None,
) -> list[Candidate]:
    """Weighted random pick of up to `count` distinct recipes.

    `hard_avoid_names` (e.g. the current plan) are always excluded. `swaps` ({recipe, reason}) steer weights by reason. `avoid_names`
    (recent meals, recent swaps) are dropped first when too few candidates remain,
    then the cooking-time limit is relaxed.
    """
    rng = rng or random.Random()
    ratings = ratings or {}
    hard = {normalize_recipe_name(n) for n in (hard_avoid_names or [])}
    soft = {normalize_recipe_name(n) for n in (avoid_names or [])}

    pool: list[Candidate] = []
    for excluded, time_factor in ((hard | soft, 1.0), (hard, 1.0), (hard, 1.5)):
        pool = [c for c in candidates if _eligible(c, settings, ratings, excluded, time_factor)]
        if len({c.name_key for c in pool}) >= count:
            break

    picked: list[Candidate] = []
    type_counts: dict[str, int] = {}
    seen: set[str] = set()
    by_name = {c.name_key: c for c in candidates}
    swaps = swaps or []
    while pool and len(picked) < count:
        weights = [_weight(c, settings, ratings) * _swap_factor(c, swaps, by_name) * _VARIETY_PENALTY ** type_counts.get(c.protein_type, 0)
                   for c in pool]
        choice = rng.choices(pool, weights=weights, k=1)[0]
        pool = [c for c in pool if c.name_key != choice.name_key]
        if choice.name_key in seen:
            continue
        seen.add(choice.name_key)
        picked.append(choice)
        type_counts[choice.protein_type] = type_counts.get(choice.protein_type, 0) + 1
    return picked
