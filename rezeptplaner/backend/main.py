import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

logger = logging.getLogger(__name__)
from fastapi.staticfiles import StaticFiles

from .database import DB_PATH, PlanStore
from .ha_client import SupervisorAdapter
from .models import (
    AddRecipeRequest,
    ChatRequest,
    ChatResponse,
    CatalogImportRequest,
    CatalogPage,
    DoubleSlotRequest,
    FillSkippedSlotRequest,
    GeneratePlanRequest,
    Meal,
    PlanMeta,
    RatingRequest,
    Recipe,
    Settings,
    ShoppingList,
    SkippedSlot,
    SkipSlotRequest,
    SwapRequest,
    SwapWithRecipeRequest,
    UndoDoubleRequest,
    UserRecipe,
    WeekPlan,
)
from .devices import PREDEFINED_KITCHEN_DEVICES
from .importer import CatalogImporter
from .service import CatalogEmpty, NoMatchingRecipes, PlanService
from .shopping import build_shopping_list, push_items

_service: PlanService
_importer: CatalogImporter


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _service, _importer
    store = await PlanStore.init(DB_PATH)
    _importer = CatalogImporter(store)
    _service = PlanService(store)
    yield
    await _importer.stop()


ingress_path = os.environ.get("INGRESS_PATH", "")
app = FastAPI(root_path=ingress_path, lifespan=lifespan)


# --- Health ---

@app.get("/api/health")
async def health():
    return {"status": "ok"}


# --- Kitchen Devices ---

@app.get("/api/kitchen-devices")
async def list_kitchen_devices():
    return PREDEFINED_KITCHEN_DEVICES


# --- Settings ---

@app.get("/api/settings", response_model=Settings)
async def read_settings():
    return await _service.get_settings()


@app.post("/api/settings", response_model=Settings)
async def write_settings(settings: Settings):
    return await _service.update_settings(settings)


# --- Recipe Catalog ---

@app.get("/api/catalog/status")
async def catalog_status():
    return {"count": await _service.catalog_count(), "import": _importer.status}


@app.post("/api/catalog/import")
async def start_catalog_import(req: CatalogImportRequest = CatalogImportRequest()):
    started = await _importer.start(limit=req.limit, refresh_images=req.refresh_images)
    return {"started": started, "import": _importer.status}


@app.get("/api/catalog/browse", response_model=CatalogPage)
async def browse_catalog(q: str = "", max_time: int | None = None, max_price: float | None = None,
                         kind: str | None = None, respect_settings: bool = True, sort: str = "neu",
                         limit: int = 20, offset: int = 0):
    return await _service.browse_catalog(
        q=q, max_time=max_time, max_price=max_price, kind=kind, respect_settings=respect_settings,
        sort=sort, limit=min(max(limit, 1), 50), offset=max(offset, 0),
    )


@app.get("/api/catalog/recipe/{catalog_id}", response_model=Recipe)
async def get_catalog_recipe(catalog_id: int):
    try:
        return await _service.get_catalog_recipe(catalog_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/catalog/import/stop")
async def stop_catalog_import():
    await _importer.stop()
    return {"import": _importer.status}


# --- Chat ---

@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    try:
        reply, new_plan, recipe = await _service.handle_chat(req.message)
        return ChatResponse(reply=reply, plan=new_plan, single_recipe=recipe)
    except (CatalogEmpty, NoMatchingRecipes) as e:
        raise HTTPException(status_code=409, detail=str(e))


# --- Week Plans ---

@app.get("/api/plans", response_model=list[PlanMeta])
async def list_plans():
    return await _service.list_plans()


@app.get("/api/plan", response_model=WeekPlan | None)
async def get_plan():
    return await _service.get_plan()


@app.get("/api/plan/{plan_id}", response_model=WeekPlan | None)
async def get_plan_by_id(plan_id: int):
    plan = await _service.get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan nicht gefunden")
    return plan


@app.post("/api/plan/generate", response_model=ChatResponse)
async def generate_plan(req: GeneratePlanRequest = GeneratePlanRequest()):
    try:
        reply, new_plan = await _service.generate_plan()
        return ChatResponse(reply=reply, plan=new_plan)
    except (CatalogEmpty, NoMatchingRecipes) as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.post("/api/plan/skip-slot", response_model=SkippedSlot)
async def skip_slot(req: SkipSlotRequest):
    try:
        return await _service.skip_slot(req.plan_id, req.day, req.meal_type)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/plan/double-slot", response_model=Meal)
async def double_slot(req: DoubleSlotRequest):
    try:
        return await _service.double_slot(req.plan_id, req.day, req.meal_type)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/plan/undo-double")
async def undo_double(req: UndoDoubleRequest):
    try:
        await _service.undo_double(req.leftovers_meal_id)
        return {"ok": True}
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/plan/fill-skipped-slot", response_model=Meal)
async def fill_skipped_slot(req: FillSkippedSlotRequest):
    try:
        return await _service.fill_skipped_slot(
            req.plan_id, req.day, req.meal_type,
            reason=req.reason, recipe_id=req.recipe_id,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (CatalogEmpty, NoMatchingRecipes) as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/plan/confirm")
async def confirm_plan():
    plan = await _service.get_plan()
    if not plan or plan.id is None:
        raise HTTPException(status_code=404, detail="Kein aktiver Wochenplan")
    await _service.confirm_plan(plan.id)
    return {"ok": True}


@app.delete("/api/plan/{plan_id}")
async def delete_plan(plan_id: int):
    deleted = await _service.delete_plan(plan_id)
    return {"ok": deleted}


@app.post("/api/plan/swap")
async def swap_meal(req: SwapRequest):
    try:
        return await _service.swap_meal(req.meal_id, req.reason)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (CatalogEmpty, NoMatchingRecipes) as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.post("/api/plan/add-recipe", response_model=Meal)
async def add_recipe_to_plan(req: AddRecipeRequest):
    plan = await _service.get_plan(req.plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan nicht gefunden")
    return await _service.add_recipe_to_plan(req.plan_id, req.day, req.meal_type, req.recipe)


# --- Single Recipe ---

@app.post("/api/recipe/single")
async def get_single_recipe():
    try:
        return await _service.generate_single_recipe()
    except (CatalogEmpty, NoMatchingRecipes) as e:
        raise HTTPException(status_code=409, detail=str(e))


# --- Ratings ---

@app.post("/api/recipe/rate")
async def rate_recipe(req: RatingRequest):
    if not 1 <= req.score <= 10:
        raise HTTPException(status_code=400, detail="Score muss zwischen 1 und 10 liegen")
    await _service.rate(req.recipe_name, req.score)
    return {"ok": True}


@app.get("/api/recipe/ratings")
async def get_all_ratings():
    return await _service.ratings()


# --- Shopping List ---

@app.get("/api/shopping-list", response_model=ShoppingList)
async def get_shopping_list(plan_id: int | None = None):
    plan = await _service.get_plan(plan_id)
    return build_shopping_list(plan)


@app.post("/api/shopping-list/push-to-ha")
async def push_shopping_list_to_ha(plan_id: int | None = None):
    plan = await _service.get_plan(plan_id)
    shopping_list = build_shopping_list(plan)
    token = os.environ.get("SUPERVISOR_TOKEN", "")
    if not token:
        return {"ok": False, "error": "SUPERVISOR_TOKEN nicht verfügbar — ist 'auth_api: true' in der Add-on Konfiguration gesetzt?"}
    result = await push_items(shopping_list, SupervisorAdapter(token))
    if not result["ok"] and result.get("failed", 0) > 0:
        result["error"] = f"{result['failed']} Artikel konnten nicht hinzugefügt werden. Prüfe die Logs."
    return result


# --- User Recipes ---

@app.get("/api/user-recipes", response_model=list[UserRecipe])
async def list_user_recipes():
    return await _service.list_user_recipes()


@app.post("/api/user-recipes", response_model=UserRecipe)
async def create_user_recipe(recipe: Recipe):
    try:
        return await _service.create_user_recipe(recipe)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.put("/api/user-recipes/{recipe_id}", response_model=UserRecipe)
async def edit_user_recipe(recipe_id: int, recipe: Recipe):
    try:
        return await _service.edit_user_recipe(recipe_id, recipe)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.delete("/api/user-recipes/{recipe_id}")
async def remove_user_recipe(recipe_id: int):
    try:
        await _service.delete_user_recipe(recipe_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"ok": True}


# --- Swap with user recipe ---

@app.post("/api/plan/swap-with-recipe", response_model=Meal)
async def swap_with_recipe(req: SwapWithRecipeRequest):
    try:
        return await _service.swap_meal_with_recipe(req.meal_id, req.recipe_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


# --- Frontend ---

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
