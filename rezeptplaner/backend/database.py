import json
import os
import tempfile
import uuid
from pathlib import Path

import aiosqlite

from .catalog import CatalogEntry
from .models import Meal, Recipe, Settings, SkippedSlot, UserRecipe, WeekPlan
from .normalize import normalize_recipe_name
from .selector import Candidate

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
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id            INTEGER NOT NULL REFERENCES meal_plans(id),
    day                TEXT    NOT NULL,
    meal_type          TEXT    NOT NULL,
    recipe_json        TEXT    NOT NULL,
    confirmed          INTEGER NOT NULL DEFAULT 0,
    is_leftovers       INTEGER NOT NULL DEFAULT 0,
    source_recipe_name TEXT,
    source_meal_id     INTEGER,
    portion_multiplier INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS skipped_slots (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id   INTEGER NOT NULL REFERENCES meal_plans(id),
    day       TEXT    NOT NULL,
    meal_type TEXT    NOT NULL
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

CREATE TABLE IF NOT EXISTS catalog_recipes (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    source_url       TEXT    NOT NULL UNIQUE,
    name             TEXT    NOT NULL,
    cooking_time     INTEGER NOT NULL,
    protein_type     TEXT    NOT NULL,
    is_vegetarian    INTEGER NOT NULL,
    is_vegan         INTEGER NOT NULL,
    is_spicy         INTEGER NOT NULL,
    protein_g        REAL    NOT NULL DEFAULT 0,
    carbs_g          REAL    NOT NULL DEFAULT 0,
    devices          TEXT    NOT NULL DEFAULT '[]',
    ingredients_text TEXT    NOT NULL,
    recipe_json      TEXT    NOT NULL,
    imported_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS catalog_skipped (
    source_url TEXT PRIMARY KEY,
    reason     TEXT NOT NULL
);
"""

_MIGRATIONS = [
    "ALTER TABLE swaps ADD COLUMN recipe_name TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE meals ADD COLUMN is_leftovers INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE meals ADD COLUMN source_recipe_name TEXT",
    "ALTER TABLE meals ADD COLUMN source_meal_id INTEGER",
    "ALTER TABLE meals ADD COLUMN portion_multiplier INTEGER NOT NULL DEFAULT 1",
    """CREATE TABLE IF NOT EXISTS skipped_slots (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        plan_id   INTEGER NOT NULL REFERENCES meal_plans(id),
        day       TEXT    NOT NULL,
        meal_type TEXT    NOT NULL
    )""",
]


class PlanStore:
    def __init__(self, db_path: str | Path, uri: bool = False) -> None:
        self._db_path = str(db_path)
        self._uri = uri

    def _conn(self):
        return aiosqlite.connect(self._db_path, uri=self._uri)

    @classmethod
    async def init(cls, db_path: str | Path, uri: bool = False) -> "PlanStore":
        store = cls(db_path, uri=uri)
        async with store._conn() as db:
            await db.executescript(_SCHEMA)
            for migration in _MIGRATIONS:
                try:
                    await db.execute(migration)
                except Exception:
                    pass
            await db.commit()
        return store

    # ── Settings ─────────────────────────────────────────────────────

    async def get_settings(self) -> dict:
        async with self._conn() as db:
            async with db.execute("SELECT key, value FROM settings") as cur:
                rows = await cur.fetchall()
        return {row[0]: json.loads(row[1]) for row in rows}

    async def save_settings(self, settings: Settings) -> None:
        data = settings.model_dump()
        async with self._conn() as db:
            for key, value in data.items():
                await db.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                    (key, json.dumps(value)),
                )
            await db.commit()

    # ── Plans ─────────────────────────────────────────────────────────

    async def get_all_plan_metas(self) -> list[dict]:
        async with self._conn() as db:
            async with db.execute(
                """SELECT mp.id, mp.week_start, COUNT(m.id) as meal_count
                   FROM meal_plans mp
                   LEFT JOIN meals m ON m.plan_id = mp.id
                   GROUP BY mp.id
                   ORDER BY mp.created_at DESC"""
            ) as cur:
                rows = await cur.fetchall()
        return [{"id": r[0], "week_start": r[1], "meal_count": r[2]} for r in rows]

    async def get_plan_by_id(self, plan_id: int) -> WeekPlan | None:
        async with self._conn() as db:
            async with db.execute(
                "SELECT id, week_start FROM meal_plans WHERE id = ?", (plan_id,)
            ) as cur:
                row = await cur.fetchone()
            if not row:
                return None
            async with db.execute(
                "SELECT id, day, meal_type, recipe_json, confirmed, is_leftovers, source_recipe_name, source_meal_id, portion_multiplier FROM meals WHERE plan_id = ?",
                (plan_id,),
            ) as cur:
                meal_rows = await cur.fetchall()
            async with db.execute(
                "SELECT id, day, meal_type FROM skipped_slots WHERE plan_id = ?",
                (plan_id,),
            ) as cur:
                skipped_rows = await cur.fetchall()
        skipped_slots = [SkippedSlot(id=r[0], plan_id=plan_id, day=r[1], meal_type=r[2]) for r in skipped_rows]
        return WeekPlan(id=row[0], week_start=row[1], meals=self._meals_from_rows(meal_rows), skipped_slots=skipped_slots)

    async def get_current_plan(self) -> WeekPlan | None:
        async with self._conn() as db:
            async with db.execute(
                "SELECT id FROM meal_plans ORDER BY created_at DESC LIMIT 1"
            ) as cur:
                row = await cur.fetchone()
        if not row:
            return None
        return await self.get_plan_by_id(row[0])

    async def save_new_plan(self, plan: WeekPlan) -> WeekPlan:
        """Create plan + save all meals and skipped slots in one transaction; returns plan with all IDs assigned."""
        async with self._conn() as db:
            cur = await db.execute(
                "INSERT INTO meal_plans (week_start) VALUES (?)", (plan.week_start,)
            )
            plan_id = cur.lastrowid
            for meal in plan.meals:
                cur = await db.execute(
                    "INSERT INTO meals (plan_id, day, meal_type, recipe_json, is_leftovers, source_recipe_name, source_meal_id, portion_multiplier) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (plan_id, meal.day, meal.meal_type, meal.recipe.model_dump_json(),
                     int(meal.is_leftovers), meal.source_recipe_name, meal.source_meal_id,
                     meal.portion_multiplier),
                )
                meal.id = cur.lastrowid
            for slot in plan.skipped_slots:
                cur = await db.execute(
                    "INSERT INTO skipped_slots (plan_id, day, meal_type) VALUES (?, ?, ?)",
                    (plan_id, slot.day, slot.meal_type),
                )
                slot.id = cur.lastrowid
                slot.plan_id = plan_id
            await db.commit()
        plan.id = plan_id
        return plan

    async def confirm_plan(self, plan_id: int) -> None:
        async with self._conn() as db:
            await db.execute("UPDATE meals SET confirmed = 1 WHERE plan_id = ?", (plan_id,))
            await db.commit()

    async def delete_plan_by_id(self, plan_id: int) -> bool:
        async with self._conn() as db:
            async with db.execute(
                "SELECT id FROM meal_plans WHERE id = ?", (plan_id,)
            ) as cur:
                if not await cur.fetchone():
                    return False
            await db.execute("DELETE FROM meals WHERE plan_id = ?", (plan_id,))
            await db.execute("DELETE FROM skipped_slots WHERE plan_id = ?", (plan_id,))
            await db.execute("DELETE FROM meal_plans WHERE id = ?", (plan_id,))
            await db.commit()
        return True

    async def add_meal_to_plan(self, plan_id: int, meal: Meal) -> Meal:
        async with self._conn() as db:
            cur = await db.execute(
                "INSERT INTO meals (plan_id, day, meal_type, recipe_json, is_leftovers, source_recipe_name, source_meal_id, portion_multiplier) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (plan_id, meal.day, meal.meal_type, meal.recipe.model_dump_json(),
                 int(meal.is_leftovers), meal.source_recipe_name, meal.source_meal_id,
                 meal.portion_multiplier),
            )
            await db.commit()
            meal.id = cur.lastrowid
        return meal

    # ── Meals ─────────────────────────────────────────────────────────

    async def get_meal_by_id(self, meal_id: int) -> Meal | None:
        async with self._conn() as db:
            async with db.execute(
                "SELECT id, day, meal_type, recipe_json, confirmed, is_leftovers, source_recipe_name, source_meal_id, portion_multiplier "
                "FROM meals WHERE id = ?",
                (meal_id,),
            ) as cur:
                row = await cur.fetchone()
        if not row:
            return None
        return Meal(
            id=row[0], day=row[1], meal_type=row[2],
            recipe=Recipe.model_validate_json(row[3]),
            confirmed=bool(row[4]),
            is_leftovers=bool(row[5]),
            source_recipe_name=row[6],
            source_meal_id=row[7],
            portion_multiplier=row[8],
        )

    async def apply_swap(self, meal_id: int, recipe: Recipe, reason: str) -> Meal:
        """Record swap + update meal in one transaction; returns the updated Meal."""
        async with self._conn() as db:
            async with db.execute(
                "SELECT recipe_json FROM meals WHERE id = ?", (meal_id,)
            ) as cur:
                row = await cur.fetchone()
            if not row:
                raise LookupError(f"Mahlzeit {meal_id} nicht gefunden")
            old_name = json.loads(row[0]).get("name", "")
            await db.execute(
                "INSERT INTO swaps (meal_id, recipe_name, reason) VALUES (?, ?, ?)",
                (meal_id, old_name, reason),
            )
            await db.execute(
                "UPDATE meals SET recipe_json = ?, confirmed = 0 WHERE id = ?",
                (recipe.model_dump_json(), meal_id),
            )
            await db.commit()
        return await self.get_meal_by_id(meal_id)

    # ── Skipped slots ─────────────────────────────────────────────────

    async def add_skipped_slot(self, plan_id: int, day: str, meal_type: str) -> SkippedSlot:
        async with self._conn() as db:
            cur = await db.execute(
                "INSERT INTO skipped_slots (plan_id, day, meal_type) VALUES (?, ?, ?)",
                (plan_id, day, meal_type),
            )
            await db.commit()
            return SkippedSlot(id=cur.lastrowid, plan_id=plan_id, day=day, meal_type=meal_type)

    async def remove_skipped_slot(self, plan_id: int, day: str, meal_type: str) -> bool:
        async with self._conn() as db:
            cur = await db.execute(
                "DELETE FROM skipped_slots WHERE plan_id = ? AND day = ? AND meal_type = ?",
                (plan_id, day, meal_type),
            )
            await db.commit()
            return cur.rowcount > 0

    async def remove_skipped_slot_by_id(self, slot_id: int) -> bool:
        async with self._conn() as db:
            cur = await db.execute("DELETE FROM skipped_slots WHERE id = ?", (slot_id,))
            await db.commit()
            return cur.rowcount > 0

    # ── Leftovers / doubling ──────────────────────────────────────────

    async def add_leftovers_meal(self, plan_id: int, day: str, meal_type: str, source_meal: Meal) -> Meal:
        meal = Meal(
            day=day, meal_type=meal_type,
            recipe=source_meal.recipe,
            is_leftovers=True,
            source_recipe_name=source_meal.recipe.name,
            source_meal_id=source_meal.id,
        )
        return await self.add_meal_to_plan(plan_id, meal)

    async def update_meal_portion_multiplier(self, meal_id: int, multiplier: int) -> None:
        async with self._conn() as db:
            await db.execute(
                "UPDATE meals SET portion_multiplier = ? WHERE id = ?",
                (multiplier, meal_id),
            )
            await db.commit()

    async def delete_meal_by_id(self, meal_id: int) -> bool:
        async with self._conn() as db:
            cur = await db.execute("DELETE FROM meals WHERE id = ?", (meal_id,))
            await db.commit()
            return cur.rowcount > 0

    # ── Swap history ──────────────────────────────────────────────────

    async def get_recent_swaps(self, limit: int = 20) -> list[dict]:
        async with self._conn() as db:
            async with db.execute(
                "SELECT recipe_name, reason, created_at FROM swaps ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ) as cur:
                rows = await cur.fetchall()
        return [{"recipe": r[0], "reason": r[1], "at": r[2]} for r in rows]

    # ── Ratings ───────────────────────────────────────────────────────

    async def save_rating(self, recipe_name: str, score: int) -> None:
        async with self._conn() as db:
            await db.execute(
                """INSERT INTO ratings (recipe_name, score, updated_at)
                   VALUES (?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(recipe_name) DO UPDATE
                   SET score = excluded.score, updated_at = CURRENT_TIMESTAMP""",
                (recipe_name, score),
            )
            await db.commit()

    async def get_ratings(self) -> dict[str, int]:
        async with self._conn() as db:
            async with db.execute("SELECT recipe_name, score FROM ratings") as cur:
                rows = await cur.fetchall()
        return {r[0]: r[1] for r in rows}

    async def get_recent_recipe_names(self, limit: int = 30) -> list[str]:
        async with self._conn() as db:
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

    # ── User Recipes ──────────────────────────────────────────────────

    async def _user_recipe_name_exists(
        self, normalized_name: str, exclude_id: int | None = None
    ) -> bool:
        async with self._conn() as db:
            if exclude_id is not None:
                async with db.execute(
                    "SELECT id, recipe_json FROM user_recipes WHERE id != ?", (exclude_id,)
                ) as cur:
                    rows = await cur.fetchall()
            else:
                async with db.execute(
                    "SELECT id, recipe_json FROM user_recipes"
                ) as cur:
                    rows = await cur.fetchall()
        for row in rows:
            existing = Recipe.model_validate_json(row[1])
            if normalize_recipe_name(existing.name) == normalized_name:
                return True
        return False

    async def get_user_recipes(self) -> list[UserRecipe]:
        async with self._conn() as db:
            async with db.execute(
                "SELECT id, recipe_json FROM user_recipes ORDER BY created_at DESC"
            ) as cur:
                rows = await cur.fetchall()
        return [UserRecipe(id=r[0], recipe=Recipe.model_validate_json(r[1])) for r in rows]

    async def get_user_recipe_by_id(self, recipe_id: int) -> UserRecipe | None:
        async with self._conn() as db:
            async with db.execute(
                "SELECT id, recipe_json FROM user_recipes WHERE id = ?", (recipe_id,)
            ) as cur:
                row = await cur.fetchone()
        if not row:
            return None
        return UserRecipe(id=row[0], recipe=Recipe.model_validate_json(row[1]))

    async def save_user_recipe(self, recipe: Recipe) -> UserRecipe:
        normalized = normalize_recipe_name(recipe.name)
        if normalized and await self._user_recipe_name_exists(normalized):
            raise ValueError(f"Ein eigenes Rezept mit dem Namen '{recipe.name}' existiert bereits.")
        async with self._conn() as db:
            cur = await db.execute(
                "INSERT INTO user_recipes (recipe_json) VALUES (?)", (recipe.model_dump_json(),)
            )
            await db.commit()
        return UserRecipe(id=cur.lastrowid, recipe=recipe)

    async def update_user_recipe(self, recipe_id: int, recipe: Recipe) -> UserRecipe | None:
        async with self._conn() as db:
            async with db.execute(
                "SELECT id FROM user_recipes WHERE id = ?", (recipe_id,)
            ) as cur:
                if not await cur.fetchone():
                    return None
        normalized = normalize_recipe_name(recipe.name)
        if normalized and await self._user_recipe_name_exists(normalized, exclude_id=recipe_id):
            raise ValueError(f"Ein eigenes Rezept mit dem Namen '{recipe.name}' existiert bereits.")
        async with self._conn() as db:
            await db.execute(
                "UPDATE user_recipes SET recipe_json = ? WHERE id = ?",
                (recipe.model_dump_json(), recipe_id),
            )
            await db.commit()
        return UserRecipe(id=recipe_id, recipe=recipe)

    async def delete_user_recipe(self, recipe_id: int) -> bool:
        async with self._conn() as db:
            async with db.execute(
                "SELECT id FROM user_recipes WHERE id = ?", (recipe_id,)
            ) as cur:
                if not await cur.fetchone():
                    return False
            await db.execute("DELETE FROM user_recipes WHERE id = ?", (recipe_id,))
            await db.commit()
        return True

    # ── Recipe catalog ────────────────────────────────────────────────

    async def catalog_count(self) -> int:
        async with self._conn() as db:
            async with db.execute("SELECT COUNT(*) FROM catalog_recipes") as cur:
                return (await cur.fetchone())[0]

    async def catalog_known_urls(self) -> set[str]:
        async with self._conn() as db:
            async with db.execute(
                "SELECT source_url FROM catalog_recipes UNION SELECT source_url FROM catalog_skipped"
            ) as cur:
                return {r[0] for r in await cur.fetchall()}

    async def catalog_add(self, entry: CatalogEntry) -> None:
        r = entry.recipe
        async with self._conn() as db:
            await db.execute(
                """INSERT OR IGNORE INTO catalog_recipes
                   (source_url, name, cooking_time, protein_type, is_vegetarian, is_vegan, is_spicy,
                    protein_g, carbs_g, devices, ingredients_text, recipe_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (entry.source_url, r.name, r.cooking_time_minutes, entry.protein_type,
                 int(entry.is_vegetarian), int(entry.is_vegan), int(entry.is_spicy),
                 r.nutrition_per_serving.protein_g, r.nutrition_per_serving.carbs_g,
                 json.dumps(r.suggested_devices), entry.ingredients_text, r.model_dump_json()),
            )
            await db.commit()

    async def catalog_mark_skipped(self, source_url: str, reason: str) -> None:
        async with self._conn() as db:
            await db.execute(
                "INSERT OR REPLACE INTO catalog_skipped (source_url, reason) VALUES (?, ?)",
                (source_url, reason),
            )
            await db.commit()

    async def catalog_candidates(self) -> list[Candidate]:
        """Lightweight rows for selection; full recipes are loaded only for the picks."""
        async with self._conn() as db:
            async with db.execute(
                """SELECT id, name, cooking_time, protein_type, is_vegetarian, is_vegan, is_spicy,
                          protein_g, carbs_g, devices, ingredients_text FROM catalog_recipes"""
            ) as cur:
                rows = await cur.fetchall()
        return [
            Candidate(
                key=f"c:{r[0]}", name=r[1], cooking_time=r[2], protein_type=r[3],
                is_vegetarian=bool(r[4]), is_vegan=bool(r[5]), is_spicy=bool(r[6]),
                protein_g=r[7], carbs_g=r[8], devices=json.loads(r[9]), ingredients_text=r[10],
            )
            for r in rows
        ]

    async def catalog_get_recipes(self, ids: list[int]) -> dict[int, Recipe]:
        if not ids:
            return {}
        marks = ",".join("?" * len(ids))
        async with self._conn() as db:
            async with db.execute(
                f"SELECT id, recipe_json FROM catalog_recipes WHERE id IN ({marks})", ids
            ) as cur:
                rows = await cur.fetchall()
        return {r[0]: Recipe.model_validate_json(r[1]) for r in rows}

    # ── Private ───────────────────────────────────────────────────────

    @staticmethod
    def _meals_from_rows(rows) -> list[Meal]:
        return [
            Meal(
                id=r[0], day=r[1], meal_type=r[2],
                recipe=Recipe.model_validate_json(r[3]),
                confirmed=bool(r[4]),
                is_leftovers=bool(r[5]),
                source_recipe_name=r[6],
                source_meal_id=r[7],
                portion_multiplier=r[8],
            )
            for r in rows
        ]


class MemoryPlanStore(PlanStore):
    """File-backed SQLite store for tests. Each instance gets its own isolated
    temp file so multiple aiosqlite connections within one test all share the
    same database while remaining isolated from other test instances."""

    @classmethod
    async def init(cls, db_path: str | Path = "", uri: bool = False) -> "MemoryPlanStore":  # type: ignore[override]
        fd, tmp_path = tempfile.mkstemp(suffix=f"_{uuid.uuid4().hex}.db")
        os.close(fd)
        return await super().init(tmp_path)  # type: ignore[return-value]
