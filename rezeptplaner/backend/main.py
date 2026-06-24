import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from .ai_client import test_connection as ai_test_connection
from .database import init_db
from .ha_client import NoopAdapter, SupervisorAdapter
from .database import (
    delete_user_recipe,
    get_user_recipes,
    save_user_recipe,
    update_user_recipe,
)
from .models import (
    AddRecipeRequest,
    ChatRequest,
    ChatResponse,
    ConnectionTestResponse,
    GeneratePlanRequest,
    Meal,
    PlanMeta,
    RatingRequest,
    Recipe,
    Settings,
    ShoppingList,
    SwapRequest,
    SwapWithRecipeRequest,
    UserRecipe,
    WeekPlan,
)
from .recipes import PlannerAI
from .service import PlanService
from .shopping import build_shopping_list, push_items


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


ingress_path = os.environ.get("INGRESS_PATH", "")
app = FastAPI(root_path=ingress_path, lifespan=lifespan)
_service = PlanService(PlannerAI())


# --- Health ---

@app.get("/api/health")
async def health():
    return {"status": "ok"}


# --- Settings ---

@app.get("/api/settings", response_model=Settings)
async def read_settings():
    return await _service.get_settings()


@app.post("/api/settings", response_model=Settings)
async def write_settings(settings: Settings):
    return await _service.update_settings(settings)


# --- AI Provider Test ---

@app.post("/api/test-connection", response_model=ConnectionTestResponse)
async def test_connection_endpoint():
    success, message = await ai_test_connection()
    return ConnectionTestResponse(success=success, message=message)


# --- Chat ---

@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    reply, new_plan = await _service.handle_chat(req.message)
    return ChatResponse(reply=reply, plan=new_plan)


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
    slot_configs = req.slots if req.slots else None
    reply, new_plan = await _service.generate_plan(slot_configs)
    return ChatResponse(reply=reply, plan=new_plan)


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


@app.post("/api/plan/add-recipe", response_model=Meal)
async def add_recipe_to_plan(req: AddRecipeRequest):
    plan = await _service.get_plan(req.plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan nicht gefunden")
    return await _service.add_recipe_to_plan(req.plan_id, req.day, req.meal_type, req.recipe)


# --- Single Recipe ---

@app.post("/api/recipe/single")
async def get_single_recipe():
    return await _service.generate_single_recipe()


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
    return await build_shopping_list(plan_id)


@app.post("/api/shopping-list/push-to-ha")
async def push_shopping_list_to_ha(plan_id: int | None = None):
    shopping_list = await build_shopping_list(plan_id)
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
    rows = await get_user_recipes()
    return [UserRecipe(id=r["id"], recipe=Recipe.model_validate_json(r["recipe_json"])) for r in rows]


@app.post("/api/user-recipes", response_model=UserRecipe)
async def create_user_recipe(recipe: Recipe):
    new_id = await save_user_recipe(recipe.model_dump_json())
    return UserRecipe(id=new_id, recipe=recipe)


@app.put("/api/user-recipes/{recipe_id}", response_model=UserRecipe)
async def edit_user_recipe(recipe_id: int, recipe: Recipe):
    if not await update_user_recipe(recipe_id, recipe.model_dump_json()):
        raise HTTPException(status_code=404, detail="Rezept nicht gefunden")
    return UserRecipe(id=recipe_id, recipe=recipe)


@app.delete("/api/user-recipes/{recipe_id}")
async def remove_user_recipe(recipe_id: int):
    if not await delete_user_recipe(recipe_id):
        raise HTTPException(status_code=404, detail="Rezept nicht gefunden")
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
