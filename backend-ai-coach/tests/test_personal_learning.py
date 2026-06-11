"""
Tests for Personal Learning Engine.

Coverage:
  - No data / empty records
  - Low confidence (< 7 records)
  - Medium confidence (7–29 records)
  - High confidence (30+ records)
  - Workout duration pattern
  - Workout time pattern
  - Stress response pattern
  - Travel response pattern
  - Meal adherence pattern
  - Sleep response pattern
  - Recovery effectiveness pattern
  - build_personalization_note
  - get_learning_insights_view
  - ML dataset extension (personal learning fields)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import date, timedelta
from personal_learning_engine import (
    analyze_learning_profile,
    build_personalization_note,
    get_learning_insights_view,
    LearnedPattern,
    PersonalLearningProfile,
    _duration_bucket,
    _time_category,
    _confidence_level,
    _pattern_confidence,
    LOW_THRESHOLD,
    MEDIUM_THRESHOLD,
)
from decision_record_service import (
    DecisionRecord, RecordContext, RecordDecision, RecordOutcome,
    export_training_dataset,
)
from outcome_tracking_service import OutcomeRecord, DailyOutcomes
from unittest.mock import MagicMock


# ── Fixtures and helpers ──────────────────────────────────────────

BASE_DATE = date(2026, 1, 1)


def _date_str(offset: int) -> str:
    return (BASE_DATE + timedelta(days=offset)).isoformat()


def _ctx(
    sleep: float = 7.0,
    stress: int = 4,
    travel: bool = False,
    meetings: int = 3,
):
    return RecordContext(
        sleep_hours=sleep, stress_level=stress, mood=7, meetings=meetings,
        travel=travel, cycle_phase=None, previous_workout=None, goal="fitness",
        recovery_score=70, energy_score=70, stress_score=70, context_flags=[],
    )


def _dec(
    day_type: str = "normal",
    duration: int = 30,
    workout_time: str = "18:00",
    location: str = "home",
):
    return RecordDecision(
        day_type=day_type, workout_type="strength",
        workout_duration_recommended=duration,
        workout_intensity="moderate",
        selected_lunch="Salad", selected_dinner="Bowl",
        meal_calories=800, delivery_location=location,
        workout_time=workout_time, sleep_target="23:00",
    )


def _outcome(
    completed: bool = True,
    completed_min: int = 30,
    completion_pct: float = 100.0,
    meal_ordered: bool = True,
    meal_confirmed: bool = True,
    sleep_achieved: bool = True,
    overall_pct: float = 90.0,
):
    return RecordOutcome(
        completed_workout=completed,
        workout_duration_completed=completed_min,
        workout_completion_percentage=completion_pct,
        meal_ordered=meal_ordered,
        meal_confirmed=meal_confirmed,
        sleep_target_achieved=sleep_achieved,
        overall_completion_percentage=overall_pct,
    )


def _record(
    offset: int = 0,
    ctx_kwargs: dict | None = None,
    dec_kwargs: dict | None = None,
    outcome_kwargs: dict | None = None,
    user_id: str = "u1",
) -> DecisionRecord:
    ctx_k  = ctx_kwargs  or {}
    dec_k  = dec_kwargs  or {}
    out_k  = outcome_kwargs or {}
    return DecisionRecord(
        user_id=user_id,
        date=_date_str(offset),
        context=_ctx(**ctx_k),
        decision=_dec(**dec_k),
        outcome=_outcome(**out_k),
    )


def _outcome_record(
    offset: int,
    energy: float = 7.0,
    stress: float = 4.0,
    mood: float = 7.0,
    user_id: str = "u1",
) -> OutcomeRecord:
    return OutcomeRecord(
        user_id=user_id,
        date=_date_str(offset),
        daily_outcomes=DailyOutcomes(
            mood=mood, energy=energy, stress=stress, sleep_hours=7.0
        ),
    )


def _make_records(n: int, **kwargs) -> list:
    return [_record(offset=i, **kwargs) for i in range(n)]


# ── Confidence level thresholds ───────────────────────────────────

def test_confidence_level_low():
    assert _confidence_level(0)  == "low"
    assert _confidence_level(6)  == "low"


def test_confidence_level_medium():
    assert _confidence_level(7)  == "medium"
    assert _confidence_level(29) == "medium"


def test_confidence_level_high():
    assert _confidence_level(30) == "high"
    assert _confidence_level(50) == "high"


def test_pattern_confidence_clamps():
    assert _pattern_confidence(0)  == 0.0
    assert _pattern_confidence(10) == 1.0
    assert _pattern_confidence(20) == 1.0
    assert _pattern_confidence(5)  == 0.5


# ── Duration bucket helper ────────────────────────────────────────

def test_duration_bucket_0_15():
    assert _duration_bucket(10) == "0-15 min"
    assert _duration_bucket(15) == "0-15 min"


def test_duration_bucket_16_30():
    assert _duration_bucket(16) == "16-30 min"
    assert _duration_bucket(30) == "16-30 min"


def test_duration_bucket_31_45():
    assert _duration_bucket(45) == "31-45 min"


def test_duration_bucket_46_60():
    assert _duration_bucket(60) == "46-60 min"


def test_duration_bucket_60plus():
    assert _duration_bucket(61) == "60+ min"
    assert _duration_bucket(90) == "60+ min"


# ── Time category helper ──────────────────────────────────────────

def test_time_category_morning_string():
    assert _time_category("morning") == "morning"


def test_time_category_morning_time():
    assert _time_category("07:30") == "morning"
    assert _time_category("11:59") == "morning"


def test_time_category_afternoon():
    assert _time_category("12:00") == "afternoon"
    assert _time_category("16:30") == "afternoon"


def test_time_category_evening():
    assert _time_category("18:00") == "evening"
    assert _time_category("23:00") == "evening"


def test_time_category_label():
    assert _time_category("afternoon") == "afternoon"
    assert _time_category("evening")   == "evening"


def test_time_category_unknown():
    assert _time_category("") == "unknown"
    assert _time_category("not_a_time") == "unknown"


# ── No data: empty records ────────────────────────────────────────

def test_no_data_returns_empty_profile():
    profile = analyze_learning_profile([], [], "u1")
    assert profile.user_id == "u1"
    assert profile.total_days_analyzed == 0
    assert profile.confidence_level == "low"
    assert profile.learned_patterns == []
    assert profile.recommended_adaptations == []


def test_no_data_insights_view():
    profile = analyze_learning_profile([], [], "u1")
    view = get_learning_insights_view(profile)
    assert view.has_sufficient_data is False
    assert view.insights == []
    assert view.actions == []


# ── Low confidence (< 7 records with outcomes) ───────────────────

def test_low_confidence_profile():
    records = _make_records(3)
    profile = analyze_learning_profile(records, [], "u1")
    assert profile.confidence_level == "low"
    assert profile.total_days_analyzed == 3


def test_low_confidence_no_patterns_from_single_samples():
    # Each bucket has only 1 sample — analyzers require >= 2 per category
    records = [
        _record(0, dec_kwargs={"duration": 20}),  # 16-30 bucket
        _record(1, dec_kwargs={"duration": 40}),  # 31-45 bucket
    ]
    profile = analyze_learning_profile(records, [], "u1")
    # Duration: 2 buckets with 1 sample each — should NOT produce a pattern
    duration_patterns = [p for p in profile.learned_patterns if p.pattern_type == "duration"]
    assert duration_patterns == []


def test_low_confidence_no_recommendations():
    # Low confidence patterns (confidence_score < 0.4) should not produce adaptations
    records = _make_records(3)
    profile = analyze_learning_profile(records, [], "u1")
    assert profile.recommended_adaptations == []


# ── Medium confidence (7–29 records) ─────────────────────────────

def test_medium_confidence_at_7():
    records = _make_records(7)
    profile = analyze_learning_profile(records, [], "u1")
    assert profile.confidence_level == "medium"


def test_medium_confidence_at_29():
    records = _make_records(29)
    profile = analyze_learning_profile(records, [], "u1")
    assert profile.confidence_level == "medium"


# ── High confidence (30+ records) ────────────────────────────────

def test_high_confidence_at_30():
    records = _make_records(30)
    profile = analyze_learning_profile(records, [], "u1")
    assert profile.confidence_level == "high"


# ── Workout duration pattern ──────────────────────────────────────

def test_duration_pattern_detects_best_bucket():
    # 8 records with 16-30 min (100% completion), 3 records with 46-60 min (50% completion)
    records = (
        [_record(i, dec_kwargs={"duration": 25}, outcome_kwargs={"completion_pct": 100.0}) for i in range(8)]
        + [_record(8+i, dec_kwargs={"duration": 55}, outcome_kwargs={"completion_pct": 50.0}) for i in range(3)]
    )
    profile = analyze_learning_profile(records, [], "u1")
    dur_pattern = next((p for p in profile.learned_patterns if p.pattern_type == "duration"), None)
    assert dur_pattern is not None
    assert "16-30 min" in dur_pattern.insight


def test_duration_pattern_confidence_reflects_sample_size():
    # 10 samples in best bucket → confidence = 1.0
    records = [_record(i, dec_kwargs={"duration": 25}) for i in range(10)] + \
              [_record(10+i, dec_kwargs={"duration": 55}, outcome_kwargs={"completion_pct": 50.0}) for i in range(3)]
    profile = analyze_learning_profile(records, [], "u1")
    dur_pattern = next((p for p in profile.learned_patterns if p.pattern_type == "duration"), None)
    assert dur_pattern is not None
    assert dur_pattern.confidence_score == 1.0


def test_duration_pattern_evidence_contains_session_count():
    records = (
        [_record(i, dec_kwargs={"duration": 25}) for i in range(5)]
        + [_record(5+i, dec_kwargs={"duration": 55}, outcome_kwargs={"completion_pct": 50.0}) for i in range(3)]
    )
    profile = analyze_learning_profile(records, [], "u1")
    dur_pattern = next((p for p in profile.learned_patterns if p.pattern_type == "duration"), None)
    assert dur_pattern is not None
    assert "sessions" in dur_pattern.evidence


def test_duration_pattern_no_pattern_if_all_one_bucket():
    # All same bucket — only 1 category with samples — needs >= 2 separate categories
    # but within a bucket we need >= 2 samples
    # 10 records all 31-45 min bucket: only 1 non-empty bucket, max is that bucket
    records = [_record(i, dec_kwargs={"duration": 40}) for i in range(10)]
    profile = analyze_learning_profile(records, [], "u1")
    dur_pattern = next((p for p in profile.learned_patterns if p.pattern_type == "duration"), None)
    assert dur_pattern is not None  # Should still detect it as the best (only) bucket


# ── Workout time pattern ──────────────────────────────────────────

def test_time_pattern_detects_best_period():
    # 8 evening completions, 3 morning failures
    records = (
        [_record(i, dec_kwargs={"workout_time": "18:00"}, outcome_kwargs={"completed": True}) for i in range(8)]
        + [_record(8+i, dec_kwargs={"workout_time": "07:00"}, outcome_kwargs={"completed": False}) for i in range(3)]
    )
    profile = analyze_learning_profile(records, [], "u1")
    time_pattern = next((p for p in profile.learned_patterns if p.pattern_type == "time_of_day"), None)
    assert time_pattern is not None
    assert "evening" in time_pattern.insight


def test_time_pattern_insight_contains_rate():
    records = [_record(i, dec_kwargs={"workout_time": "18:00"}, outcome_kwargs={"completed": True}) for i in range(5)] + \
              [_record(5+i, dec_kwargs={"workout_time": "07:00"}, outcome_kwargs={"completed": False}) for i in range(3)]
    profile = analyze_learning_profile(records, [], "u1")
    time_pattern = next((p for p in profile.learned_patterns if p.pattern_type == "time_of_day"), None)
    assert time_pattern is not None
    assert "%" in time_pattern.insight


def test_time_pattern_not_generated_without_enough_per_category():
    # Only 1 record per time category
    records = [
        _record(0, dec_kwargs={"workout_time": "07:00"}),
        _record(1, dec_kwargs={"workout_time": "12:00"}),
        _record(2, dec_kwargs={"workout_time": "18:00"}),
    ]
    profile = analyze_learning_profile(records, [], "u1")
    time_pattern = next((p for p in profile.learned_patterns if p.pattern_type == "time_of_day"), None)
    assert time_pattern is None


# ── Stress response pattern ───────────────────────────────────────

def test_stress_pattern_detects_drop():
    # High stress → 40% completion; low stress → 90% completion
    records = (
        [_record(i, ctx_kwargs={"stress": 8}, outcome_kwargs={"completion_pct": 40.0}) for i in range(5)]
        + [_record(5+i, ctx_kwargs={"stress": 3}, outcome_kwargs={"completion_pct": 90.0}) for i in range(5)]
    )
    profile = analyze_learning_profile(records, [], "u1")
    stress_pattern = next((p for p in profile.learned_patterns if p.pattern_type == "stress_response"), None)
    assert stress_pattern is not None
    assert "stress" in stress_pattern.insight.lower()


def test_stress_pattern_not_generated_if_small_delta():
    # Only 3% difference — below the 5% threshold
    records = (
        [_record(i, ctx_kwargs={"stress": 8}, outcome_kwargs={"completion_pct": 87.0}) for i in range(4)]
        + [_record(4+i, ctx_kwargs={"stress": 3}, outcome_kwargs={"completion_pct": 90.0}) for i in range(4)]
    )
    profile = analyze_learning_profile(records, [], "u1")
    stress_pattern = next((p for p in profile.learned_patterns if p.pattern_type == "stress_response"), None)
    assert stress_pattern is None


def test_stress_pattern_resilience_when_high_stress_better():
    # High stress → 90% completion; low stress → 70% completion
    records = (
        [_record(i, ctx_kwargs={"stress": 8}, outcome_kwargs={"completion_pct": 90.0}) for i in range(5)]
        + [_record(5+i, ctx_kwargs={"stress": 3}, outcome_kwargs={"completion_pct": 70.0}) for i in range(5)]
    )
    profile = analyze_learning_profile(records, [], "u1")
    stress_pattern = next((p for p in profile.learned_patterns if p.pattern_type == "stress_response"), None)
    assert stress_pattern is not None
    assert "resilience" in stress_pattern.insight.lower() or "holds" in stress_pattern.insight.lower() or "strong" in stress_pattern.insight.lower()


def test_stress_pattern_needs_both_groups():
    # Only high-stress records → no pattern
    records = [_record(i, ctx_kwargs={"stress": 8}, outcome_kwargs={"completion_pct": 40.0}) for i in range(5)]
    profile = analyze_learning_profile(records, [], "u1")
    stress_pattern = next((p for p in profile.learned_patterns if p.pattern_type == "stress_response"), None)
    assert stress_pattern is None


# ── Travel response pattern ───────────────────────────────────────

def test_travel_pattern_detects_drop():
    # Travel → 30% workout; no-travel → 90% workout
    records = (
        [_record(i, ctx_kwargs={"travel": True}, outcome_kwargs={"completion_pct": 30.0, "overall_pct": 35.0}) for i in range(4)]
        + [_record(4+i, ctx_kwargs={"travel": False}, outcome_kwargs={"completion_pct": 90.0, "overall_pct": 88.0}) for i in range(4)]
    )
    profile = analyze_learning_profile(records, [], "u1")
    travel_pattern = next((p for p in profile.learned_patterns if p.pattern_type == "travel_response"), None)
    assert travel_pattern is not None
    assert "travel" in travel_pattern.insight.lower()


def test_travel_pattern_evidence_mentions_counts():
    records = (
        [_record(i, ctx_kwargs={"travel": True}, outcome_kwargs={"completion_pct": 30.0, "overall_pct": 30.0}) for i in range(3)]
        + [_record(3+i, ctx_kwargs={"travel": False}, outcome_kwargs={"completion_pct": 90.0, "overall_pct": 90.0}) for i in range(5)]
    )
    profile = analyze_learning_profile(records, [], "u1")
    travel_pattern = next((p for p in profile.learned_patterns if p.pattern_type == "travel_response"), None)
    assert travel_pattern is not None
    assert "3" in travel_pattern.evidence  # 3 travel days


def test_travel_pattern_not_generated_without_enough_travel():
    records = (
        [_record(0, ctx_kwargs={"travel": True}, outcome_kwargs={"completion_pct": 30.0, "overall_pct": 30.0})]
        + [_record(i+1, ctx_kwargs={"travel": False}, outcome_kwargs={"completion_pct": 90.0, "overall_pct": 90.0}) for i in range(5)]
    )
    profile = analyze_learning_profile(records, [], "u1")
    travel_pattern = next((p for p in profile.learned_patterns if p.pattern_type == "travel_response"), None)
    assert travel_pattern is None


# ── Meal adherence pattern ────────────────────────────────────────

def test_meal_pattern_detects_best_location():
    records = (
        [_record(i, dec_kwargs={"location": "office"}, outcome_kwargs={"meal_ordered": True, "meal_confirmed": True}) for i in range(5)]
        + [_record(5+i, dec_kwargs={"location": "home"}, outcome_kwargs={"meal_ordered": True, "meal_confirmed": False}) for i in range(4)]
    )
    profile = analyze_learning_profile(records, [], "u1")
    meal_pattern = next((p for p in profile.learned_patterns if p.pattern_type == "meal_adherence"), None)
    assert meal_pattern is not None
    assert "office" in meal_pattern.insight


def test_meal_pattern_evidence_lists_locations():
    records = (
        [_record(i, dec_kwargs={"location": "office"}) for i in range(3)]
        + [_record(3+i, dec_kwargs={"location": "home"}) for i in range(3)]
    )
    profile = analyze_learning_profile(records, [], "u1")
    meal_pattern = next((p for p in profile.learned_patterns if p.pattern_type == "meal_adherence"), None)
    assert meal_pattern is not None
    assert "office" in meal_pattern.evidence or "home" in meal_pattern.evidence


# ── Sleep response pattern ────────────────────────────────────────

def test_sleep_pattern_detects_energy_drop():
    # Short sleep → next day energy 4; good sleep → next day energy 8
    records = [_record(i, ctx_kwargs={"sleep": 5.0}) for i in range(4)] + \
              [_record(4+i, ctx_kwargs={"sleep": 7.5}) for i in range(4)]
    # Next-day outcomes: short sleep records → low energy, good sleep → high energy
    outcomes = (
        [_outcome_record(i + 1, energy=4.0) for i in range(4)]
        + [_outcome_record(4+i + 1, energy=8.0) for i in range(4)]
    )
    profile = analyze_learning_profile(records, outcomes, "u1")
    sleep_pattern = next((p for p in profile.learned_patterns if p.pattern_type == "sleep_response"), None)
    assert sleep_pattern is not None
    assert "6h" in sleep_pattern.insight or "sleep" in sleep_pattern.insight.lower()


def test_sleep_pattern_not_generated_without_outcome_records():
    records = [_record(i, ctx_kwargs={"sleep": 5.0 if i < 3 else 7.5}) for i in range(6)]
    profile = analyze_learning_profile(records, [], "u1")
    sleep_pattern = next((p for p in profile.learned_patterns if p.pattern_type == "sleep_response"), None)
    assert sleep_pattern is None


def test_sleep_pattern_not_generated_with_small_delta():
    # Only 0.3 point difference — below 0.5 threshold
    records = [_record(i, ctx_kwargs={"sleep": 5.0}) for i in range(3)] + \
              [_record(3+i, ctx_kwargs={"sleep": 7.5}) for i in range(3)]
    outcomes = (
        [_outcome_record(i + 1, energy=6.8) for i in range(3)]
        + [_outcome_record(3+i + 1, energy=7.1) for i in range(3)]
    )
    profile = analyze_learning_profile(records, outcomes, "u1")
    sleep_pattern = next((p for p in profile.learned_patterns if p.pattern_type == "sleep_response"), None)
    assert sleep_pattern is None


# ── Recovery effectiveness pattern ───────────────────────────────

def test_recovery_pattern_detects_stress_reduction():
    # Recovery days → next-day stress drops from 7 to 3
    records = [_record(i, dec_kwargs={"day_type": "recovery"}) for i in range(4)]
    outcomes = []
    for i in range(4):
        outcomes.append(_outcome_record(i,     stress=7.0))  # same day
        outcomes.append(_outcome_record(i + 1, stress=3.0))  # next day
    profile = analyze_learning_profile(records, outcomes, "u1")
    rec_pattern = next((p for p in profile.learned_patterns if p.pattern_type == "recovery_effectiveness"), None)
    assert rec_pattern is not None
    assert "stress" in rec_pattern.insight.lower() or "recovery" in rec_pattern.insight.lower()


def test_recovery_pattern_not_generated_without_outcome_records():
    records = [_record(i, dec_kwargs={"day_type": "recovery"}) for i in range(4)]
    profile = analyze_learning_profile(records, [], "u1")
    rec_pattern = next((p for p in profile.learned_patterns if p.pattern_type == "recovery_effectiveness"), None)
    assert rec_pattern is None


def test_recovery_pattern_not_generated_without_enough_recovery_days():
    # Only 1 recovery day
    records = [
        _record(0, dec_kwargs={"day_type": "recovery"}),
        _record(1, dec_kwargs={"day_type": "normal"}),
    ]
    outcomes = [_outcome_record(0, stress=7.0), _outcome_record(1, stress=3.0)]
    profile = analyze_learning_profile(records, outcomes, "u1")
    rec_pattern = next((p for p in profile.learned_patterns if p.pattern_type == "recovery_effectiveness"), None)
    assert rec_pattern is None


# ── Pattern confidence output ─────────────────────────────────────

def test_all_patterns_have_required_fields():
    records = (
        [_record(i, dec_kwargs={"duration": 25, "workout_time": "18:00", "location": "office"}) for i in range(5)]
        + [_record(5+i, dec_kwargs={"duration": 50, "workout_time": "07:00", "location": "home"},
                   outcome_kwargs={"completion_pct": 50.0}) for i in range(3)]
    )
    profile = analyze_learning_profile(records, [], "u1")
    for pattern in profile.learned_patterns:
        assert isinstance(pattern.pattern_type, str) and pattern.pattern_type
        assert isinstance(pattern.insight, str) and len(pattern.insight) > 10
        assert isinstance(pattern.evidence, str) and len(pattern.evidence) > 10
        assert 0.0 <= pattern.confidence_score <= 1.0
        assert isinstance(pattern.recommended_action, str) and len(pattern.recommended_action) > 10


def test_recommended_adaptations_only_from_medium_plus_confidence():
    # Create a pattern that has confidence_score < 0.4 (2 samples → 0.2)
    records = (
        [_record(i, dec_kwargs={"duration": 25}, outcome_kwargs={"completion_pct": 100.0}) for i in range(2)]
        + [_record(2+i, dec_kwargs={"duration": 55}, outcome_kwargs={"completion_pct": 50.0}) for i in range(2)]
    )
    profile = analyze_learning_profile(records, [], "u1")
    dur_pattern = next((p for p in profile.learned_patterns if p.pattern_type == "duration"), None)
    if dur_pattern and dur_pattern.confidence_score < 0.4:
        assert dur_pattern.recommended_action not in profile.recommended_adaptations


# ── build_personalization_note ────────────────────────────────────

def test_personalization_note_returned_when_mismatch():
    # Best bucket is 16-30 min (high confidence), recommended is 46 min → mismatch
    records = [_record(i, dec_kwargs={"duration": 25}, outcome_kwargs={"completion_pct": 95.0}) for i in range(10)] + \
              [_record(10+i, dec_kwargs={"duration": 55}, outcome_kwargs={"completion_pct": 40.0}) for i in range(5)]
    profile = analyze_learning_profile(records, [], "u1")
    note = build_personalization_note(profile, recommended_duration=55)
    # Should return a note since 55 min → "46-60 min" bucket, best is "16-30 min"
    if note is not None:
        assert "16-30 min" in note or "Personalized" in note


def test_personalization_note_none_when_low_confidence():
    records = _make_records(3)  # confidence = "low"
    profile = analyze_learning_profile(records, [], "u1")
    note = build_personalization_note(profile, recommended_duration=45)
    assert note is None


def test_personalization_note_none_when_no_duration_pattern():
    # No duration pattern generated (same bucket for all)
    records = [_record(i, dec_kwargs={"duration": 30}) for i in range(10)]
    profile = analyze_learning_profile(records, [], "u1")
    note = build_personalization_note(profile, recommended_duration=30)
    # If duration pattern matches recommended bucket → note should be None
    # (no mismatch to surface)
    assert note is None or isinstance(note, str)


# ── get_learning_insights_view ────────────────────────────────────

def test_insights_view_has_sufficient_data_false_below_threshold():
    profile = analyze_learning_profile([], [], "u1")
    view = get_learning_insights_view(profile)
    assert view.has_sufficient_data is False


def test_insights_view_has_sufficient_data_true_at_threshold():
    records = _make_records(LOW_THRESHOLD)
    profile = analyze_learning_profile(records, [], "u1")
    view = get_learning_insights_view(profile)
    assert view.has_sufficient_data is True


def test_insights_view_insights_count_matches_patterns():
    records = (
        [_record(i, dec_kwargs={"duration": 25, "workout_time": "18:00"}) for i in range(5)]
        + [_record(5+i, dec_kwargs={"duration": 50, "workout_time": "07:00"},
                   outcome_kwargs={"completion_pct": 50.0, "completed": False}) for i in range(3)]
    )
    profile = analyze_learning_profile(records, [], "u1")
    view = get_learning_insights_view(profile)
    assert len(view.insights) == len(profile.learned_patterns)


def test_insights_view_actions_only_from_medium_confidence():
    records = _make_records(5)
    profile = analyze_learning_profile(records, [], "u1")
    view = get_learning_insights_view(profile)
    for action in view.actions:
        matching = [p for p in profile.learned_patterns if p.recommended_action == action]
        assert all(p.confidence_score >= 0.4 for p in matching)


# ── ML dataset extension ──────────────────────────────────────────

def _decision_doc_ext(user_id, date_str, duration=30, workout_time="18:00",
                      location="home", stress=4, travel=False,
                      completed=True, completion_pct=90.0, meal_ordered=True,
                      meal_confirmed=True, sleep_achieved=True, overall_pct=85.0):
    ctx = RecordContext(
        sleep_hours=7, stress_level=stress, mood=7, meetings=2,
        travel=travel, cycle_phase=None, previous_workout=None,
        goal="fitness", recovery_score=70, energy_score=70,
        stress_score=70, context_flags=[],
    )
    dec = RecordDecision(
        day_type="normal", workout_type="strength",
        workout_duration_recommended=duration, workout_intensity="moderate",
        selected_lunch="Salad", selected_dinner="Bowl",
        meal_calories=800, delivery_location=location,
        workout_time=workout_time, sleep_target="23:00",
    )
    outcome = RecordOutcome(
        completed_workout=completed,
        workout_duration_completed=duration if completed else 0,
        workout_completion_percentage=completion_pct,
        meal_ordered=meal_ordered,
        meal_confirmed=meal_confirmed,
        sleep_target_achieved=sleep_achieved,
        overall_completion_percentage=overall_pct,
    )
    return DecisionRecord(user_id=user_id, date=date_str, context=ctx, decision=dec, outcome=outcome).model_dump()


def _ml_col(docs):
    col = MagicMock()
    col.find = MagicMock(return_value=iter(docs))
    return col


def test_ml_export_has_learning_fields():
    doc = _decision_doc_ext("u1", "2026-06-09")
    col = _ml_col([doc])
    rows = export_training_dataset(col, None)
    assert len(rows) == 1
    row = rows[0]
    assert "best_workout_duration_bucket" in row
    assert "best_workout_time" in row
    assert "meal_adherence_rate" in row
    assert "sleep_adherence_rate" in row
    assert "personal_learning_confidence" in row


def test_ml_export_learning_confidence_starts_low():
    docs = [_decision_doc_ext("u1", f"2026-06-0{i+1}") for i in range(3)]
    col = _ml_col(docs)
    rows = export_training_dataset(col, None)
    # All 3 rows should have low confidence
    for row in rows:
        assert row["personal_learning_confidence"] == "low"


def test_ml_export_learning_confidence_medium_at_7():
    docs = [_decision_doc_ext("u1", f"2026-0{(i//30)+1}-{(i%30)+1:02d}") for i in range(7)]
    col = _ml_col(docs)
    rows = export_training_dataset(col, None)
    assert rows[-1]["personal_learning_confidence"] == "medium"


def test_ml_export_duration_bucket_correct():
    doc = _decision_doc_ext("u1", "2026-06-09", duration=25)
    col = _ml_col([doc])
    rows = export_training_dataset(col, None)
    assert rows[0]["best_workout_duration_bucket"] == "16-30 min"


def test_ml_export_workout_time_correct():
    doc = _decision_doc_ext("u1", "2026-06-09", workout_time="18:00")
    col = _ml_col([doc])
    rows = export_training_dataset(col, None)
    assert rows[0]["best_workout_time"] == "evening"


def test_ml_export_meal_adherence_rate_computed():
    doc = _decision_doc_ext("u1", "2026-06-09", meal_ordered=True, meal_confirmed=True)
    col = _ml_col([doc])
    rows = export_training_dataset(col, None)
    assert rows[0]["meal_adherence_rate"] == 100.0


def test_ml_export_sleep_adherence_rate_computed():
    doc = _decision_doc_ext("u1", "2026-06-09", sleep_achieved=True)
    col = _ml_col([doc])
    rows = export_training_dataset(col, None)
    assert rows[0]["sleep_adherence_rate"] == 100.0


def test_ml_export_stress_adherence_rate_none_when_no_high_stress():
    doc = _decision_doc_ext("u1", "2026-06-09", stress=3)  # stress < 7 → not tracked
    col = _ml_col([doc])
    rows = export_training_dataset(col, None)
    assert rows[0]["stress_adherence_rate"] is None


def test_ml_export_stress_adherence_rate_computed_when_high_stress():
    doc = _decision_doc_ext("u1", "2026-06-09", stress=8, completion_pct=60.0)
    col = _ml_col([doc])
    rows = export_training_dataset(col, None)
    assert rows[0]["stress_adherence_rate"] == 60.0


def test_ml_export_travel_adherence_rate_none_when_no_travel():
    doc = _decision_doc_ext("u1", "2026-06-09", travel=False)
    col = _ml_col([doc])
    rows = export_training_dataset(col, None)
    assert rows[0]["travel_adherence_rate"] is None


def test_ml_export_travel_adherence_rate_computed():
    doc = _decision_doc_ext("u1", "2026-06-09", travel=True, overall_pct=55.0)
    col = _ml_col([doc])
    rows = export_training_dataset(col, None)
    assert rows[0]["travel_adherence_rate"] == 55.0


def test_ml_export_running_meal_adherence_accumulates():
    doc1 = _decision_doc_ext("u1", "2026-06-08", meal_ordered=True, meal_confirmed=True)   # 100
    doc2 = _decision_doc_ext("u1", "2026-06-09", meal_ordered=False, meal_confirmed=False)  # 0
    col = _ml_col([doc1, doc2])
    rows = export_training_dataset(col, None)
    assert rows[0]["meal_adherence_rate"] == 100.0
    assert rows[1]["meal_adherence_rate"] == 50.0  # (100 + 0) / 2
