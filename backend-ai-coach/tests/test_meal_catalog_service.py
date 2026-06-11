import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import meal_catalog_service as svc
from meal_catalog_service import MealItem


# ── get_all_meals ─────────────────────────────────────────────────

def test_get_all_meals_returns_list():
    meals = svc.get_all_meals()
    assert isinstance(meals, list)
    assert len(meals) > 0


def test_all_meals_are_meal_items():
    for meal in svc.get_all_meals():
        assert isinstance(meal, MealItem)


def test_catalog_loaded_once(monkeypatch):
    """Cache should mean the JSON file is only opened once."""
    # Force cache reset
    svc._catalog_cache = None
    load_count = {"n": 0}
    original_open = open

    def counting_open(path, *args, **kwargs):
        if str(path).endswith("mock_catalog.json"):
            load_count["n"] += 1
        return original_open(path, *args, **kwargs)

    import builtins
    monkeypatch.setattr(builtins, "open", counting_open)

    svc.get_all_meals()
    svc.get_all_meals()  # second call — should NOT re-open the file
    assert load_count["n"] == 1, "Catalog file should only be read once (cached)"


def test_meals_have_normalized_fields():
    meal = svc.get_all_meals()[0]
    assert hasattr(meal, "id")
    assert hasattr(meal, "name")
    assert hasattr(meal, "provider")
    assert hasattr(meal, "fat_g")       # normalized from fats_g
    assert not hasattr(meal, "mock_sku")   # old field gone
    assert not hasattr(meal, "meal_name")  # old field gone
    assert not hasattr(meal, "partner")    # old field gone
    assert not hasattr(meal, "fats_g")     # old field gone


def test_meal_ids_start_with_mock():
    for meal in svc.get_all_meals():
        assert meal.id.startswith("MOCK-"), f"Unexpected id: {meal.id}"


def test_meal_available_defaults_to_true():
    for meal in svc.get_all_meals():
        assert meal.available is True


# ── get_meal_by_id ────────────────────────────────────────────────

def test_get_meal_by_id_returns_correct_meal():
    meal = svc.get_meal_by_id("MOCK-EVR-001")
    assert meal is not None
    assert meal.id == "MOCK-EVR-001"
    assert meal.name == "Chicken & Sweet Potato Bowl"
    assert meal.provider == "Every. Foods"


def test_get_meal_by_id_returns_none_for_unknown():
    assert svc.get_meal_by_id("DOES-NOT-EXIST") is None


# ── find_meals ────────────────────────────────────────────────────

def test_find_meals_filters_by_diet_and_goal():
    meals = svc.find_meals("Vegan", "Muskelaufbau")
    for m in meals:
        assert "Vegan" in m.diet_tags or "Muskelaufbau" in m.goal_tags


def test_find_meals_recovery_sorts_by_calories_asc():
    meals = svc.find_meals("Mischkost", "Muskelaufbau", day_type="recovery")
    cals = [m.calories for m in meals]
    assert cals == sorted(cals), "Recovery meals should be sorted lowest calories first"


def test_find_meals_performance_sorts_by_protein_desc():
    meals = svc.find_meals("Mischkost", "Muskelaufbau", day_type="performance")
    proteins = [m.protein_g for m in meals]
    assert proteins == sorted(proteins, reverse=True), "Performance meals should be sorted highest protein first"


def test_find_meals_limit_applied():
    meals = svc.find_meals("Mischkost", "Muskelaufbau", limit=3)
    assert len(meals) <= 3


def test_find_meals_fallback_when_diet_no_match():
    # "Omnivore" doesn't exist in diet_tags → falls back to goal-only match
    meals = svc.find_meals("Omnivore", "Muskelaufbau")
    assert len(meals) >= 1
    for m in meals:
        assert "Muskelaufbau" in m.goal_tags


def test_find_meals_fallback_to_all_when_nothing_matches():
    meals = svc.find_meals("NonexistentDiet", "NonexistentGoal")
    assert len(meals) == len(svc.get_all_meals())


# ── select_daily_meals ────────────────────────────────────────────

def test_select_daily_meals_returns_two_meals():
    lunch, dinner = svc.select_daily_meals("Mischkost", "Muskelaufbau", "normal")
    assert isinstance(lunch, MealItem)
    assert isinstance(dinner, MealItem)


def test_select_daily_meals_lunch_differs_from_dinner():
    lunch, dinner = svc.select_daily_meals("Mischkost", "Fettabbau", "recovery")
    assert lunch.id != dinner.id


def test_select_daily_meals_recovery_prefers_lower_calories():
    lunch, _ = svc.select_daily_meals("Mischkost", "Fettabbau", "recovery")
    all_recovery = svc.find_meals("Mischkost", "Fettabbau", day_type="recovery")
    assert lunch.id == all_recovery[0].id


def test_select_daily_meals_performance_prefers_high_protein():
    lunch, _ = svc.select_daily_meals("Mischkost", "Muskelaufbau", "performance")
    all_perf = svc.find_meals("Mischkost", "Muskelaufbau", day_type="performance")
    assert lunch.id == all_perf[0].id


# ── select_weekly_meals ───────────────────────────────────────────

def test_select_weekly_meals_returns_list():
    meals = svc.select_weekly_meals("Vegan", "Gesund bleiben")
    assert isinstance(meals, list)
    assert len(meals) >= 1


def test_select_weekly_meals_default_limit_six():
    meals = svc.select_weekly_meals("Mischkost", "Muskelaufbau")
    assert len(meals) <= 6


def test_select_weekly_meals_custom_limit():
    meals = svc.select_weekly_meals("Mischkost", "Muskelaufbau", limit=3)
    assert len(meals) <= 3


# ── format_for_prompt ─────────────────────────────────────────────

def test_format_for_prompt_contains_meal_ids():
    meals = svc.select_weekly_meals("Mischkost", "Muskelaufbau", limit=2)
    text = svc.format_for_prompt(meals)
    for m in meals:
        assert m.id in text
        assert m.name in text


def test_format_for_prompt_empty_list():
    assert svc.format_for_prompt([]) == ""
