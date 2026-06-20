import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import load_options
from .database import (
    confirm_plan,
    get_current_plan,
    get_settings,
    init_db,
    record_swap,
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
    if not data:
        return Settings()
    return Settings(**data)


@app.post("/api/settings", response_model=Settings)
async def write_settings(settings: Settings):
    await save_settings(settings)
    return settings


# --- AI Provider Test ---

@app.post("/api/test-connection", response_model=ConnectionTestResponse)
async def test_connection():
    # Implemented in Issue #4
    return ConnectionTestResponse(success=False, message="Noch nicht implementiert")


# --- Chat ---

@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    # Implemented in Issue #5
    raise HTTPException(status_code=501, detail="Noch nicht implementiert")


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
    # AI call implemented in Issue #5
    await record_swap(req.meal_id, req.reason)
    raise HTTPException(status_code=501, detail="Noch nicht implementiert")


# --- Shopping List ---

@app.get("/api/shopping-list", response_model=ShoppingList)
async def get_shopping_list():
    # Implemented in Issue #6
    raise HTTPException(status_code=501, detail="Noch nicht implementiert")


@app.post("/api/shopping-list/push-to-ha")
async def push_to_ha():
    # Implemented in Issue #7
    raise HTTPException(status_code=501, detail="Noch nicht implementiert")


# --- Frontend (muss zuletzt stehen) ---

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
