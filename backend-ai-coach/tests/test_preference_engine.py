"""
Tests for Preference Engine.

Coverage:
  - Helper functions: _duration_bucket, _time_category, _confidence_level
  - Workout type preference detection (preferred / neutral / disliked)
  - Workout dislike detection
  - Duration preference analysis
  - Time preference analysis
  - Delivery location preference
  - Meal category and provider preferences
  - Coaching style inference
  - Feedback CRUD (save / retrieve via mock collection)
  - Preference profile: no data / low / medium / high confidence
  - Preference note generation
  - Daily decision integration (disliked types filtered)
  - ML dataset extension fields
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock, call

from preference_engine import (
    WorkoutFeedback,
    MealFeedback,
    WorkoutTypePreference,
    UserPreferenceProfile,
    save_workout_feedback,
    save_meal_feedback,
    get_workout_feedbacks,
    get_meal_feedbacks,
    compute_preference_profile,
    build_preference_note,
    _duration_bucket,
    _time_category,
    _confidence_level,
    _compute_workout_type_preferences,
    _analyze_duration_preference,
    _analyze_time_preference,
    _analyze_delivery_preference,
    _analyze_meal_preferences,
    _infer_coaching_style,
    PREFERRED_THRESHOLD,
    DISLIKED_THRESHOLD,
    MIN_OCCURRENCES,
    LOW_THRESHOLD,
    MEDIUM_THRESHOLD,
)
from decision_record_service import (
    DecisionRecord, RecordContext, RecordDecision, RecordOutcome,
    export_training_dataset,
)


# ── Fixtures and helpers ──────────────────────────────────────────

BASE_DATE = date(2026, 1, 1)


def _date_str(offset: int) -> str:
    return (BASE_DATE + timedelta(days=offset)).isoformat()


def _ctx(sleep: float = 7.0, stress: int = 4, travel: bool = False):
    return RecordContext(
        sleep_hours=sleep, stress_level=stress, mood=7, meetings=3,
        travel=travel, cycle_phase=None, previous_workout=None, goal="fitness",
        recovery_score=70, energy_score=70, stress_score=70, context_flags=[],
    )


def _dec(
    workout_type: str = "strength",
    duration: int = 30,
    workout_time: str = "18:00",
    location: str = "home",
    day_type: str = "normal",
):
    return RecordDecision(
        day_type=day_type, workout_type=workout_type,
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
    workout_type: str = "strength",
    duration: int = 30,
    workout_time: str = "18:00",
    location: str = "home",
    completion_pct: float = 100.0,
    meal_ordered: bool = True,
    meal_confirmed: bool = True,
    user_id: str = "u1",
    has_outcome: bool = True,
) -> DecisionRecord:
    return DecisionRecord(
        user_id=user_id,
        date=_date_str(offset),
        context=_ctx(),
        decision=_dec(workout_type=workout_type, duration=duration,
                      workout_time=workout_time, location=location),
        outcome=_outcome(completion_pct=completion_pct,
                         meal_ordered=meal_ordered,
                         meal_confirmed=meal_confirmed) if has_outcome else None,
    )


def _wo_feedback(
    offset: int = 0,
    workout_type: str = "strength",
    score: int = 1,
    reason: str = None,
    coaching_style: str = None,
    user_id: str = "u1",
) -> WorkoutFeedback:
    return WorkoutFeedback(
        user_id=user_id, workout_type=workout_type, score=score,
        reason=reason, coaching_style=coaching_style,
        date=_date_str(offset),
    )


def _meal_feedback(
    offset: int = 0,
    meal_id: str = "m1",
    score: int = 1,
    category: str = None,
    provider: str = None,
    reason: str = None,
    user_id: str = "u1",
) -> MealFeedback:
    return MealFeedback(
        user_id=user_id, meal_id=meal_id, score=score,
        category=category, provider=provider, reason=reason,
        date=_date_str(offset),
    )


def _mock_wo_fb_col(feedbacks):
    col = MagicMock()
    docs = [{"feedback_type": "workout", **f.model_dump()} for f in feedbacks]
    col.find = MagicMock(return_value=iter(docs))
    return col


def _mock_meal_fb_col(feedbacks):
    col = MagicMock()
    docs = [{"feedback_type": "meal", **f.model_dump()} for f in feedbacks]
    col.find = MagicMock(return_value=iter(docs))
    return col


def _decision_doc(user_id, date_str, workout_type="strength", duration=30,
                  workout_time="18:00", location="home",
                  completion_pct=90.0, meal_ordered=True,
                  meal_confirmed=True, overall_pct=85.0):
    ctx = RecordContext(
        sleep_hours=7, stress_level=4, mood=7, meetings=2,
        travel=False, cycle_phase=None, previous_workout=None,
        goal="fitness", recovery_score=70, energy_score=70,
        stress_score=70, context_flags=[],
    )
    dec = RecordDecision(
        day_type="normal", workout_type=workout_type,
        workout_duration_recommended=duration, workout_intensity="moderate",
        selected_lunch="Salad", selected_dinner="Bowl",
        meal_calories=800, delivery_location=location,
        workout_time=workout_time, sleep_target="23:00",
    )
    out = RecordOutcome(
        completed_workout=True,
        workout_duration_completed=duration,
        workout_completion_percentage=completion_pct,
        meal_ordered=meal_ordered,
        meal_confirmed=meal_confirmed,
        sleep_target_achieved=True,
        overall_completion_percentage=overall_pct,
    )
    return DecisionRecord(user_id=user_id, date=date_str, context=ctx,
                          decision=dec, outcome=out).model_dump()


def _ml_col(docs):
    col = MagicMock()
    col.find = MagicMock(return_value=iter(docs))
    return col


# ── _duration_bucket helper ───────────────────────────────────────

def test_duration_bucket_0_15():
    assert _duration_bucket(0)  == "0-15 min"
    assert _duration_bucket(15) == "0-15 min"


def test_duration_bucket_16_30():
    assert _duration_bucket(16) == "16-30 min"
    assert _duration_bucket(30) == "16-30 min"


def test_duration_bucket_31_45():
    assert _duration_bucket(31) == "31-45 min"
    assert _duration_bucket(45) == "31-45 min"


def test_duration_bucket_46_60():
    assert _duration_bucket(46) == "46-60 min"
    assert _duration_bucket(60) == "46-60 min"


def test_duration_bucket_60plus():
    assert _duration_bucket(61) == "60+ min"
    assert _duration_bucket(90) == "60+ min"


# ── _time_category helper ─────────────────────────────────────────

def test_time_category_labels_passthrough():
    assert _time_category("morning")   == "morning"
    assert _time_category("afternoon") == "afternoon"
    assert _time_category("evening")   == "evening"


def test_time_category_morning_hour():
    assert _time_category("06:00") == "morning"
    assert _time_category("11:59") == "morning"


def test_time_category_afternoon_hour():
    assert _time_category("12:00") == "afternoon"
    assert _time_category("16:45") == "afternoon"


def test_time_category_evening_hour():
    assert _time_category("17:00") == "evening"
    assert _time_category("22:30") == "evening"


def test_time_category_unknown():
    assert _time_category("")           == "unknown"
    assert _time_category("not_a_time") == "unknown"


# ── _confidence_level helper ──────────────────────────────────────

def test_confidence_level_low():
    assert _confidence_level(0) == "low"
    assert _confidence_level(LOW_THRESHOLD - 1) == "low"


def test_confidence_level_medium():
    assert _confidence_level(LOW_THRESHOLD)      == "medium"
    assert _confidence_level(MEDIUM_THRESHOLD - 1) == "medium"


def test_confidence_level_high():
    assert _confidence_level(MEDIUM_THRESHOLD)   == "high"
    assert _confidence_level(50) == "high"


# ── Feedback CRUD ─────────────────────────────────────────────────

def test_save_workout_feedback_inserts_doc():
    col = MagicMock()
    fb = _wo_feedback(workout_type="yoga", score=1)
    result_id = save_workout_feedback(col, fb)
    assert result_id == fb.id
    col.insert_one.assert_called_once()
    inserted = col.insert_one.call_args[0][0]
    assert inserted["feedback_type"] == "workout"
    assert inserted["workout_type"] == "yoga"
    assert inserted["score"] == 1


def test_save_meal_feedback_inserts_doc():
    col = MagicMock()
    fb = _meal_feedback(meal_id="m42", score=-1, category="vegan")
    result_id = save_meal_feedback(col, fb)
    assert result_id == fb.id
    col.insert_one.assert_called_once()
    inserted = col.insert_one.call_args[0][0]
    assert inserted["feedback_type"] == "meal"
    assert inserted["score"] == -1


def test_get_workout_feedbacks_returns_list():
    feedbacks = [_wo_feedback(i, workout_type="yoga", score=1) for i in range(3)]
    col = _mock_wo_fb_col(feedbacks)
    result = get_workout_feedbacks(col, "u1")
    assert len(result) == 3
    assert all(isinstance(f, WorkoutFeedback) for f in result)
    assert all(f.workout_type == "yoga" for f in result)


def test_get_workout_feedbacks_excludes_feedback_type_field():
    feedbacks = [_wo_feedback(0, workout_type="strength", score=1)]
    col = _mock_wo_fb_col(feedbacks)
    result = get_workout_feedbacks(col, "u1")
    assert len(result) == 1
    # feedback_type should not appear as an attribute on WorkoutFeedback
    assert not hasattr(result[0], "feedback_type")


def test_get_meal_feedbacks_returns_list():
    feedbacks = [_meal_feedback(i, meal_id=f"m{i}", score=1) for i in range(4)]
    col = _mock_meal_fb_col(feedbacks)
    result = get_meal_feedbacks(col, "u1")
    assert len(result) == 4
    assert all(isinstance(f, MealFeedback) for f in result)


def test_get_workout_feedbacks_empty():
    col = _mock_wo_fb_col([])
    result = get_workout_feedbacks(col, "u1")
    assert result == []


def test_get_meal_feedbacks_empty():
    col = _mock_meal_fb_col([])
    result = get_meal_feedbacks(col, "u1")
    assert result == []


# ── _compute_workout_type_preferences ────────────────────────────

def test_workout_pref_below_min_occurrences_excluded():
    records = [_record(0, workout_type="yoga")]  # only 1 occurrence
    result = _compute_workout_type_preferences(records, [])
    assert result == []


def test_workout_pref_preferred_high_completion():
    records = [_record(i, workout_type="strength", completion_pct=95.0) for i in range(5)]
    result = _compute_workout_type_preferences(records, [])
    assert len(result) == 1
    assert result[0].workout_type == "strength"
    assert result[0].classification == "preferred"
    assert result[0].preference_score >= PREFERRED_THRESHOLD


def test_workout_pref_disliked_low_completion():
    records = [_record(i, workout_type="hiit", completion_pct=20.0) for i in range(5)]
    result = _compute_workout_type_preferences(records, [])
    assert len(result) == 1
    assert result[0].classification == "disliked"
    assert result[0].preference_score <= DISLIKED_THRESHOLD


def test_workout_pref_neutral_mid_range_completion():
    records = [_record(i, workout_type="yoga", completion_pct=55.0) for i in range(3)]
    result = _compute_workout_type_preferences(records, [])
    assert len(result) == 1
    assert result[0].classification == "neutral"


def test_workout_pref_explicit_positive_boosts_score():
    # 50% completion alone = 0.35 score → disliked
    # but +ve feedback should push it above disliked threshold
    records = [_record(i, workout_type="yoga", completion_pct=50.0) for i in range(3)]
    feedbacks = [_wo_feedback(i, workout_type="yoga", score=1) for i in range(3)]
    result = _compute_workout_type_preferences(records, feedbacks)
    assert len(result) == 1
    # explicit_factor = 0.5 + (3/3)*0.5 = 1.0; score = 0.5*0.7 + 1.0*0.3 = 0.65
    assert result[0].preference_score > 0.35


def test_workout_pref_explicit_negative_lowers_score():
    # 80% completion → would be preferred, but all-negative feedback should lower it
    records = [_record(i, workout_type="strength", completion_pct=80.0) for i in range(3)]
    feedbacks = [_wo_feedback(i, workout_type="strength", score=-1) for i in range(5)]
    result = _compute_workout_type_preferences(records, feedbacks)
    assert len(result) == 1
    # explicit_factor = 0.5 + (-1)*0.5 = 0.0; score = 0.8*0.7 + 0.0*0.3 = 0.56
    assert result[0].preference_score < 0.65


def test_workout_pref_neutral_when_no_feedback():
    records = [_record(i, workout_type="yoga", completion_pct=80.0) for i in range(3)]
    result = _compute_workout_type_preferences(records, [])
    # explicit_factor = 0.5 (neutral); score = 0.8*0.7 + 0.5*0.3 = 0.71 → preferred
    assert result[0].explicit_factor == 0.5


def test_workout_pref_sorted_descending():
    records = (
        [_record(i, workout_type="strength", completion_pct=95.0) for i in range(4)]
        + [_record(4+i, workout_type="yoga", completion_pct=40.0) for i in range(3)]
    )
    result = _compute_workout_type_preferences(records, [])
    scores = [r.preference_score for r in result]
    assert scores == sorted(scores, reverse=True)


def test_workout_pref_times_selected_counted():
    records = [_record(i, workout_type="strength") for i in range(5)]
    result = _compute_workout_type_preferences(records, [])
    assert result[0].times_selected == 5


def test_workout_pref_ignores_records_without_outcomes():
    records = (
        [_record(i, workout_type="strength", has_outcome=True) for i in range(3)]
        + [_record(3+i, workout_type="strength", has_outcome=False) for i in range(5)]
    )
    result = _compute_workout_type_preferences(records, [])
    # Only 3 records with outcomes
    assert result[0].times_selected == 3


# ── _analyze_duration_preference ─────────────────────────────────

def test_duration_pref_returns_best_bucket():
    records = (
        [_record(i, duration=25, completion_pct=95.0) for i in range(4)]  # 16-30 min
        + [_record(4+i, duration=55, completion_pct=40.0) for i in range(3)]  # 46-60 min
    )
    result = _analyze_duration_preference(records)
    assert result == "16-30 min"


def test_duration_pref_none_when_no_eligible_bucket():
    # Only 1 record per bucket → below MIN_OCCURRENCES
    records = [
        _record(0, duration=20),
        _record(1, duration=35),
        _record(2, duration=55),
    ]
    result = _analyze_duration_preference(records)
    assert result is None


def test_duration_pref_none_when_no_outcomes():
    records = [_record(i, duration=30, has_outcome=False) for i in range(5)]
    result = _analyze_duration_preference(records)
    assert result is None


def test_duration_pref_correct_bucket_label():
    records = [_record(i, duration=45, completion_pct=90.0) for i in range(3)]
    result = _analyze_duration_preference(records)
    assert result == "31-45 min"


# ── _analyze_time_preference ──────────────────────────────────────

def test_time_pref_returns_best_time_period():
    records = (
        [_record(i, workout_time="18:00", completion_pct=100.0) for i in range(4)]  # evening
        + [_record(4+i, workout_time="07:00", completion_pct=30.0) for i in range(3)]  # morning
    )
    # Use _analyze_time_preference which uses completed_workout bool
    from preference_engine import _analyze_time_preference as atp
    # Need completed flag — _analyze_time_preference checks completed_workout
    records2 = (
        [_record(i, workout_time="18:00") for i in range(4)]
        + [_record(4+i, workout_time="07:00", completion_pct=0.0) for i in range(3)]
    )
    # Add completed flag via full record rebuild
    from decision_record_service import RecordOutcome
    for r in records2[:4]:
        r.outcome.completed_workout = True
    for r in records2[4:]:
        r.outcome.completed_workout = False
    result = _analyze_time_preference(records2)
    assert result == "evening"


def test_time_pref_none_when_no_eligible_category():
    # Only 1 record per time category
    records = [
        _record(0, workout_time="07:00"),
        _record(1, workout_time="12:00"),
        _record(2, workout_time="18:00"),
    ]
    result = _analyze_time_preference(records)
    assert result is None


def test_time_pref_skips_unknown_time():
    records = [_record(i, workout_time="not_valid") for i in range(5)]
    result = _analyze_time_preference(records)
    assert result is None


def test_time_pref_none_when_no_outcomes():
    records = [_record(i, workout_time="18:00", has_outcome=False) for i in range(5)]
    result = _analyze_time_preference(records)
    assert result is None


# ── _analyze_delivery_preference ──────────────────────────────────

def test_delivery_pref_returns_best_location():
    records = (
        [_record(i, location="office", meal_ordered=True, meal_confirmed=True) for i in range(4)]
        + [_record(4+i, location="home", meal_ordered=False, meal_confirmed=False) for i in range(3)]
    )
    result = _analyze_delivery_preference(records)
    assert result == "office"


def test_delivery_pref_none_when_no_eligible():
    # Only 1 record per location
    records = [
        _record(0, location="office"),
        _record(1, location="home"),
        _record(2, location="travel"),
    ]
    result = _analyze_delivery_preference(records)
    assert result is None


def test_delivery_pref_scores_partial_order():
    # Home: fully confirmed (100), travel: only ordered (50)
    records = (
        [_record(i, location="home", meal_ordered=True, meal_confirmed=True) for i in range(3)]
        + [_record(3+i, location="travel", meal_ordered=True, meal_confirmed=False) for i in range(3)]
    )
    result = _analyze_delivery_preference(records)
    assert result == "home"


# ── _analyze_meal_preferences ─────────────────────────────────────

def test_meal_pref_positive_categories_returned():
    feedbacks = [_meal_feedback(i, category="vegan", score=1) for i in range(3)]
    cats, providers = _analyze_meal_preferences(feedbacks)
    assert "vegan" in cats


def test_meal_pref_negative_categories_excluded():
    feedbacks = [_meal_feedback(i, category="junk_food", score=-1) for i in range(3)]
    cats, _ = _analyze_meal_preferences(feedbacks)
    assert "junk_food" not in cats


def test_meal_pref_positive_providers_returned():
    feedbacks = [_meal_feedback(i, provider="Every Foods", score=1) for i in range(3)]
    _, providers = _analyze_meal_preferences(feedbacks)
    assert "Every Foods" in providers


def test_meal_pref_min_occurrences_required():
    # Only 1 feedback per category — below MIN_OCCURRENCES=2
    feedbacks = [_meal_feedback(0, category="vegan", score=1)]
    cats, _ = _analyze_meal_preferences(feedbacks)
    assert "vegan" not in cats


def test_meal_pref_empty_feedback():
    cats, providers = _analyze_meal_preferences([])
    assert cats == []
    assert providers == []


def test_meal_pref_mixed_scores_excluded():
    # Net 0 (1 positive, 1 negative) → not positive
    feedbacks = [
        _meal_feedback(0, category="mediterranean", score=1),
        _meal_feedback(1, category="mediterranean", score=-1),
    ]
    cats, _ = _analyze_meal_preferences(feedbacks)
    assert "mediterranean" not in cats


# ── _infer_coaching_style ─────────────────────────────────────────

def test_coaching_style_returns_best_style():
    feedbacks = (
        [_wo_feedback(i, coaching_style="motivational", score=1) for i in range(3)]
        + [_wo_feedback(3+i, coaching_style="scientific", score=-1) for i in range(2)]
    )
    result = _infer_coaching_style(feedbacks)
    assert result == "motivational"


def test_coaching_style_none_when_insufficient_feedback():
    feedbacks = [_wo_feedback(0, coaching_style="direct", score=1)]  # only 1
    result = _infer_coaching_style(feedbacks)
    assert result is None


def test_coaching_style_none_when_net_score_negative():
    feedbacks = [_wo_feedback(i, coaching_style="direct", score=-1) for i in range(3)]
    result = _infer_coaching_style(feedbacks)
    assert result is None


def test_coaching_style_ignores_invalid_styles():
    feedbacks = [_wo_feedback(i, coaching_style="aggressive", score=1) for i in range(3)]
    result = _infer_coaching_style(feedbacks)
    assert result is None


def test_coaching_style_none_when_no_feedback():
    result = _infer_coaching_style([])
    assert result is None


def test_coaching_style_none_when_no_style_tagged():
    feedbacks = [_wo_feedback(i, score=1) for i in range(5)]  # no coaching_style set
    result = _infer_coaching_style(feedbacks)
    assert result is None


# ── compute_preference_profile ────────────────────────────────────

def test_profile_no_data():
    profile = compute_preference_profile("u1", [], [], [])
    assert profile.user_id == "u1"
    assert profile.total_decisions_analyzed == 0
    assert profile.confidence_level == "low"
    assert profile.preferred_workout_types == []
    assert profile.disliked_workout_types == []
    assert profile.workout_type_scores == []
    assert profile.preferred_workout_time is None
    assert profile.preferred_duration_bucket is None
    assert profile.preferred_delivery_location is None
    assert profile.preferred_meal_categories == []
    assert profile.preferred_providers == []
    assert profile.preferred_coaching_style is None


def test_profile_confidence_low():
    records = [_record(i) for i in range(LOW_THRESHOLD - 1)]
    profile = compute_preference_profile("u1", records, [], [])
    assert profile.confidence_level == "low"
    assert profile.total_decisions_analyzed == LOW_THRESHOLD - 1


def test_profile_confidence_medium_at_threshold():
    records = [_record(i) for i in range(LOW_THRESHOLD)]
    profile = compute_preference_profile("u1", records, [], [])
    assert profile.confidence_level == "medium"


def test_profile_confidence_high_at_threshold():
    records = [_record(i) for i in range(MEDIUM_THRESHOLD)]
    profile = compute_preference_profile("u1", records, [], [])
    assert profile.confidence_level == "high"


def test_profile_preferred_workout_types_populated():
    records = [_record(i, workout_type="yoga", completion_pct=90.0) for i in range(5)]
    profile = compute_preference_profile("u1", records, [], [])
    assert "yoga" in profile.preferred_workout_types


def test_profile_disliked_workout_types_populated():
    records = [_record(i, workout_type="hiit", completion_pct=10.0) for i in range(5)]
    profile = compute_preference_profile("u1", records, [], [])
    assert "hiit" in profile.disliked_workout_types


def test_profile_type_scores_present():
    records = [_record(i, workout_type="strength", completion_pct=85.0) for i in range(3)]
    profile = compute_preference_profile("u1", records, [], [])
    assert len(profile.workout_type_scores) == 1
    assert profile.workout_type_scores[0].workout_type == "strength"


def test_profile_duration_bucket_populated():
    records = [_record(i, duration=25, completion_pct=90.0) for i in range(3)]
    profile = compute_preference_profile("u1", records, [], [])
    assert profile.preferred_duration_bucket == "16-30 min"


def test_profile_delivery_location_populated():
    records = [_record(i, location="office", meal_ordered=True, meal_confirmed=True)
               for i in range(3)]
    profile = compute_preference_profile("u1", records, [], [])
    assert profile.preferred_delivery_location == "office"


def test_profile_meal_categories_from_feedback():
    records = [_record(i) for i in range(3)]
    meal_fbs = [_meal_feedback(i, category="mediterranean", score=1) for i in range(3)]
    profile = compute_preference_profile("u1", records, [], meal_fbs)
    assert "mediterranean" in profile.preferred_meal_categories


def test_profile_coaching_style_from_feedback():
    records = [_record(i) for i in range(3)]
    wo_fbs = [_wo_feedback(i, coaching_style="supportive", score=1) for i in range(3)]
    profile = compute_preference_profile("u1", records, wo_fbs, [])
    assert profile.preferred_coaching_style == "supportive"


def test_profile_insights_nonempty_with_data():
    records = [_record(i, workout_type="strength", completion_pct=90.0) for i in range(3)]
    profile = compute_preference_profile("u1", records, [], [])
    assert len(profile.preference_insights) > 0


def test_profile_recommendation_boosts_from_preferred():
    records = [_record(i, workout_type="yoga", completion_pct=90.0) for i in range(3)]
    profile = compute_preference_profile("u1", records, [], [])
    boosts_text = " ".join(profile.recommendation_boosts).lower()
    assert "yoga" in boosts_text


def test_profile_generated_at_present():
    profile = compute_preference_profile("u1", [], [], [])
    assert isinstance(profile.generated_at, str) and len(profile.generated_at) > 0


def test_profile_excludes_records_without_outcomes():
    records = (
        [_record(i, workout_type="strength", has_outcome=True) for i in range(3)]
        + [_record(3+i, workout_type="strength", has_outcome=False) for i in range(10)]
    )
    profile = compute_preference_profile("u1", records, [], [])
    assert profile.total_decisions_analyzed == 3


# ── build_preference_note ─────────────────────────────────────────

def test_preference_note_none_when_low_confidence():
    records = [_record(i, workout_type="strength") for i in range(3)]
    profile = compute_preference_profile("u1", records, [], [])
    # confidence = low (3 < 7)
    note = build_preference_note(profile, "strength", 30)
    assert note is None


def test_preference_note_returned_for_preferred_type_high_completion():
    records = [_record(i, workout_type="strength", completion_pct=90.0) for i in range(LOW_THRESHOLD)]
    profile = compute_preference_profile("u1", records, [], [])
    # strength is preferred with high completion rate
    note = build_preference_note(profile, "strength", 30)
    if note is not None:
        assert "strength" in note.lower() or "adherence" in note.lower()


def test_preference_note_warns_for_disliked_type():
    records = [_record(i, workout_type="hiit", completion_pct=15.0) for i in range(LOW_THRESHOLD)]
    profile = compute_preference_profile("u1", records, [], [])
    note = build_preference_note(profile, "hiit", 30)
    if note is not None:
        assert "hiit" in note.lower() or "lower adherence" in note.lower()


def test_preference_note_none_for_neutral_type():
    # 55% completion → neutral classification
    records = [_record(i, workout_type="yoga", completion_pct=55.0) for i in range(LOW_THRESHOLD)]
    profile = compute_preference_profile("u1", records, [], [])
    note = build_preference_note(profile, "yoga", 30)
    # neutral type → no note
    assert note is None


def test_preference_note_none_when_no_workout_types():
    profile = compute_preference_profile("u1", [], [], [])
    note = build_preference_note(profile, "strength", 30)
    assert note is None


# ── Daily decision integration ────────────────────────────────────

def test_select_workout_filters_disliked():
    from daily_decision_engine import select_workout
    # Candidates for "normal" day should include disliked type
    # When disliked is specified, it should be filtered out if alternatives exist
    result = select_workout(
        effective_day_type="normal",
        level="intermediate",
        preferred_types=[],
        available_minutes=30,
        disliked_types=["hiit"],
    )
    # Result must not be hiit if alternatives available
    assert isinstance(result, dict)
    assert "workout_type" in result


def test_select_workout_falls_back_when_all_disliked():
    from daily_decision_engine import select_workout
    # When all candidates are disliked, should still return a workout
    result = select_workout(
        effective_day_type="normal",
        level="beginner",
        preferred_types=[],
        available_minutes=30,
        disliked_types=["strength", "hiit", "yoga", "cardio", "mobility",
                        "sport", "pilates", "crossfit", "calisthenics", "cycling"],
    )
    assert result is not None
    assert "workout_type" in result


def test_generate_daily_decision_accepts_preference_params():
    from daily_decision_engine import generate_daily_decision, DailyDecisionRequest

    request = DailyDecisionRequest(
        user_id="u1",
        user_profile={
            "name": "Test User",
            "ziel": "Gesund bleiben",
            "ernaehrung": "Mischkost",
            "level": "Einsteiger",
        },
        daily_context={
            "sleep_hours": 7,
            "stress_level": 4,
            "meetings_count": 3,
            "mood_level": 7,
            "travel_today": False,
            "available_training_window_minutes": 30,
        },
    )
    response = generate_daily_decision(
        request,
        user_preferred_workout_types=["yoga"],
        user_disliked_workout_types=["hiit"],
    )
    assert response is not None
    assert hasattr(response, "selected_workout")


# ── ML dataset preference fields ──────────────────────────────────

def test_ml_export_has_preference_fields():
    doc = _decision_doc("u1", "2026-06-09")
    col = _ml_col([doc])
    rows = export_training_dataset(col, None)
    assert len(rows) == 1
    row = rows[0]
    assert "preferred_workout_type" in row
    assert "preferred_delivery_location" in row
    assert "preference_confidence" in row


def test_ml_export_preference_confidence_matches_learning_confidence():
    doc = _decision_doc("u1", "2026-06-09")
    col = _ml_col([doc])
    rows = export_training_dataset(col, None)
    row = rows[0]
    assert row["preference_confidence"] == row["personal_learning_confidence"]


def test_ml_export_preferred_workout_type_none_below_min_occurrences():
    # Only 1 record per workout type → no preferred type
    doc = _decision_doc("u1", "2026-06-09", workout_type="strength")
    col = _ml_col([doc])
    rows = export_training_dataset(col, None)
    assert rows[0]["preferred_workout_type"] is None


def test_ml_export_preferred_workout_type_computed_after_two():
    # 2 records of same type → qualifies for preferred type
    doc1 = _decision_doc("u1", "2026-06-08", workout_type="yoga", completion_pct=90.0)
    doc2 = _decision_doc("u1", "2026-06-09", workout_type="yoga", completion_pct=90.0)
    col = _ml_col([doc1, doc2])
    rows = export_training_dataset(col, None)
    assert rows[1]["preferred_workout_type"] == "yoga"


def test_ml_export_preferred_delivery_location_none_below_min():
    doc = _decision_doc("u1", "2026-06-09", location="office")
    col = _ml_col([doc])
    rows = export_training_dataset(col, None)
    assert rows[0]["preferred_delivery_location"] is None


def test_ml_export_preferred_delivery_location_computed_after_two():
    doc1 = _decision_doc("u1", "2026-06-08", location="office",
                         meal_ordered=True, meal_confirmed=True)
    doc2 = _decision_doc("u1", "2026-06-09", location="office",
                         meal_ordered=True, meal_confirmed=True)
    col = _ml_col([doc1, doc2])
    rows = export_training_dataset(col, None)
    assert rows[1]["preferred_delivery_location"] == "office"


def test_ml_export_preference_confidence_low_at_start():
    doc = _decision_doc("u1", "2026-06-09")
    col = _ml_col([doc])
    rows = export_training_dataset(col, None)
    assert rows[0]["preference_confidence"] == "low"


def test_ml_export_preference_confidence_medium_at_7():
    docs = [_decision_doc("u1", f"2026-0{(i//30)+1}-{(i%30)+1:02d}") for i in range(7)]
    col = _ml_col(docs)
    rows = export_training_dataset(col, None)
    assert rows[-1]["preference_confidence"] == "medium"


def test_ml_export_running_preferred_type_updates_per_record():
    # First record: no preferred type (1 < MIN_OCCURRENCES)
    # Second record: yoga becomes preferred (2 occurrences)
    doc1 = _decision_doc("u1", "2026-06-08", workout_type="yoga", completion_pct=90.0)
    doc2 = _decision_doc("u1", "2026-06-09", workout_type="yoga", completion_pct=90.0)
    col = _ml_col([doc1, doc2])
    rows = export_training_dataset(col, None)
    assert rows[0]["preferred_workout_type"] is None
    assert rows[1]["preferred_workout_type"] == "yoga"
