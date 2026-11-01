"""Rule-based recipe selection from the local catalog — no AI involved."""
import math
import random
import re
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

from .catalog import has_gluten, has_lactose, matches_term
from .models import Settings
from .normalize import normalize_recipe_name

# Penalty applied per already-picked recipe of the same protein type, for variety.
_VARIETY_PENALTY = 0.35
_LOW_CARB_MAX_G = 50
_HIGH_PROTEIN_MIN_G = 30


# Titles whose word sets overlap at least this much count as near-duplicates.
_SIMILAR_TITLE = 0.6
_TITLE_WORD_RE = re.compile(r"[a-zäöüß0-9]+")
_TITLE_STOPWORDS = {
    "mit", "und", "dazu", "auf", "der", "die", "das", "von", "dem", "den", "in", "an", "aus", "für",
    "doppelt", "doppeltes", "doppelte", "feine", "feiner", "feinem", "bio",
}


def title_tokens(name: str) -> frozenset[str]:
    """Stemmed content words of a recipe title, for near-duplicate detection."""
    tokens = set()
    for word in _TITLE_WORD_RE.findall(name.lower()):
        if word in _TITLE_STOPWORDS:
            continue
        if len(word) > 5 and word.endswith(("en", "es", "er")):
            word = word[:-2]
        elif len(word) > 4 and word.endswith(("e", "n", "s")):
            word = word[:-1]
        tokens.add(word)
    return frozenset(tokens)


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
    price: float | None = None  # rough EUR per serving
    title_tokens: frozenset[str] = field(init=False, repr=False, default=frozenset())
    name_key: str = field(init=False, repr=False, default="")

    def __post_init__(self) -> None:
        self.title_tokens = title_tokens(self.name)
        self.name_key = normalize_recipe_name(self.name)


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


def _name_tokens(name: str) -> set[str]:
    """Noun-ish prefixes of a recipe name ("Lachs", "Pilze" -> "lachs", "pilze")."""
    return {t[:5].lower() for t in _NAME_TOKEN_RE.findall(name)} - _GENERIC_NAME_TOKENS


def _prepare_swaps(swaps: list[dict], by_name: dict[str, Candidate]) -> list[tuple[str, Candidate | None, set[str]]]:
    """Resolve each swap once: (reason, swapped-out candidate if in the pool, its name tokens)."""
    return [
        (swap.get("reason", ""), by_name.get(normalize_recipe_name(swap["recipe"])), _name_tokens(swap["recipe"]))
        for swap in swaps
    ]


def _swap_factor(c: Candidate, prepared: list[tuple[str, Candidate | None, set[str]]]) -> float:
    """Down-weight candidates that resemble recently swapped-out recipes, depending on the reason."""
    factor = 1.0
    c_tokens = None
    for reason, old, old_tokens in prepared:
        if reason == "mag_ich_nicht":
            c_tokens = _name_tokens(c.name) if c_tokens is None else c_tokens
            if c_tokens & old_tokens:
                factor *= 0.3
        elif reason == "zu_aufwendig" and old and c.cooking_time >= old.cooking_time:
            factor *= 0.4
        elif reason == "zu_teuer":
            if old and old.price is not None and c.price is not None:
                if c.price >= old.price:
                    factor *= 0.4
            elif c.protein_type in ("fleisch", "fisch"):
                factor *= 0.6
    return max(factor, 0.05)


# Share of the catalog (cheapest first) each budget level may draw from.
_BUDGET_QUANTILE = {"günstig": 1 / 3, "mittel": 2 / 3}


def _budget_limit(candidates: list[Candidate], budget: str) -> float | None:
    """Price ceiling (EUR/serving) for the budget level, taken from the catalog's price distribution."""
    share = _BUDGET_QUANTILE.get(budget)
    prices = sorted(c.price for c in candidates if c.price is not None)
    if share is None or not prices:
        return None
    return prices[max(0, math.ceil(len(prices) * share) - 1)]


def _weight(c: Candidate, settings: Settings, ratings: dict[str, int]) -> float:
    weight = 1.0
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


def _similar_indices(index: dict[str, list[int]], candidates: list[Candidate],
                     tokens: frozenset[str]) -> set[int]:
    """Indices of candidates whose title is a near-duplicate of `tokens` (Jaccard >= threshold)."""
    if not tokens:
        return set()
    overlap: Counter = Counter()
    for token in tokens:
        overlap.update(index.get(token, ()))
    return {
        i for i, n in overlap.items()
        if n / (len(tokens) + len(candidates[i].title_tokens) - n) >= _SIMILAR_TITLE
    }


def pick_recipes(
    candidates: list[Candidate],
    count: int,
    settings: Settings,
    ratings: dict[str, int] | None = None,
    avoid_names: list[str] | None = None,
    hard_avoid_names: list[str] | None = None,
    swaps: list[dict] | None = None,
    rng: random.Random | None = None,
    only: Callable[[Candidate], bool] | None = None,
) -> list[Candidate]:
    """Weighted random pick of up to `count` distinct, non-near-duplicate recipes.

    `hard_avoid_names` (e.g. the current plan) and their near-duplicate variants are always
    excluded. `avoid_names` (recent meals, recent swaps) are dropped first when too few
    candidates remain, then the cooking-time limit is relaxed. `swaps` ({recipe, reason})
    steer weights by reason.
    """
    rng = rng or random.Random()
    ratings = ratings or {}
    swaps = swaps or []
    hard = {normalize_recipe_name(n) for n in (hard_avoid_names or [])}
    soft = {normalize_recipe_name(n) for n in (avoid_names or [])}

    index: dict[str, list[int]] = defaultdict(list)
    for i, c in enumerate(candidates):
        for token in c.title_tokens:
            index[token].append(i)

    def similar_to_any(names: list[str] | None) -> set[int]:
        found: set[int] = set()
        for name in names or []:
            found |= _similar_indices(index, candidates, title_tokens(name))
        return found

    hard_similar = similar_to_any(hard_avoid_names)
    all_similar = hard_similar | similar_to_any(avoid_names)

    # Budget tiers are computed on the full catalog, before any `only` narrowing.
    budget_limit = _budget_limit(candidates, settings.budget)

    def affordable(c: Candidate) -> bool:
        return budget_limit is None or c.price is None or c.price <= budget_limit

    # Stages relax constraints in order: recent meals, then the time limit, then the budget.
    pool: list[Candidate] = []
    for excluded, similar, time_factor, budget_ok in (
            (hard | soft, all_similar, 1.0, True), (hard, hard_similar, 1.0, True),
            (hard, hard_similar, 1.5, True), (hard, hard_similar, 1.5, False)):
        pool = [c for i, c in enumerate(candidates)
                if i not in similar and (not budget_ok or affordable(c)) and (only is None or only(c))
                and _eligible(c, settings, ratings, excluded, time_factor)]
        if len({c.name_key for c in pool}) >= count:
            break

    by_name = {c.name_key: c for c in candidates}
    prepared = _prepare_swaps(swaps, by_name)
    base = {c.key: _weight(c, settings, ratings) * _swap_factor(c, prepared) for c in pool}
    pool_index = {c.key: i for i, c in enumerate(candidates)}

    picked: list[Candidate] = []
    type_counts: dict[str, int] = {}
    while pool and len(picked) < count:
        weights = [base[c.key] * _VARIETY_PENALTY ** type_counts.get(c.protein_type, 0) for c in pool]
        choice = rng.choices(pool, weights=weights, k=1)[0]
        picked.append(choice)
        type_counts[choice.protein_type] = type_counts.get(choice.protein_type, 0) + 1
        dupes = _similar_indices(index, candidates, choice.title_tokens) | {pool_index[choice.key]}
        dupes_keys = {candidates[i].key for i in dupes} | {c.key for c in pool if c.name_key == choice.name_key}
        pool = [c for c in pool if c.key not in dupes_keys]
    return picked
