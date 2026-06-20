import json
import os
from pathlib import Path

import aiosqlite

from .models import Meal, Recipe, Settings, WeekPlan

DB_PATH = Path(os.environ.get("DB_PATH", "/data/rezeptplaner.db"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meal_plans (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start DATE    NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS meals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id     INTEGER NOT NULL REFERENCES meal_plans(id),
    day         TEXT    NOT NULL,
    meal_type   TEXT    NOT NULL,
    recipe_json TEXT    NOT NULL,
    confirmed   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS swaps (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    meal_id     INTEGER REFERENCES meals(id),
    recipe_name TEXT    NOT NULL,
    reason      TEXT    NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# Migration: add recipe_name column to existing swaps tables
_MIGRATIONS = [
    "ALTER TABLE swaps ADD COLUMN recipe_name TEXT NOT NULL DEFAULT ''",
]


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(_SCHEMA)
        for migration in _MIGRATIONS:
            try:
                await db.execute(migration)
            except Exception:
                pass  # column already exists
        await db.commit()


# --- Settings ---

async def get_settings() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT key, value FROM settings") as cur:
            rows = await cur.fetchall()
    return {row[0]: json.loads(row[1]) for row in rows}


async def save_settings(settings: Settings) -> None:
    data = settings.model_dump()
    async with aiosqlite.connect(DB_PATH) as db:
        for key, value in data.items():
            await db.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, json.dumps(value)),
            )
        await db.commit()


# --- Meal Plans ---

async def create_plan(week_start: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO meal_plans (week_start) VALUES (?)", (week_start,)
        )
        await db.commit()
        return cur.lastrowid


async def save_meals(plan_id: int, meals: list[Meal]) -> list[int]:
    ids = []
    async with aiosqlite.connect(DB_PATH) as db:
        for meal in meals:
            cur = await db.execute(
                "INSERT INTO meals (plan_id, day, meal_type, recipe_json) VALUES (?, ?, ?, ?)",
                (plan_id, meal.day, meal.meal_type, meal.recipe.model_dump_json()),
            )
            ids.append(cur.lastrowid)
        await db.commit()
    return ids


async def get_current_plan() -> WeekPlan | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, week_start FROM meal_plans ORDER BY created_at DESC LIMIT 1"
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        plan_id, week_start = row

        async with db.execute(
            "SELECT id, day, meal_type, recipe_json, confirmed FROM meals WHERE plan_id = ?",
            (plan_id,),
        ) as cur:
            meal_rows = await cur.fetchall()

    meals = [
        Meal(
            id=r[0],
            day=r[1],
            meal_type=r[2],
            recipe=Recipe.model_validate_json(r[3]),
            confirmed=bool(r[4]),
        )
        for r in meal_rows
    ]
    return WeekPlan(id=plan_id, week_start=week_start, meals=meals)


async def confirm_plan(plan_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE meals SET confirmed = 1 WHERE plan_id = ?", (plan_id,)
        )
        await db.commit()


async def update_meal(meal_id: int, recipe: Recipe) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE meals SET recipe_json = ?, confirmed = 0 WHERE id = ?",
            (recipe.model_dump_json(), meal_id),
        )
        await db.commit()


async def record_swap(meal_id: int, recipe_name: str, reason: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO swaps (meal_id, recipe_name, reason) VALUES (?, ?, ?)",
            (meal_id, recipe_name, reason),
        )
        await db.commit()


async def get_recent_swaps(limit: int = 20) -> list[dict]:
    """Returns swap history — survives plan deletion because recipe_name is stored directly."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT recipe_name, reason, created_at FROM swaps ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
    return [{"recipe": r[0], "reason": r[1], "at": r[2]} for r in rows]


async def delete_current_plan() -> bool:
    """Deletes the current plan and its meals. Swap history is preserved."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM meal_plans ORDER BY created_at DESC LIMIT 1"
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return False
        plan_id = row[0]
        await db.execute("DELETE FROM meals WHERE plan_id = ?", (plan_id,))
        await db.execute("DELETE FROM meal_plans WHERE id = ?", (plan_id,))
        await db.commit()
    return True
