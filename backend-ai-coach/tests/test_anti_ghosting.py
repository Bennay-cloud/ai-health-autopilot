"""
Tests for the Anti-Ghosting Engine & Adherence Intelligence.

Covers:
  - Streak calculation (current + best)
  - Weekly trend analysis
  - AT_RISK detection (all three conditions)
  - Adaptive recommendations (all adaptation levels + progression)
  - Adherence insights generation
  - Dashboard composition
  - adherence_badge thresholds
  - ML dataset adherence feature extension
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock

from decision_record_service import (
    DecisionRecord, RecordContext, RecordDecision, RecordOutcome,
    AdherenceMetrics, calculate_overall_completion,
    export_training_dataset,
)
from anti_ghosting_service import (
    StreakResult, WeeklyTrends, AtRiskResult, AdaptiveRecommendation,
    AdherenceInsights, DashboardData,
    adherence_badge,
    calculate_streak,
    generate_weekly_trends,
    detect_at_risk,
    generate_adherence_insights,
    generate_adaptive_recommendation,
    generate_dashboard,
    _reduce_intensity,
    _increase_intensity,
)


# ── Fixtures ──────────────────────────────────────────────────────

TODAY = date(2026, 6, 10)


def _ctx(**kw) -> RecordContext:
    d = dict(
        sleep_hours=7.0, stress_level=4, mood=7, meetings=3,
        travel=False, cycle_phase="unknown", previous_workout=None,
        goal="Muskelaufbau", recovery_score=70, energy_score=65, stress_score=72,
        context_flags=[],
    )
    d.update(kw)
    return RecordContext(**d)


def _dec(**kw) -> RecordDecision:
    d = dict(
        day_type="normal", workout_type="strength",
        workout_duration_recommended=45, workout_intensity="moderate",
        selected_lunch="Bowl", selected_dinner="Salmon",
        meal_calories=1200, delivery_location="home",
        workout_time="18:00", sleep_target="22:30",
    )
    d.update(kw)
    return RecordDecision(**d)


def _out(overall: float, *, workout_pct: float | None = None, meal_ordered=True,
         meal_confirmed=True, sleep=True, workout_completed_min=0) -> RecordOutcome:
    wp = workout_pct if workout_pct is not None else overall
    return RecordOutcome(
        completed_workout=wp > 0,
        workout_duration_completed=workout_completed_min,
        workout_completion_percentage=wp,
        meal_ordered=meal_ordered,
        meal_confirmed=meal_confirmed,
        sleep_target_achieved=sleep,
        overall_completion_percentage=overall,
    )


def _record(
    overall: float,
    days_ago: int = 0,
    *,
    travel: bool = False,
    meal_confirmed: bool = True,
    meal_ordered: bool = True,
    sleep: bool = True,
    no_outcome: bool = False,
) -> DecisionRecord:
    d = (TODAY - timedelta(days=days_ago)).isoformat()
    outcome = None if no_outcome else _out(
        overall, meal_confirmed=meal_confirmed, meal_ordered=meal_ordered, sleep=sleep
    )
    return DecisionRecord(
        user_id="test_user",
        date=d,
        context=_ctx(travel=travel),
        decision=_dec(),
        outcome=outcome,
    )


def _adherence(
    workout=80.0, meal=80.0, sleep=80.0, overall=80.0, total=10
) -> AdherenceMetrics:
    return AdherenceMetrics(
        workout_adherence=workout,
        meal_adherence=meal,
        sleep_adherence=sleep,
        overall_adherence=overall,
        total_days_tracked=total,
    )


# ── adherence_badge ───────────────────────────────────────────────

def test_badge_excellent():
    assert adherence_badge(85) == "Excellent"
    assert adherence_badge(100) == "Excellent"


def test_badge_good():
    assert adherence_badge(70) == "Good"
    assert adherence_badge(84.9) == "Good"


def test_badge_needs_attention():
    assert adherence_badge(50) == "Needs Attention"
    assert adherence_badge(69.9) == "Needs Attention"


def test_badge_at_risk():
    assert adherence_badge(49.9) == "At Risk"
    assert adherence_badge(0) == "At Risk"


# ── intensity helpers ─────────────────────────────────────────────

def test_reduce_intensity_high_to_moderate():
    assert _reduce_intensity("high") == "moderate"


def test_reduce_intensity_moderate_to_low():
    assert _reduce_intensity("moderate") == "low"


def test_reduce_intensity_low_stays_low():
    assert _reduce_intensity("low") == "low"


def test_increase_intensity_low_to_moderate():
    assert _increase_intensity("low") == "moderate"


def test_increase_intensity_high_stays_high():
    assert _increase_intensity("high") == "high"


def test_reduce_intensity_unknown_defaults_to_low():
    assert _reduce_intensity("unknown") == "low"


def test_increase_intensity_unknown_defaults_to_high():
    assert _increase_intensity("unknown") == "high"


# ── Streak calculation ────────────────────────────────────────────

def test_streak_empty_records():
    result = calculate_streak([])
    assert result.current_streak == 0
    assert result.best_streak == 0


def test_streak_spec_example():
    # Day 1=75%, Day 2=82%, Day 3=60%, Day 4=45% → current=3
    records = [
        _record(75, days_ago=3),
        _record(82, days_ago=2),
        _record(60, days_ago=1),
        _record(45, days_ago=0),   # most recent = below threshold
    ]
    result = calculate_streak(records)
    assert result.current_streak == 0   # most recent is 45 < 50, streak breaks immediately


def test_streak_spec_example_corrected():
    # From spec: Day 1=75%, Day 2=82%, Day 3=60%, Day 4=45%
    # "Current streak = 3" means going backwards from Day 4:
    # Day 4 = 45% < 50 → streak breaks → current=0
    # BUT if Day 4 is the oldest and Day 1 is most recent:
    # Day 1(most recent)=75%, Day 2=82%, Day 3=60% → these all pass, Day 4=45% breaks
    records = [
        _record(45, days_ago=3),   # oldest
        _record(60, days_ago=2),
        _record(82, days_ago=1),
        _record(75, days_ago=0),   # most recent
    ]
    result = calculate_streak(records)
    assert result.current_streak == 3
    assert result.best_streak == 3


def test_streak_all_passing():
    records = [_record(75, days_ago=i) for i in range(5)]
    result = calculate_streak(records)
    assert result.current_streak == 5
    assert result.best_streak == 5


def test_streak_all_failing():
    records = [_record(40, days_ago=i) for i in range(5)]
    result = calculate_streak(records)
    assert result.current_streak == 0
    assert result.best_streak == 0


def test_best_streak_higher_than_current():
    records = [
        _record(80, days_ago=6),
        _record(80, days_ago=5),
        _record(80, days_ago=4),
        _record(80, days_ago=3),   # best streak = 4 here
        _record(30, days_ago=2),   # breaks
        _record(70, days_ago=1),
        _record(70, days_ago=0),   # current streak = 2
    ]
    result = calculate_streak(records)
    assert result.current_streak == 2
    assert result.best_streak == 4


def test_streak_ignores_records_without_outcome():
    records = [
        _record(80, days_ago=2),
        _record(80, days_ago=1),
        _record(0, days_ago=0, no_outcome=True),  # no outcome — not counted
    ]
    result = calculate_streak(records)
    # Records with outcomes: 80%, 80% → current streak = 2
    assert result.current_streak == 2


def test_streak_exactly_50_counts():
    records = [_record(50, days_ago=0)]
    assert calculate_streak(records).current_streak == 1


def test_streak_49_does_not_count():
    records = [_record(49.9, days_ago=0)]
    assert calculate_streak(records).current_streak == 0


# ── Weekly trends ─────────────────────────────────────────────────

def test_trends_no_records():
    trends = generate_weekly_trends([], reference_date=TODAY)
    assert trends.workout_trend == 0.0
    assert trends.overall_trend == 0.0


def test_trends_only_this_week():
    # No previous week data → last_week avg = 0, delta = this_week avg
    records = [_record(80, days_ago=0), _record(60, days_ago=3)]
    trends = generate_weekly_trends(records, reference_date=TODAY)
    # this_week avg overall = (80+60)/2 = 70, last_week avg = 0 → trend = 70
    assert trends.overall_trend == 70.0


def test_trends_improvement():
    # last week avg = 50, this week avg = 80 → trend = +30
    records = [
        _record(80, days_ago=0),  # this week
        _record(80, days_ago=2),  # this week
        _record(50, days_ago=8),  # last week
        _record(50, days_ago=10), # last week
    ]
    trends = generate_weekly_trends(records, reference_date=TODAY)
    assert trends.overall_trend == 30.0


def test_trends_decline():
    records = [
        _record(40, days_ago=0),  # this week
        _record(40, days_ago=2),  # this week
        _record(80, days_ago=8),  # last week
        _record(80, days_ago=10), # last week
    ]
    trends = generate_weekly_trends(records, reference_date=TODAY)
    assert trends.overall_trend == -40.0


def test_trends_stable():
    records = [
        _record(70, days_ago=1),
        _record(70, days_ago=8),
    ]
    trends = generate_weekly_trends(records, reference_date=TODAY)
    assert trends.overall_trend == 0.0


def test_trends_no_outcome_records_excluded():
    records = [
        _record(80, days_ago=0),
        _record(0, days_ago=1, no_outcome=True),   # no outcome
    ]
    trends = generate_weekly_trends(records, reference_date=TODAY)
    assert trends.overall_trend == 80.0  # only the outcome record counts


# ── AT_RISK detection ─────────────────────────────────────────────

def test_at_risk_low_adherence():
    adherence = _adherence(overall=35.0, total=5)
    result = detect_at_risk([], adherence, TODAY)
    assert result.at_risk is True
    assert any("40%" in r for r in result.reasons)


def test_not_at_risk_adherence_40():
    adherence = _adherence(overall=40.0, total=5)
    result = detect_at_risk([], adherence, TODAY)
    # overall == 40 is NOT < 40, so condition 1 doesn't trigger
    assert not any("40%" in r for r in result.reasons)


def test_at_risk_3_consecutive_low():
    records = [
        _record(40, days_ago=0),
        _record(40, days_ago=1),
        _record(40, days_ago=2),
        _record(80, days_ago=3),  # before the streak
    ]
    result = detect_at_risk(records, _adherence(overall=55.0, total=4), TODAY)
    assert result.at_risk is True
    assert any("consecutive" in r for r in result.reasons)


def test_not_at_risk_2_consecutive_low():
    records = [
        _record(40, days_ago=0),
        _record(40, days_ago=1),
        _record(80, days_ago=2),
    ]
    result = detect_at_risk(records, _adherence(overall=55.0, total=3), TODAY)
    # Only 2 consecutive — should not trigger condition 2
    assert not any("consecutive" in r for r in result.reasons)


def test_at_risk_no_meal_confirmation_7_days():
    records = [
        _record(70, days_ago=0, meal_confirmed=False, meal_ordered=True),
        _record(70, days_ago=2, meal_confirmed=False, meal_ordered=True),
        _record(70, days_ago=5, meal_confirmed=False, meal_ordered=True),
    ]
    result = detect_at_risk(records, _adherence(overall=70.0, total=3), TODAY)
    assert result.at_risk is True
    assert any("meal" in r.lower() for r in result.reasons)


def test_not_at_risk_meal_confirmed_in_window():
    records = [
        _record(70, days_ago=0, meal_confirmed=True),
    ]
    result = detect_at_risk(records, _adherence(overall=70.0, total=1), TODAY)
    assert result.at_risk is False


def test_at_risk_no_tracked_days_no_trigger():
    adherence = _adherence(overall=0.0, total=0)
    result = detect_at_risk([], adherence, TODAY)
    # total_days_tracked == 0 → condition 1 should not trigger
    assert not any("40%" in r for r in result.reasons)


def test_adaptation_level_3_for_10_consecutive():
    records = [_record(30, days_ago=i) for i in range(12)]
    adherence = _adherence(overall=30.0, total=12)
    result = detect_at_risk(records, adherence, TODAY)
    assert result.adaptation_level == 3


def test_adaptation_level_2_for_6_consecutive():
    records = [_record(30, days_ago=i) for i in range(7)]
    adherence = _adherence(overall=50.0, total=7)
    result = detect_at_risk(records, adherence, TODAY)
    assert result.adaptation_level == 2


def test_adaptation_level_1_for_3_consecutive():
    records = [_record(30, days_ago=i) for i in range(3)]
    adherence = _adherence(overall=60.0, total=3)
    result = detect_at_risk(records, adherence, TODAY)
    assert result.adaptation_level == 1


# ── Adaptive recommendations ──────────────────────────────────────

def test_adaptive_maintain_when_on_track():
    records = [_record(75, days_ago=i) for i in range(5)]
    adherence = _adherence(overall=75.0, total=5)
    rec = generate_adaptive_recommendation(records, adherence, 45, "moderate", TODAY)
    assert rec.adaptation_level == "maintain"
    assert rec.adjusted_workout_duration == 45
    assert rec.adjusted_intensity == "moderate"
    assert rec.at_risk is False


def test_adaptive_reduce_level1():
    # 3 consecutive low days → level 1 reduction
    records = [_record(30, days_ago=i) for i in range(3)] + [_record(80, days_ago=3)]
    adherence = _adherence(overall=55.0, total=4)
    rec = generate_adaptive_recommendation(records, adherence, 60, "high", TODAY)
    assert rec.adaptation_level == "reduce"
    assert rec.adjusted_workout_duration == 30  # max(30, 60*0.5)
    assert rec.adjusted_intensity == "moderate"  # reduced from high
    assert rec.at_risk is True


def test_adaptive_reduce_minimum_30_min():
    # Even if 50% of 20 = 10, floor is 30
    records = [_record(30, days_ago=i) for i in range(3)] + [_record(80, days_ago=3)]
    adherence = _adherence(overall=55.0, total=4)
    rec = generate_adaptive_recommendation(records, adherence, 20, "moderate", TODAY)
    assert rec.adjusted_workout_duration == 30


def test_adaptive_minimal_level2():
    records = [_record(30, days_ago=i) for i in range(7)]
    adherence = _adherence(overall=30.0, total=7)
    rec = generate_adaptive_recommendation(records, adherence, 60, "high", TODAY)
    assert rec.adaptation_level == "minimal"
    assert rec.adjusted_workout_duration == max(15, round(60 * 0.25))
    assert rec.adjusted_intensity == "low"


def test_adaptive_minimum_viable_level3():
    records = [_record(30, days_ago=i) for i in range(12)]
    adherence = _adherence(overall=30.0, total=12)
    rec = generate_adaptive_recommendation(records, adherence, 60, "high", TODAY)
    assert rec.adaptation_level == "minimum_viable"
    assert rec.adjusted_workout_duration == 10
    assert rec.adjusted_intensity == "low"


def test_adaptive_progress_14_day_high_streak():
    records = [_record(85, days_ago=i) for i in range(14)]
    adherence = _adherence(overall=85.0, total=14)
    rec = generate_adaptive_recommendation(records, adherence, 60, "moderate", TODAY)
    assert rec.adaptation_level == "progress"
    assert rec.adjusted_workout_duration == round(60 * 1.1)
    assert rec.adjusted_intensity == "high"
    assert rec.at_risk is False


def test_adaptive_no_progress_below_14_days():
    records = [_record(85, days_ago=i) for i in range(13)]
    adherence = _adherence(overall=85.0, total=13)
    rec = generate_adaptive_recommendation(records, adherence, 60, "moderate", TODAY)
    assert rec.adaptation_level == "maintain"


def test_adaptive_no_progress_low_overall_adherence():
    # 14-day high streak but overall_adherence <= 80
    records = [_record(85, days_ago=i) for i in range(14)]
    adherence = _adherence(overall=79.0, total=14)
    rec = generate_adaptive_recommendation(records, adherence, 60, "moderate", TODAY)
    assert rec.adaptation_level == "maintain"


def test_adaptive_intensity_not_below_low():
    records = [_record(30, days_ago=i) for i in range(3)] + [_record(80, days_ago=3)]
    adherence = _adherence(overall=55.0, total=4)
    rec = generate_adaptive_recommendation(records, adherence, 45, "low", TODAY)
    assert rec.adjusted_intensity == "low"   # can't go below low


# ── Adherence insights ────────────────────────────────────────────

def test_insights_strong_workout_is_strength():
    records = [_record(80, days_ago=i) for i in range(5)]
    adherence = _adherence(workout=85.0, meal=60.0, sleep=60.0, overall=70.0)
    insights = generate_adherence_insights(records, adherence)
    assert any("workout" in s.lower() for s in insights.strengths)


def test_insights_low_meal_is_weakness():
    records = [_record(60, days_ago=i) for i in range(5)]
    adherence = _adherence(workout=70.0, meal=40.0, sleep=70.0, overall=60.0)
    insights = generate_adherence_insights(records, adherence)
    assert any("meal" in w.lower() for w in insights.weaknesses)
    assert any("meal" in r.lower() or "confirm" in r.lower() for r in insights.recommendations)


def test_insights_low_sleep_is_weakness():
    records = [_record(60, days_ago=i) for i in range(5)]
    adherence = _adherence(workout=75.0, meal=75.0, sleep=30.0, overall=65.0)
    insights = generate_adherence_insights(records, adherence)
    assert any("sleep" in w.lower() for w in insights.weaknesses)


def test_insights_travel_day_weakness():
    records = [
        _record(30, days_ago=0, travel=True),   # travel: low adherence
        _record(30, days_ago=1, travel=True),
        _record(85, days_ago=2, travel=False),
        _record(85, days_ago=3, travel=False),
        _record(85, days_ago=4, travel=False),
    ]
    adherence = _adherence(overall=63.0, total=5)
    insights = generate_adherence_insights(records, adherence)
    assert any("travel" in w.lower() for w in insights.weaknesses)
    assert any("travel" in r.lower() or "walk" in r.lower() for r in insights.recommendations)


def test_insights_7_day_streak_is_strength():
    records = [_record(75, days_ago=i) for i in range(8)]
    adherence = _adherence(overall=75.0, total=8)
    insights = generate_adherence_insights(records, adherence)
    assert any("streak" in s.lower() or "day" in s.lower() for s in insights.strengths)


def test_insights_defaults_when_no_data():
    insights = generate_adherence_insights([], _adherence(total=0, overall=0.0))
    assert len(insights.strengths) > 0
    assert len(insights.weaknesses) > 0
    assert len(insights.recommendations) > 0


# ── Dashboard ─────────────────────────────────────────────────────

def test_dashboard_returns_all_fields():
    records = [_record(75, days_ago=i) for i in range(5)]
    adherence = _adherence()
    dashboard = generate_dashboard(records, adherence, TODAY)
    assert isinstance(dashboard.adherence, AdherenceMetrics)
    assert isinstance(dashboard.streaks, StreakResult)
    assert isinstance(dashboard.trends, WeeklyTrends)
    assert isinstance(dashboard.insights, AdherenceInsights)
    assert isinstance(dashboard.at_risk, AtRiskResult)
    assert isinstance(dashboard.ai_insight, str)
    assert len(dashboard.ai_insight) > 10


def test_dashboard_at_risk_ai_insight():
    records = [_record(20, days_ago=i) for i in range(5)]
    adherence = _adherence(overall=20.0, total=5)
    dashboard = generate_dashboard(records, adherence, TODAY)
    assert "adapt" in dashboard.ai_insight.lower() or "friction" in dashboard.ai_insight.lower()


def test_dashboard_improving_ai_insight():
    records = [
        _record(90, days_ago=0),
        _record(90, days_ago=2),
        _record(50, days_ago=8),
        _record(50, days_ago=10),
    ]
    adherence = _adherence(overall=70.0, total=4)
    dashboard = generate_dashboard(records, adherence, TODAY)
    assert "improv" in dashboard.ai_insight.lower() or "momentum" in dashboard.ai_insight.lower() or "streak" in dashboard.ai_insight.lower()


def test_dashboard_declining_ai_insight():
    records = [
        _record(30, days_ago=0),
        _record(30, days_ago=2),
        _record(90, days_ago=8),
        _record(90, days_ago=10),
    ]
    adherence = _adherence(overall=60.0, total=4)
    dashboard = generate_dashboard(records, adherence, TODAY)
    # At_risk triggers first (3 consecutive low) → "friction" message
    assert len(dashboard.ai_insight) > 0


def test_dashboard_streak_ai_insight():
    records = [_record(75, days_ago=i) for i in range(8)]
    adherence = _adherence(overall=75.0, total=8)
    dashboard = generate_dashboard(records, adherence, TODAY)
    assert "streak" in dashboard.ai_insight.lower() or "habit" in dashboard.ai_insight.lower() or "consist" in dashboard.ai_insight.lower()


# ── ML dataset adherence features ────────────────────────────────

def _record_with_outcome_doc(overall: float, days_ago: int, user_id: str = "u1") -> dict:
    d = (TODAY - timedelta(days=days_ago)).isoformat()
    overall_val = calculate_overall_completion(overall, True, True, overall >= 50)
    return {
        "user_id": user_id,
        "date": d,
        "context": {"sleep_hours": 7, "stress_level": 4, "mood": 7, "meetings": 3,
                    "travel": False, "cycle_phase": "unknown", "previous_workout": None,
                    "goal": "test", "recovery_score": 70, "energy_score": 65, "stress_score": 72,
                    "context_flags": []},
        "decision": {"day_type": "normal", "workout_type": "strength",
                     "workout_duration_recommended": 45, "workout_intensity": "moderate",
                     "selected_lunch": "A", "selected_dinner": "B", "meal_calories": 1200,
                     "delivery_location": "home", "workout_time": "18:00", "sleep_target": "22:30"},
        "outcome": {"completed_workout": True, "workout_duration_completed": 30,
                    "workout_completion_percentage": overall,
                    "meal_ordered": True, "meal_confirmed": True,
                    "sleep_target_achieved": True,
                    "overall_completion_percentage": overall},
    }


def _mock_collection_with_docs(docs: list) -> MagicMock:
    col = MagicMock()
    cursor = MagicMock()
    cursor.__iter__ = MagicMock(return_value=iter(docs))
    col.find = MagicMock(return_value=cursor)
    return col


def test_ml_export_includes_adherence_fields():
    docs = [_record_with_outcome_doc(80.0, days_ago=0)]
    col = _mock_collection_with_docs(docs)
    dataset = export_training_dataset(col)
    assert len(dataset) == 1
    row = dataset[0]
    assert "adherence_score" in row
    assert "current_streak" in row
    assert "best_streak" in row
    assert "at_risk" in row


def test_ml_export_running_streak():
    # 3 passing days → streak builds up
    docs = [
        _record_with_outcome_doc(75.0, days_ago=2),
        _record_with_outcome_doc(80.0, days_ago=1),
        _record_with_outcome_doc(70.0, days_ago=0),
    ]
    col = _mock_collection_with_docs(docs)
    dataset = export_training_dataset(col)
    # Rows are sorted ascending, so last row = most recent
    assert dataset[2]["current_streak"] == 3
    assert dataset[2]["best_streak"] == 3


def test_ml_export_streak_breaks():
    docs = [
        _record_with_outcome_doc(80.0, days_ago=3),
        _record_with_outcome_doc(80.0, days_ago=2),
        _record_with_outcome_doc(20.0, days_ago=1),  # breaks streak
        _record_with_outcome_doc(80.0, days_ago=0),
    ]
    col = _mock_collection_with_docs(docs)
    dataset = export_training_dataset(col)
    assert dataset[3]["current_streak"] == 1   # most recent only
    assert dataset[3]["best_streak"] == 2       # first two


def test_ml_export_at_risk_flag():
    docs = [
        _record_with_outcome_doc(30.0, days_ago=2),
        _record_with_outcome_doc(30.0, days_ago=1),
        _record_with_outcome_doc(30.0, days_ago=0),
    ]
    col = _mock_collection_with_docs(docs)
    dataset = export_training_dataset(col)
    assert dataset[2]["at_risk"] is True


def test_ml_export_per_user_stats():
    # Two users should have independent running stats
    docs = [
        _record_with_outcome_doc(80.0, days_ago=1, user_id="alice"),
        _record_with_outcome_doc(20.0, days_ago=1, user_id="bob"),
    ]
    col = _mock_collection_with_docs(docs)
    dataset = export_training_dataset(col)
    by_user = {r["sleep_hours"]: r for r in dataset}  # both have same sleep; use a smarter lookup
    alice_row = next(r for r in dataset if r["overall_completion_percentage"] == 80.0)
    bob_row   = next(r for r in dataset if r["overall_completion_percentage"] == 20.0)
    assert alice_row["adherence_score"] == 80.0
    assert bob_row["adherence_score"] == 20.0
