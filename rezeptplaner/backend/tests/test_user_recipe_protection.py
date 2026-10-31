import pytest

from ..normalize import normalize_recipe_name
from ..service import PlanService
from .conftest import make_recipe, make_service


@pytest.mark.parametrize("name,expected", [
    ("One-Pot Pasta", "onepotpasta"),
    ("One Pot-Pasta", "onepotpasta"),
    ("Cremiges Kürbis-Risotto", "cremigeskuerbisrisotto"),
    ("SPÄTZLE", "spaetzle"),
    ("Schweinebraten (Bayrisch)", "schweinebratenbayrisch"),
    ("  Pizza Margherita  ", "pizzamargherita"),
])
def test_normalize_recipe_name(name, expected):
    assert normalize_recipe_name(name) == expected


async def _only_user_recipe_service(name: str = "One-Pot Pasta") -> PlanService:
    svc = await make_service(catalog_size=0)
    await svc.create_user_recipe(make_recipe(name, servings=4))
    return svc


@pytest.mark.asyncio
async def test_user_recipes_are_part_of_the_pool():
    svc = await _only_user_recipe_service()
    recipe = await svc.generate_single_recipe()
    assert recipe.name == "One-Pot Pasta"


@pytest.mark.asyncio
async def test_low_rated_user_recipe_is_excluded():
    svc = await _only_user_recipe_service()
    await svc.rate("One-Pot Pasta", 2)
    from ..service import CatalogEmpty
    with pytest.raises(CatalogEmpty):
        await svc.generate_single_recipe()


@pytest.mark.asyncio
async def test_user_recipe_is_used_verbatim_apart_from_scaling():
    svc = await _only_user_recipe_service()
    original = (await svc.list_user_recipes())[0].recipe
    picked = await svc.generate_single_recipe()  # persons default 2, recipe has 4 servings
    assert picked.steps == original.steps
    assert picked.ingredients[0].amount == 100


@pytest.mark.asyncio
async def test_cannot_save_user_recipe_with_duplicate_normalized_name():
    svc = await _only_user_recipe_service()
    with pytest.raises(ValueError):
        await svc.create_user_recipe(make_recipe("One Pot-Pasta"))


@pytest.mark.asyncio
async def test_cannot_update_user_recipe_to_duplicate_normalized_name():
    svc = await _only_user_recipe_service()
    created = (await svc.list_user_recipes())[0]
    await svc.create_user_recipe(make_recipe("Kürbisrisotto"))
    with pytest.raises(ValueError):
        await svc.edit_user_recipe(created.id, make_recipe("Kürbis-Risotto"))
