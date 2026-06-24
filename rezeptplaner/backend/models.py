from enum import Enum

from pydantic import BaseModel
from typing import List, Optional


class Settings(BaseModel):
    persons: int = 2
    diet_types: List[str] = []
    disliked_foods: List[str] = []
    favorite_foods: List[str] = []
    max_cooking_time: int = 30
    budget: str = "mittel"
    likes_spicy: bool = False


class Ingredient(BaseModel):
    name: str
    name_en: Optional[str] = None
    amount: float
    unit: str
    category: str


class NutritionInfo(BaseModel):
    calories: int
    protein_g: float
    carbs_g: float
    fat_g: float


class Recipe(BaseModel):
    name: str
    cooking_time_minutes: int
    servings: int
    ingredients: List[Ingredient]
    steps: List[str]
    nutrition_per_serving: NutritionInfo


class Meal(BaseModel):
    id: Optional[int] = None
    day: str
    meal_type: str  # "lunch" | "dinner"
    recipe: Recipe
    confirmed: bool = False
    rating: Optional[int] = None
    is_leftovers: bool = False
    source_recipe_name: Optional[str] = None


class WeekPlan(BaseModel):
    id: Optional[int] = None
    week_start: str
    meals: List[Meal]


class PlanMeta(BaseModel):
    id: int
    week_start: str
    meal_count: int


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    plan: Optional[WeekPlan] = None
    single_recipe: Optional[Recipe] = None


class UserRecipe(BaseModel):
    id: Optional[int] = None
    recipe: Recipe


class SwapRequest(BaseModel):
    meal_id: int
    reason: str


class SwapWithRecipeRequest(BaseModel):
    meal_id: int
    recipe_id: int


class AddRecipeRequest(BaseModel):
    recipe: Recipe
    plan_id: int
    day: str
    meal_type: str


class RatingRequest(BaseModel):
    recipe_name: str
    score: int  # 1–10


class ShoppingItem(BaseModel):
    name: str
    amount: float
    unit: str
    category: str
    checked: bool = False


class ShoppingList(BaseModel):
    items_by_category: dict[str, List[ShoppingItem]]


class ConnectionTestResponse(BaseModel):
    success: bool
    message: str


class SlotMode(str, Enum):
    normal = "normal"
    skip = "skip"
    leftovers = "leftovers"


class SlotConfig(BaseModel):
    day: str
    meal_type: str
    mode: SlotMode = SlotMode.normal


class GeneratePlanRequest(BaseModel):
    slots: List[SlotConfig] = []
