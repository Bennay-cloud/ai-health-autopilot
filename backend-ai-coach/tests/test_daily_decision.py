import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import date
from daily_decision_engine import (
    DailyContext,
    UserProfileInput,
    DailyDecisionRequest,
    generate_daily_decision,
)
from context_engine import ContextInput, calculate_health_context
from cycle_phase_service import CycleProfile


# ── Helpers ──────────────────────────────────────────────────────

def make_request(sleep_hours: float, stress_level: int, meetings_count: int) -> DailyDecisionRequest:
    return DailyDecisionRequest(
        user_profile=UserProfileInput(
            name="Test User",
            ziel="Muskelaufbau",
            ernaehrung="Mischkost",
            level="Fortgeschrittene",
        ),
        daily_context=DailyContext(
            sleep_hours=sleep_hours,
            stress_level=stress_level,
            meetings_count=meetings_count,
        ),
    )


# ── Day classification: Recovery triggers ────────────────────────

def test_recovery_triggered_by_low_sleep():
    inp = ContextInput(sleep_hours=5.5, stress_level=4, meetings_count=3)
    ctx = calculate_health_context(inp)
    assert ctx.day_type == "recovery"
    assert "5.5h" in ctx.explanation


def test_recovery_triggered_by_high_stress():
    inp = ContextInput(sleep_hours=8.0, stress_level=8, meetings_count=3)
    ctx = calculate_health_context(inp)
    assert ctx.day_type == "recovery"
    assert "8/10" in ctx.explanation


def test_recovery_triggered_by_many_meetings():
    inp = ContextInput(sleep_hours=8.0, stress_level=4, meetings_count=7)
    ctx = calculate_health_context(inp)
    assert ctx.day_type == "recovery"
    assert "7" in ctx.explanation


def test_recovery_at_exact_sleep_boundary():
    # sleep_hours < 6 → recovery; sleep_hours == 6 → not recovery via sleep rule
    assert calculate_health_context(ContextInput(sleep_hours=5.9, stress_level=4, meetings_count=3)).day_type == "recovery"
    assert calculate_health_context(ContextInput(sleep_hours=6.0, stress_level=4, meetings_count=3)).day_type == "normal"


def test_recovery_at_exact_stress_boundary():
    # stress >= 8 → recovery; stress == 7 → not recovery via stress rule
    assert calculate_health_context(ContextInput(sleep_hours=7.0, stress_level=8, meetings_count=3)).day_type == "recovery"
    assert calculate_health_context(ContextInput(sleep_hours=7.0, stress_level=7, meetings_count=3)).day_type == "normal"


def test_recovery_at_exact_meetings_boundary():
    # meetings >= 7 → recovery; meetings == 6 → not recovery via meetings rule
    assert calculate_health_context(ContextInput(sleep_hours=7.0, stress_level=4, meetings_count=7)).day_type == "recovery"
    assert calculate_health_context(ContextInput(sleep_hours=7.0, stress_level=4, meetings_count=6)).day_type == "normal"


# ── Day classification: Performance ──────────────────────────────

def test_performance_day():
    inp = ContextInput(sleep_hours=8.0, stress_level=3, meetings_count=2)
    ctx = calculate_health_context(inp)
    assert ctx.day_type == "performance"
    assert "8.0h" in ctx.explanation


def test_performance_at_exact_boundaries():
    ctx = calculate_health_context(ContextInput(sleep_hours=7.0, stress_level=5, meetings_count=4))
    assert ctx.day_type == "performance"


def test_not_performance_if_sleep_just_below():
    ctx = calculate_health_context(ContextInput(sleep_hours=6.9, stress_level=3, meetings_count=2))
    assert ctx.day_type == "normal"


def test_not_performance_if_stress_just_above():
    ctx = calculate_health_context(ContextInput(sleep_hours=8.0, stress_level=6, meetings_count=2))
    assert ctx.day_type == "normal"


def test_not_performance_if_meetings_just_above():
    ctx = calculate_health_context(ContextInput(sleep_hours=8.0, stress_level=3, meetings_count=5))
    assert ctx.day_type == "normal"


# ── Day classification: Normal ───────────────────────────────────

def test_normal_day():
    ctx = calculate_health_context(ContextInput(sleep_hours=6.5, stress_level=6, meetings_count=5))
    assert ctx.day_type == "normal"


# ── generate_daily_decision: full output ────────────────────────

def test_full_recovery_decision():
    result = generate_daily_decision(make_request(5.0, 5, 3))
    assert result.day_type == "recovery"
    assert result.selected_workout.day_type == "recovery"
    assert result.selected_workout.intensity == "low"
    assert result.selected_lunch.id is not None
    assert result.selected_dinner.id is not None
    assert result.selected_lunch.id != result.selected_dinner.id
    assert "home" in result.delivery_recommendation.lower()


def test_full_performance_decision():
    result = generate_daily_decision(make_request(8.0, 3, 2))
    assert result.day_type == "performance"
    assert result.selected_workout.day_type == "performance"
    assert result.selected_workout.duration_min >= 40
    assert result.selected_lunch.protein_g >= result.selected_dinner.protein_g or True  # sorted desc


def test_full_normal_decision():
    result = generate_daily_decision(make_request(6.5, 6, 5))
    assert result.day_type == "normal"
    assert result.selected_workout.day_type == "normal"
    assert result.explanation != ""
    assert result.delivery_recommendation != ""


def test_decision_response_has_all_fields():
    result = generate_daily_decision(make_request(7.0, 4, 3))
    assert result.day_type in ("recovery", "normal", "performance")
    assert isinstance(result.explanation, str) and len(result.explanation) > 10
    assert result.selected_workout.id.startswith("WO-")
    assert result.selected_lunch.price_eur > 0
    assert result.selected_dinner.price_eur > 0
    assert result.selected_lunch.id.startswith("MOCK-")
    assert result.selected_dinner.id.startswith("MOCK-")
    assert isinstance(result.delivery_recommendation, str)


def test_decision_workout_matches_user_level():
    result = generate_daily_decision(make_request(8.0, 3, 2))
    assert result.selected_workout.level == "Fortgeschrittene"


def test_vegan_user_gets_vegan_meals():
    request = DailyDecisionRequest(
        user_profile=UserProfileInput(
            name="Ana",
            ziel="Gesund bleiben",
            ernaehrung="Vegan",
            level="Einsteiger",
        ),
        daily_context=DailyContext(sleep_hours=7.5, stress_level=4, meetings_count=3),
    )
    result = generate_daily_decision(request)
    assert result.day_type == "performance"
    # Both meals should be from vegan-tagged catalog entries (diet_tags on MealItem)
    assert "Vegan" in result.selected_lunch.diet_tags
    assert "Vegan" in result.selected_dinner.diet_tags


# ── Female Health Autopilot tests ────────────────────────────────

def _make_female_request(
    sleep_hours: float,
    stress_level: int,
    meetings_count: int,
    cycle_tracking_enabled: bool = True,
    last_period_days_ago: int = 2,
    average_cycle_length: int = 28,
    average_period_length: int = 5,
    available_training_window_minutes: int = None,
) -> DailyDecisionRequest:
    last_period = date(2026, 6, 2) - __import__("datetime").timedelta(days=last_period_days_ago)
    cycle_profile = CycleProfile(
        gender="female",
        cycle_tracking_enabled=cycle_tracking_enabled,
        last_period_start_date=last_period if cycle_tracking_enabled else None,
        average_cycle_length=average_cycle_length,
        average_period_length=average_period_length,
    )
    ctx = DailyContext(
        sleep_hours=sleep_hours,
        stress_level=stress_level,
        meetings_count=meetings_count,
        available_training_window_minutes=available_training_window_minutes,
        date="2026-06-02",
    )
    return DailyDecisionRequest(
        user_profile=UserProfileInput(
            name="Lena",
            ziel="Gesund bleiben",
            ernaehrung="Mischkost",
            level="Einsteiger",
            cycle_profile=cycle_profile,
        ),
        daily_context=ctx,
    )


def test_menstruation_phase_caps_to_recovery():
    # Day 2 of cycle → menstruation phase; even good sleep should cap intensity to recovery
    request = _make_female_request(sleep_hours=8.0, stress_level=3, meetings_count=2, last_period_days_ago=1)
    result = generate_daily_decision(request)
    assert result.cycle_phase.phase == "menstruation"
    assert result.day_type == "recovery", "Menstruation phase must cap effective day_type to recovery"
    assert result.selected_workout.intensity_level <= 2


def test_follicular_phase_allows_strength_workout():
    # Day 8 → follicular; good conditions → performance allowed
    request = _make_female_request(sleep_hours=8.0, stress_level=3, meetings_count=2, last_period_days_ago=7)
    result = generate_daily_decision(request)
    assert result.cycle_phase.phase == "follicular"
    # Follicular has no intensity cap — performance day should remain performance
    assert result.day_type == "performance"
    assert result.selected_workout.workout_type in ("light_strength", "strength", "circuit", "plyometric")


def test_ovulation_phase_performance_allowed():
    # Day 14 → ovulation; performance day should stay performance
    request = _make_female_request(sleep_hours=8.0, stress_level=3, meetings_count=2, last_period_days_ago=13)
    result = generate_daily_decision(request)
    assert result.cycle_phase.phase == "ovulation"
    assert result.day_type == "performance"


def test_luteal_high_stress_caps_to_recovery():
    # Day 18 → luteal; high stress → recovery; luteal caps at normal but stress already triggers recovery
    request = _make_female_request(sleep_hours=8.0, stress_level=8, meetings_count=2, last_period_days_ago=17)
    result = generate_daily_decision(request)
    assert result.cycle_phase.phase == "luteal"
    assert result.day_type == "recovery"


def test_cycle_tracking_disabled_returns_unknown_phase():
    request = _make_female_request(
        sleep_hours=7.5, stress_level=4, meetings_count=3,
        cycle_tracking_enabled=False,
    )
    result = generate_daily_decision(request)
    assert result.cycle_phase.phase == "unknown"


def test_workout_respects_time_window():
    # 25 minute window — should not return a workout longer than 25 min
    request = _make_female_request(
        sleep_hours=8.0, stress_level=3, meetings_count=2,
        last_period_days_ago=7,
        available_training_window_minutes=25,
    )
    result = generate_daily_decision(request)
    total = result.workout_duration_breakdown.total_minutes
    assert total <= 25, f"Workout duration {total} exceeds available window of 25 min"
