"""
Unified meal catalog service.

Single source of truth for all catalog access across gpt_service,
daily_decision_engine, and order endpoints. Catalog is loaded once
from mock_catalog.json and cached in memory for the process lifetime.
"""
import json
import os
from typing import List, Optional
from pydantic import BaseModel

CATALOG_PATH = os.path.join(os.path.dirname(__file__), "rag", "mock_catalog.json")

_catalog_cache: Optional[List["MealItem"]] = None


class MealItem(BaseModel):
    id: str
    name: str
    provider: str
    price_eur: float
    calories: int
    protein_g: float
    carbs_g: float
    fat_g: float
    diet_tags: List[str]
    goal_tags: List[str]
    meal_type: str = "any"
    available: bool = True


def _normalize(raw: dict) -> MealItem:
    """Map raw catalog JSON fields to the canonical MealItem shape."""
    return MealItem(
        id=raw["mock_sku"],
        name=raw["meal_name"],
        provider=raw["partner"],
        price_eur=raw["price_eur"],
        calories=raw["calories"],
        protein_g=raw["protein_g"],
        carbs_g=raw["carbs_g"],
        fat_g=raw["fats_g"],
        diet_tags=raw.get("diet_tags", []),
        goal_tags=raw.get("goal_tags", []),
        meal_type=raw.get("meal_type", "any"),
        available=raw.get("available", True),
    )


def _load() -> List[MealItem]:
    global _catalog_cache
    if _catalog_cache is None:
        with open(CATALOG_PATH, "r", encoding="utf-8") as f:
            raw_list = json.load(f)
        _catalog_cache = [_normalize(r) for r in raw_list]
    return _catalog_cache


# ── Public API ────────────────────────────────────────────────────

def get_all_meals() -> List[MealItem]:
    return _load()


def get_meal_by_id(meal_id: str) -> Optional[MealItem]:
    return next((m for m in _load() if m.id == meal_id), None)


def find_meals(
    ernaehrung: str,
    ziel: str,
    day_type: Optional[str] = None,
    limit: int = 0,
) -> List[MealItem]:
    """
    Filter catalog by diet style and goal, optionally sort by day type priority.
    Falls back progressively: diet+goal → goal only → all.
    """
    meals = _load()

    matched = [m for m in meals if ernaehrung in m.diet_tags and ziel in m.goal_tags]
    if len(matched) < 2:
        matched = [m for m in meals if ziel in m.goal_tags]
    if len(matched) < 2:
        matched = list(meals)

    if day_type == "recovery":
        matched = sorted(matched, key=lambda m: m.calories)
    elif day_type == "performance":
        matched = sorted(matched, key=lambda m: m.protein_g, reverse=True)

    return matched[:limit] if limit > 0 else matched


def select_daily_meals(
    ernaehrung: str,
    ziel: str,
    day_type: str,
) -> tuple[MealItem, MealItem]:
    """Return (lunch, dinner) MealItems for the given day type."""
    matched = find_meals(ernaehrung, ziel, day_type=day_type)
    lunch = matched[0]
    dinner = matched[1] if len(matched) > 1 else matched[0]
    return lunch, dinner


def select_weekly_meals(ernaehrung: str, ziel: str, limit: int = 6) -> List[MealItem]:
    """Return up to `limit` meals for the weekly plan prompt and ordering grid."""
    return find_meals(ernaehrung, ziel, limit=limit)


def format_for_prompt(meals: List[MealItem]) -> str:
    """Format meals for injection into the LLM prompt."""
    lines = []
    for m in meals:
        lines.append(
            f"- [{m.id}] {m.name} von {m.provider} | "
            f"{m.calories} kcal | Protein: {m.protein_g}g | "
            f"Carbs: {m.carbs_g}g | Fett: {m.fat_g}g | {m.price_eur} EUR"
        )
    return "\n".join(lines)
