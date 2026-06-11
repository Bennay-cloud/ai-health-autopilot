import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from context_engine import (
    ContextFlag,
    ContextInput,
    HealthContext,
    calculate_health_context,
    _compute_recovery_score,
    _compute_energy_score,
    _compute_stress_score,
    _detect_flags,
    _classify_day,
)


# ── Helpers ───────────────────────────────────────────────────────

def inp(**kwargs) -> ContextInput:
    """Build a ContextInput with sensible defaults, overriding with kwargs."""
    defaults = dict(sleep_hours=7.5, stress_level=4, meetings_count=3)
    defaults.update(kwargs)
    return ContextInput(**defaults)


# ── Recovery Score ────────────────────────────────────────────────

def test_recovery_score_perfect_sleep():
    score = _compute_recovery_score(inp(sleep_hours=8.0, stress_level=1, meetings_count=0,
                                        previous_day_workout_intensity=0))
    assert score == 100


def test_recovery_score_low_sleep_reduces_score():
    high = _compute_recovery_score(inp(sleep_hours=8.0))
    low  = _compute_recovery_score(inp(sleep_hours=4.0))
    assert low < high


def test_recovery_score_heavy_workout_reduces_score():
    no_workout   = _compute_recovery_score(inp(previous_day_workout_intensity=None))
    max_workout  = _compute_recovery_score(inp(previous_day_workout_intensity=10))
    assert max_workout < no_workout


def test_recovery_score_within_range():
    for sleep in [4, 6, 8]:
        for stress in [1, 5, 10]:
            score = _compute_recovery_score(inp(sleep_hours=sleep, stress_level=stress))
            assert 0 <= score <= 100, f"Score {score} out of range for sleep={sleep}, stress={stress}"


# ── Energy Score ──────────────────────────────────────────────────

def test_energy_score_travel_penalty():
    no_travel = _compute_energy_score(inp(travel_today=False))
    travel    = _compute_energy_score(inp(travel_today=True))
    assert travel < no_travel


def test_energy_score_ovulation_bonus():
    ovulation   = _compute_energy_score(inp(cycle_phase="ovulation"))
    menstruation = _compute_energy_score(inp(cycle_phase="menstruation"))
    assert ovulation > menstruation


def test_energy_score_mood_contribution():
    high_mood = _compute_energy_score(inp(mood_level=10))
    low_mood  = _compute_energy_score(inp(mood_level=1))
    assert high_mood > low_mood


def test_energy_score_within_range():
    for mood in [1, 5, 10]:
        score = _compute_energy_score(inp(mood_level=mood))
        assert 0 <= score <= 100


# ── Stress Score ──────────────────────────────────────────────────

def test_stress_score_high_stress_lowers_score():
    low_stress  = _compute_stress_score(inp(stress_level=1))
    high_stress = _compute_stress_score(inp(stress_level=10))
    assert high_stress < low_stress


def test_stress_score_many_meetings_lower_score():
    few  = _compute_stress_score(inp(meetings_count=0))
    many = _compute_stress_score(inp(meetings_count=10))
    assert many < few


def test_stress_score_travel_lowers_score():
    no_travel = _compute_stress_score(inp(travel_today=False))
    travel    = _compute_stress_score(inp(travel_today=True))
    assert travel < no_travel


def test_stress_score_within_range():
    for stress in [1, 5, 10]:
        score = _compute_stress_score(inp(stress_level=stress))
        assert 0 <= score <= 100


# ── Flag Detection ────────────────────────────────────────────────

def test_flag_low_sleep():
    flags = _detect_flags(inp(sleep_hours=5.9))
    assert ContextFlag.LOW_SLEEP.value in flags


def test_flag_low_sleep_not_set_at_boundary():
    flags = _detect_flags(inp(sleep_hours=6.0))
    assert ContextFlag.LOW_SLEEP.value not in flags


def test_flag_high_stress():
    flags = _detect_flags(inp(stress_level=8))
    assert ContextFlag.HIGH_STRESS.value in flags


def test_flag_high_stress_not_set_below_threshold():
    flags = _detect_flags(inp(stress_level=7))
    assert ContextFlag.HIGH_STRESS.value not in flags


def test_flag_travel_day():
    flags = _detect_flags(inp(travel_today=True))
    assert ContextFlag.TRAVEL_DAY.value in flags


def test_flag_menstruation():
    flags = _detect_flags(inp(cycle_phase="menstruation"))
    assert ContextFlag.MENSTRUATION.value in flags
    assert ContextFlag.FOLLICULAR_PHASE.value not in flags


def test_flag_follicular():
    flags = _detect_flags(inp(cycle_phase="follicular"))
    assert ContextFlag.FOLLICULAR_PHASE.value in flags


def test_flag_ovulation():
    flags = _detect_flags(inp(cycle_phase="ovulation"))
    assert ContextFlag.OVULATION.value in flags


def test_flag_luteal():
    flags = _detect_flags(inp(cycle_phase="luteal"))
    assert ContextFlag.LUTEAL_PHASE.value in flags


def test_flag_heavy_training_yesterday():
    flags = _detect_flags(inp(previous_day_workout_intensity=8))
    assert ContextFlag.HEAVY_TRAINING_YESTERDAY.value in flags


def test_flag_heavy_training_not_set_below_threshold():
    flags = _detect_flags(inp(previous_day_workout_intensity=7))
    assert ContextFlag.HEAVY_TRAINING_YESTERDAY.value not in flags


def test_flag_high_meeting_load():
    flags = _detect_flags(inp(meetings_count=7))
    assert ContextFlag.HIGH_MEETING_LOAD.value in flags


def test_flag_low_mood():
    flags = _detect_flags(inp(mood_level=3))
    assert ContextFlag.LOW_MOOD.value in flags


def test_flag_performance_ready_all_green():
    flags = _detect_flags(inp(sleep_hours=8.0, stress_level=4, meetings_count=2))
    assert ContextFlag.PERFORMANCE_READY.value in flags


def test_flag_performance_ready_blocked_by_low_sleep():
    flags = _detect_flags(inp(sleep_hours=5.0, stress_level=3, meetings_count=2))
    assert ContextFlag.PERFORMANCE_READY.value not in flags


def test_flag_performance_ready_blocked_by_high_stress():
    flags = _detect_flags(inp(sleep_hours=8.0, stress_level=9, meetings_count=2))
    assert ContextFlag.PERFORMANCE_READY.value not in flags


def test_flag_performance_ready_at_exact_thresholds():
    # sleep=7, stress=5, meetings=4 → exactly on boundary → performance ready
    flags = _detect_flags(inp(sleep_hours=7.0, stress_level=5, meetings_count=4))
    assert ContextFlag.PERFORMANCE_READY.value in flags


# ── Day Classification ────────────────────────────────────────────

def test_classify_recovery_low_sleep():
    ctx = calculate_health_context(inp(sleep_hours=5.5))
    assert ctx.day_type == "recovery"


def test_classify_recovery_high_stress():
    ctx = calculate_health_context(inp(stress_level=8))
    assert ctx.day_type == "recovery"


def test_classify_recovery_many_meetings():
    ctx = calculate_health_context(inp(meetings_count=7))
    assert ctx.day_type == "recovery"


def test_classify_performance_all_green():
    ctx = calculate_health_context(inp(sleep_hours=8.0, stress_level=3, meetings_count=2))
    assert ctx.day_type == "performance"


def test_classify_normal_moderate_conditions():
    ctx = calculate_health_context(inp(sleep_hours=6.5, stress_level=6, meetings_count=5))
    assert ctx.day_type == "normal"


# ── Cycle Intensity Cap ───────────────────────────────────────────

def test_menstruation_caps_to_recovery():
    # Even with perfect sleep/stress, menstruation must force recovery
    ctx = calculate_health_context(inp(
        sleep_hours=8.0, stress_level=3, meetings_count=2,
        cycle_phase="menstruation",
    ))
    assert ctx.day_type == "recovery"


def test_luteal_caps_to_normal():
    # Perfect conditions + luteal → capped to normal (not performance)
    ctx = calculate_health_context(inp(
        sleep_hours=8.0, stress_level=3, meetings_count=2,
        cycle_phase="luteal",
    ))
    assert ctx.day_type == "normal"


def test_luteal_does_not_promote_from_recovery():
    # Luteal cap is "normal" — but if base is already recovery, stays recovery
    ctx = calculate_health_context(inp(
        sleep_hours=5.0, stress_level=3, meetings_count=2,
        cycle_phase="luteal",
    ))
    assert ctx.day_type == "recovery"


def test_ovulation_allows_performance():
    ctx = calculate_health_context(inp(
        sleep_hours=8.0, stress_level=3, meetings_count=2,
        cycle_phase="ovulation",
    ))
    assert ctx.day_type == "performance"


def test_follicular_allows_performance():
    ctx = calculate_health_context(inp(
        sleep_hours=8.0, stress_level=3, meetings_count=2,
        cycle_phase="follicular",
    ))
    assert ctx.day_type == "performance"


# ── Full calculate_health_context ─────────────────────────────────

def test_health_context_returns_all_fields():
    ctx = calculate_health_context(inp())
    assert isinstance(ctx, HealthContext)
    assert 0 <= ctx.health_score <= 100
    assert 0 <= ctx.recovery_score <= 100
    assert 0 <= ctx.energy_score <= 100
    assert 0 <= ctx.stress_score <= 100
    assert ctx.day_type in ("recovery", "normal", "performance")
    assert isinstance(ctx.context_flags, list)
    assert isinstance(ctx.explanation, str) and len(ctx.explanation) > 0
    assert isinstance(ctx.positive_factors, list)
    assert isinstance(ctx.negative_factors, list)


def test_health_score_is_weighted_composite():
    # health_score = round(0.4*recovery + 0.35*energy + 0.25*stress)
    i = inp(sleep_hours=8.0, stress_level=1, meetings_count=0)
    ctx = calculate_health_context(i)
    expected = round(0.4 * ctx.recovery_score + 0.35 * ctx.energy_score + 0.25 * ctx.stress_score)
    assert ctx.health_score == min(expected, 100)


def test_low_sleep_appears_in_negative_factors():
    ctx = calculate_health_context(inp(sleep_hours=5.0))
    assert any("5.0h" in f or "Schlaf" in f for f in ctx.negative_factors)


def test_high_stress_appears_in_negative_factors():
    ctx = calculate_health_context(inp(stress_level=9))
    assert any("Stress" in f or "9/10" in f for f in ctx.negative_factors)


def test_travel_day_appears_in_negative_factors():
    ctx = calculate_health_context(inp(travel_today=True))
    assert any("Reise" in f for f in ctx.negative_factors)


def test_menstruation_appears_in_negative_factors():
    ctx = calculate_health_context(inp(cycle_phase="menstruation"))
    assert any("Menstruation" in f or "menstruation" in f.lower() for f in ctx.negative_factors)


def test_ovulation_appears_in_positive_factors():
    ctx = calculate_health_context(inp(cycle_phase="ovulation"))
    assert any("Eisprung" in f or "ovulation" in f.lower() for f in ctx.positive_factors)


def test_heavy_workout_yesterday_appears_in_negative_factors():
    ctx = calculate_health_context(inp(previous_day_workout_intensity=9))
    assert any("9/10" in f or "Training" in f for f in ctx.negative_factors)


def test_good_sleep_appears_in_positive_factors():
    ctx = calculate_health_context(inp(sleep_hours=8.5))
    assert any("Schlaf" in f for f in ctx.positive_factors)


def test_context_flags_are_strings():
    ctx = calculate_health_context(inp(sleep_hours=5.0, travel_today=True))
    for flag in ctx.context_flags:
        assert isinstance(flag, str)
    assert "LOW_SLEEP" in ctx.context_flags
    assert "TRAVEL_DAY" in ctx.context_flags
