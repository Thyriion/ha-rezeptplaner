import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from .ai_client import test_connection as ai_test_connection
from .database import (
    confirm_plan,
    delete_current_plan,
    get_current_plan,
    get_settings,
    init_db,
    save_settings,
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
from .recipes import PlannerAI
from .service import PlanService
from .shopping import build_shopping_list
from .shopping import push_to_ha as ha_push


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
    data = await get_settings()
    return Settings(**(data or {}))


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
    reply, new_plan = await _service.handle_chat(req.message)
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


@app.delete("/api/plan")
async def delete_plan():
    deleted = await delete_current_plan()
    return {"ok": deleted}


@app.post("/api/plan/swap")
async def swap_meal(req: SwapRequest):
    try:
        meal = await _service.swap_meal(req.meal_id, req.reason)
        return meal
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


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
