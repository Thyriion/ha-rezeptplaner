import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from .ai_client import test_connection as ai_test_connection
from .database import (
    confirm_plan,
    create_plan,
    get_current_plan,
    get_recent_swaps,
    get_settings,
    init_db,
    record_swap,
    save_meals,
    save_settings,
    update_meal,
)
from .models import (
    ChatRequest,
    ChatResponse,
    ConnectionTestResponse,
    Settings,
    ShoppingList,
    SwapRequest,
    WeekPlan,
)
from .recipes import chat as ai_chat
from .recipes import generate_replacement, generate_week_plan
from .shopping import build_shopping_list
from .shopping import push_to_ha as ha_push


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


ingress_path = os.environ.get("INGRESS_PATH", "")
app = FastAPI(root_path=ingress_path, lifespan=lifespan)


# --- Health ---

@app.get("/api/health")
async def health():
    return {"status": "ok"}


# --- Settings ---

@app.get("/api/settings", response_model=Settings)
async def read_settings():
    data = await get_settings()
    return Settings(**data) if data else Settings()


@app.post("/api/settings", response_model=Settings)
async def write_settings(settings: Settings):
    await save_settings(settings)
    return settings


# --- AI Provider Test ---

@app.post("/api/test-connection", response_model=ConnectionTestResponse)
async def test_connection_endpoint():
    success, message = await ai_test_connection()
    return ConnectionTestResponse(success=success, message=message)


# --- Chat ---

@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    settings = await get_settings()
    recent_swaps = await get_recent_swaps()
    current_plan = await get_current_plan()

    reply, wants_plan = await ai_chat(req.message, settings, current_plan, recent_swaps)

    new_plan: WeekPlan | None = None
    if wants_plan:
        new_plan = await generate_week_plan(settings, recent_swaps)
        plan_id = await create_plan(new_plan.week_start)
        meal_ids = await save_meals(plan_id, new_plan.meals)
        for meal, mid in zip(new_plan.meals, meal_ids):
            meal.id = mid
        new_plan.id = plan_id

    return ChatResponse(reply=reply, plan=new_plan)


# --- Week Plan ---

@app.get("/api/plan", response_model=WeekPlan | None)
async def get_plan():
    return await get_current_plan()


@app.post("/api/plan/confirm")
async def confirm_current_plan():
    plan = await get_current_plan()
    if not plan or plan.id is None:
        raise HTTPException(status_code=404, detail="Kein aktiver Wochenplan")
    await confirm_plan(plan.id)
    return {"ok": True}


@app.post("/api/plan/swap")
async def swap_meal(req: SwapRequest):
    plan = await get_current_plan()
    if not plan:
        raise HTTPException(status_code=404, detail="Kein aktiver Wochenplan")

    meal = next((m for m in plan.meals if m.id == req.meal_id), None)
    if not meal:
        raise HTTPException(status_code=404, detail="Mahlzeit nicht gefunden")

    settings = await get_settings()
    recent_swaps = await get_recent_swaps()

    await record_swap(req.meal_id, req.reason)
    new_recipe = await generate_replacement(
        old_recipe_name=meal.recipe.name,
        reason=req.reason,
        day=meal.day,
        meal_type=meal.meal_type,
        settings=settings,
        recent_swaps=recent_swaps,
    )
    await update_meal(req.meal_id, new_recipe)
    meal.recipe = new_recipe
    return meal


# --- Shopping List ---

@app.get("/api/shopping-list", response_model=ShoppingList)
async def get_shopping_list():
    return await build_shopping_list()


@app.post("/api/shopping-list/push-to-ha")
async def push_shopping_list_to_ha():
    shopping_list = await build_shopping_list()
    return await ha_push(shopping_list)


# --- Frontend (muss zuletzt stehen) ---

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
