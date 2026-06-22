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

CREATE TABLE IF NOT EXISTS ratings (
    recipe_name TEXT    PRIMARY KEY,
    score       INTEGER NOT NULL DEFAULT 5,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_recipes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_json TEXT    NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

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
                pass
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


async def get_all_plan_metas() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT mp.id, mp.week_start, COUNT(m.id) as meal_count
               FROM meal_plans mp
               LEFT JOIN meals m ON m.plan_id = mp.id
               GROUP BY mp.id
               ORDER BY mp.created_at DESC"""
        ) as cur:
            rows = await cur.fetchall()
    return [{"id": r[0], "week_start": r[1], "meal_count": r[2]} for r in rows]


def _meals_from_rows(meal_rows) -> list[Meal]:
    return [
        Meal(
            id=r[0],
            day=r[1],
            meal_type=r[2],
            recipe=Recipe.model_validate_json(r[3]),
            confirmed=bool(r[4]),
        )
        for r in meal_rows
    ]


async def get_plan_by_id(plan_id: int) -> WeekPlan | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, week_start FROM meal_plans WHERE id = ?", (plan_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        async with db.execute(
            "SELECT id, day, meal_type, recipe_json, confirmed FROM meals WHERE plan_id = ?",
            (plan_id,),
        ) as cur:
            meal_rows = await cur.fetchall()
    return WeekPlan(id=row[0], week_start=row[1], meals=_meals_from_rows(meal_rows))


async def get_current_plan() -> WeekPlan | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM meal_plans ORDER BY created_at DESC LIMIT 1"
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    return await get_plan_by_id(row[0])


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


async def add_meal_to_plan(plan_id: int, meal: Meal) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO meals (plan_id, day, meal_type, recipe_json) VALUES (?, ?, ?, ?)",
            (plan_id, meal.day, meal.meal_type, meal.recipe.model_dump_json()),
        )
        await db.commit()
        return cur.lastrowid


async def confirm_plan(plan_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE meals SET confirmed = 1 WHERE plan_id = ?", (plan_id,)
        )
        await db.commit()


async def get_meal_by_id(meal_id: int) -> Meal | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, day, meal_type, recipe_json, confirmed FROM meals WHERE id = ?",
            (meal_id,),
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    return Meal(
        id=row[0], day=row[1], meal_type=row[2],
        recipe=Recipe.model_validate_json(row[3]),
        confirmed=bool(row[4]),
    )


async def update_meal(meal_id: int, recipe: Recipe) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE meals SET recipe_json = ?, confirmed = 0 WHERE id = ?",
            (recipe.model_dump_json(), meal_id),
        )
        await db.commit()


async def delete_plan_by_id(plan_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM meal_plans WHERE id = ?", (plan_id,)
        ) as cur:
            if not await cur.fetchone():
                return False
        await db.execute("DELETE FROM meals WHERE plan_id = ?", (plan_id,))
        await db.execute("DELETE FROM meal_plans WHERE id = ?", (plan_id,))
        await db.commit()
    return True


async def delete_current_plan() -> bool:
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


# --- Swaps ---

async def record_swap(meal_id: int, recipe_name: str, reason: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO swaps (meal_id, recipe_name, reason) VALUES (?, ?, ?)",
            (meal_id, recipe_name, reason),
        )
        await db.commit()


async def get_recent_swaps(limit: int = 20) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT recipe_name, reason, created_at FROM swaps ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
    return [{"recipe": r[0], "reason": r[1], "at": r[2]} for r in rows]


# --- Ratings ---

async def save_rating(recipe_name: str, score: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO ratings (recipe_name, score, updated_at)
               VALUES (?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(recipe_name) DO UPDATE SET score = excluded.score, updated_at = CURRENT_TIMESTAMP""",
            (recipe_name, score),
        )
        await db.commit()


async def get_ratings() -> dict[str, int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT recipe_name, score FROM ratings") as cur:
            rows = await cur.fetchall()
    return {r[0]: r[1] for r in rows}


# --- Recent recipe names for diversity ---

# --- User Recipes ---

async def get_user_recipes() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, recipe_json FROM user_recipes ORDER BY created_at DESC"
        ) as cur:
            rows = await cur.fetchall()
    return [{"id": r[0], "recipe_json": r[1]} for r in rows]


async def get_user_recipe_by_id(recipe_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, recipe_json FROM user_recipes WHERE id = ?", (recipe_id,)
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    return {"id": row[0], "recipe_json": row[1]}


async def save_user_recipe(recipe_json: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO user_recipes (recipe_json) VALUES (?)", (recipe_json,)
        )
        await db.commit()
        return cur.lastrowid


async def delete_user_recipe(recipe_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM user_recipes WHERE id = ?", (recipe_id,)
        ) as cur:
            if not await cur.fetchone():
                return False
        await db.execute("DELETE FROM user_recipes WHERE id = ?", (recipe_id,))
        await db.commit()
    return True


async def get_recent_recipe_names(limit: int = 30) -> list[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT DISTINCT json_extract(m.recipe_json, '$.name')
               FROM meals m
               JOIN meal_plans mp ON m.plan_id = mp.id
               ORDER BY mp.created_at DESC
               LIMIT ?""",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
    return [r[0] for r in rows if r[0]]
