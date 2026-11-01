import random

from ..models import Settings
from ..selector import Candidate, _prepare_swaps, _swap_factor, pick_recipes


def _cand(i: int, ingredients: str = "nudeln", protein: str = "vegetarisch", **kw) -> Candidate:
    base = dict(key=f"c:{i}", name=f"Rezept {i}", cooking_time=20, protein_type=protein,
                is_vegetarian=protein == "vegetarisch", is_vegan=False, is_spicy=False,
                ingredients_text=ingredients)
    base.update(kw)
    return Candidate(**base)


def _pick(cands, n=3, settings=None, **kw):
    return pick_recipes(cands, n, settings or Settings(), rng=random.Random(1), **kw)


def test_respects_diet_dislikes_and_time():
    cands = [_cand(1, protein="fleisch"), _cand(2, "nudeln, pilze"), _cand(3, cooking_time=50), _cand(4)]
    picks = _pick(cands, settings=Settings(diet_types=["Vegetarisch"], disliked_foods=["Pilze"], max_cooking_time=30))
    assert [c.key for c in picks] == ["c:4"]


def test_excludes_low_rated_and_spicy():
    cands = [_cand(1), _cand(2, is_spicy=True), _cand(3)]
    picks = _pick(cands, ratings={"Rezept 1": 2})
    assert [c.key for c in picks] == ["c:3"]


def test_recent_names_are_dropped_first_then_relaxed():
    cands = [_cand(i) for i in range(1, 5)]
    picks = _pick(cands, n=3, avoid_names=["Rezept 1", "Rezept 2"])
    assert len(picks) == 3  # soft avoid relaxed because only 2 remain
    picks = _pick(cands, n=3, hard_avoid_names=["Rezept 1", "Rezept 2"])
    assert len(picks) == 2  # hard avoid is never relaxed


def test_variety_prefers_different_protein_types():
    cands = [_cand(i, protein="fleisch") for i in range(20)] + [_cand(100 + i) for i in range(20)]
    types = [c.protein_type for c in _pick(cands, n=6)]
    assert 1 <= types.count("fleisch") <= 5


def test_dislike_groups_and_plurals():
    cands = [_cand(1, "champignons | nudeln"), _cand(2, "hähnchenbrust"), _cand(3, "lachsfilet"),
             _cand(4, "tomaten | reis")]
    keys = lambda dislikes: sorted(c.key for c in _pick(cands, n=4, settings=Settings(disliked_foods=dislikes)))
    assert keys(["Pilze"]) == ["c:2", "c:3", "c:4"]
    assert keys(["Fleisch"]) == ["c:1", "c:3", "c:4"]
    assert keys(["Fisch", "Tomaten"]) == ["c:1", "c:2"]


def test_swap_reasons_weight_similar_recipes_down():
    lachs = _cand(1, name="Lachs mit Dill", cooking_time=40)
    other_lachs = _cand(2, name="Heißer Lachs auf Reis", cooking_time=40)
    pasta = _cand(3, name="Pasta Pomodoro", cooking_time=15)
    slow = _cand(4, name="Eintopf", cooking_time=60, protein_type="fleisch")
    by_name = {c.name_key: c for c in (lachs, other_lachs, pasta, slow)}

    mag = [{"recipe": "Lachs mit Dill", "reason": "mag_ich_nicht"}]
    assert _swap_factor(other_lachs, _prepare_swaps(mag, by_name)) < 0.5 and _swap_factor(pasta, _prepare_swaps(mag, by_name)) == 1.0

    aufwendig = [{"recipe": "Lachs mit Dill", "reason": "zu_aufwendig"}]
    assert _swap_factor(slow, _prepare_swaps(aufwendig, by_name)) < 0.5 and _swap_factor(pasta, _prepare_swaps(aufwendig, by_name)) == 1.0

    teuer = [{"recipe": "Lachs mit Dill", "reason": "zu_teuer"}]
    assert _swap_factor(slow, _prepare_swaps(teuer, by_name)) < 1.0 and _swap_factor(pasta, _prepare_swaps(teuer, by_name)) == 1.0


def test_budget_tiers_limit_the_price_range():
    cands = [_cand(i, name=f"Gericht {chr(97 + i)}", price=float(i + 1)) for i in range(9)]  # 1..9 EUR
    prices = lambda budget, n: {c.price for c in _pick(cands, n=n, settings=Settings(budget=budget))}
    assert prices("günstig", 3) == {1.0, 2.0, 3.0}
    assert prices("mittel", 6) == {1.0, 2.0, 3.0, 4.0, 5.0, 6.0}
    assert prices("egal", 9) == {float(i) for i in range(1, 10)}


def test_budget_is_relaxed_when_too_few_recipes_fit():
    cands = [_cand(i, name=f"Gericht {chr(97 + i)}", price=float(i + 1)) for i in range(9)]
    assert len(_pick(cands, n=5, settings=Settings(budget="günstig"))) == 5


def test_budget_tiers_ignore_the_search_narrowing():
    cheap = [_cand(i, name=f"Billig {chr(97 + i)}", price=1.0) for i in range(6)]
    pricey = [_cand(10 + i, name=f"Teuer {chr(97 + i)}", price=10.0) for i in range(3)]
    picks = pick_recipes(cheap + pricey, 3, Settings(budget="günstig"), only=lambda c: c.name.startswith("Teuer"),
                         rng=random.Random(1))
    assert len(picks) == 3  # tiers come from the whole catalog; relaxed because nothing "Teuer" is cheap


def test_near_duplicate_titles_are_never_picked_together():
    cands = [_cand(1, name="Cremige Räucherlachs-Farfalle"), _cand(2, name="Cremige Farfalle mit Räucherlachs"),
             _cand(3, name="Cremiges Thai-Curry"), _cand(4, name="Cremiges Thai-Curry-Risotto"),
             _cand(5, name="Pizza Margherita")]
    for seed in range(20):
        names = [c.name for c in pick_recipes(cands, 5, Settings(), rng=random.Random(seed))]
        assert len(names) == 3
        assert not {"Cremige Räucherlachs-Farfalle", "Cremige Farfalle mit Räucherlachs"} <= set(names)
        assert not {"Cremiges Thai-Curry", "Cremiges Thai-Curry-Risotto"} <= set(names)


def test_variants_of_avoided_recipes_are_blocked():
    cands = [_cand(1, name="Gnocchi in feiner Tomatensoße"), _cand(2, name="Gnocchi in feiner Mascarpone-Tomatensoße"),
             _cand(3, name="Pizza Margherita")]
    names = {c.name for c in pick_recipes(cands, 3, Settings(), hard_avoid_names=["Gnocchi in feiner Tomatensoße"])}
    assert names == {"Pizza Margherita"}
    soft = pick_recipes(cands, 1, Settings(), avoid_names=["Gnocchi in feiner Tomatensoße"], rng=random.Random(0))
    assert soft[0].name == "Pizza Margherita"
