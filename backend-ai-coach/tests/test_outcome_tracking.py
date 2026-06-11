"""
Tests for Outcome Tracking Engine.
Covers: CRUD, trends, insights, decision effectiveness, ML export extension.
"""
import sys
import os
import pytest
from unittest.mock import MagicMock
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import outcome_tracking_service as ots
from outcome_tracking_service import (
    DailyOutcomes, WeeklyOutcomes, OutcomeRecord,
    save_daily_outcome, save_weekly_outcome, get_user_outcomes,
    calculate_outcome_trends, generate_outcome_insights,
    evaluate_decision_effectiveness,
)
import decision_record_service as drs
from decision_record_service import (
    DecisionRecord, RecordContext, RecordDecision, RecordOutcome,
    export_training_dataset,
)


# ── Mock helpers ──────────────────────────────────────────────────

def _mock_col(docs: list) -> MagicMock:
    col = MagicMock()
    col.find_one = MagicMock(return_value=None)
    col.update_one = MagicMock()
    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=iter(docs))
    col.find = MagicMock(return_value=cursor)
    return col


def _decision_col(records: list) -> MagicMock:
    col = MagicMock()
    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=iter([r.model_dump() for r in records]))
    col.find = MagicMock(return_value=cursor)
    return col


def _daily(mood=7.0, energy=7.0, stress=4.0, sleep=7.5, notes=None):
    return DailyOutcomes(mood=mood, energy=energy, stress=stress, sleep_hours=sleep, notes=notes)


def _weekly(weight=82.5, waist=90.0, bf=18.0):
    return WeeklyOutcomes(weight_kg=weight, waist_cm=waist, body_fat_percentage=bf)


def _outcome_doc(user_id, date_str, daily=None, weekly=None):
    return OutcomeRecord(
        user_id=user_id, date=date_str,
        daily_outcomes=daily, weekly_outcomes=weekly,
    ).model_dump()


REF = date(2026, 6, 10)


# ── Daily CRUD ────────────────────────────────────────────────────

def test_save_daily_creates_new_record():
    col = _mock_col([])
    record = save_daily_outcome(col, "u1", _daily(), date="2026-06-10")
    assert record.user_id == "u1"
    assert record.date == "2026-06-10"
    assert record.daily_outcomes is not None
    col.update_one.assert_called_once()


def test_save_daily_sets_correct_values():
    col = _mock_col([])
    daily = _daily(mood=9, energy=8, stress=2, sleep=8.5)
    record = save_daily_outcome(col, "u1", daily, date="2026-06-10")
    assert record.daily_outcomes.mood == 9
    assert record.daily_outcomes.energy == 8
    assert record.daily_outcomes.stress == 2
    assert record.daily_outcomes.sleep_hours == 8.5


def test_save_daily_upsert_true():
    col = _mock_col([])
    save_daily_outcome(col, "u1", _daily(), date="2026-06-10")
    assert col.update_one.call_args[1]["upsert"] is True


def test_save_daily_updates_existing_preserves_weekly():
    existing = _outcome_doc("u1", "2026-06-10", weekly=_weekly(weight=80.0))
    col = _mock_col([])
    col.find_one = MagicMock(return_value=existing)
    record = save_daily_outcome(col, "u1", _daily(mood=9), date="2026-06-10")
    assert record.daily_outcomes.mood == 9
    assert record.weekly_outcomes is not None
    assert record.weekly_outcomes.weight_kg == 80.0


def test_save_daily_notes_optional():
    col = _mock_col([])
    record = save_daily_outcome(col, "u1", _daily(notes="Good day"), date="2026-06-10")
    assert record.daily_outcomes.notes == "Good day"


# ── Weekly CRUD ───────────────────────────────────────────────────

def test_save_weekly_creates_new_record():
    col = _mock_col([])
    record = save_weekly_outcome(col, "u1", _weekly(weight=80.0), date="2026-06-10")
    assert record.weekly_outcomes.weight_kg == 80.0
    col.update_one.assert_called_once()


def test_save_weekly_partial_fields_allowed():
    col = _mock_col([])
    weekly = WeeklyOutcomes(weight_kg=78.0)
    record = save_weekly_outcome(col, "u1", weekly, date="2026-06-10")
    assert record.weekly_outcomes.weight_kg == 78.0
    assert record.weekly_outcomes.waist_cm is None
    assert record.weekly_outcomes.body_fat_percentage is None


def test_save_weekly_updates_existing_preserves_daily():
    existing = _outcome_doc("u1", "2026-06-10", daily=_daily(mood=8))
    col = _mock_col([])
    col.find_one = MagicMock(return_value=existing)
    record = save_weekly_outcome(col, "u1", _weekly(), date="2026-06-10")
    assert record.daily_outcomes is not None
    assert record.daily_outcomes.mood == 8


def test_save_weekly_upsert_true():
    col = _mock_col([])
    save_weekly_outcome(col, "u1", _weekly(), date="2026-06-10")
    assert col.update_one.call_args[1]["upsert"] is True


# ── get_user_outcomes ─────────────────────────────────────────────

def test_get_user_outcomes_returns_records():
    docs = [
        _outcome_doc("u1", "2026-06-08", daily=_daily()),
        _outcome_doc("u1", "2026-06-09", daily=_daily()),
    ]
    col = _mock_col(docs)
    results = get_user_outcomes(col, "u1")
    assert len(results) == 2
    assert all(isinstance(r, OutcomeRecord) for r in results)


def test_get_user_outcomes_empty():
    col = _mock_col([])
    assert get_user_outcomes(col, "u1") == []


def test_get_user_outcomes_days_filter_adds_gte():
    col = _mock_col([])
    get_user_outcomes(col, "u1", days=7)
    query = col.find.call_args[0][0]
    assert "$gte" in query.get("date", {})


# ── calculate_outcome_trends ──────────────────────────────────────

def _trends_col(this_week_vals, prev_week_vals):
    """Build col with this-week docs (days 4-10) and prev-week docs (days -3 to +3)."""
    this_docs = [
        _outcome_doc("u1", f"2026-06-{d:02d}", daily=DailyOutcomes(**v))
        for d, v in zip(range(4, 11), this_week_vals)
    ]
    prev_docs = [
        _outcome_doc("u1", f"2026-06-0{d}", daily=DailyOutcomes(**v))
        for d, v in zip(range(1, 4), prev_week_vals[:3])
    ]
    return _mock_col(prev_docs + this_docs)


_HI = dict(mood=8.0, energy=8.0, stress=3.0, sleep_hours=8.0)
_LO = dict(mood=5.0, energy=5.0, stress=7.0, sleep_hours=6.0)


def test_trends_mood_improves():
    col = _trends_col([_HI]*7, [_LO]*3)
    t = calculate_outcome_trends(col, "u1", REF)
    assert t.mood_change is not None and t.mood_change > 0


def test_trends_stress_decreases():
    col = _trends_col([_HI]*7, [_LO]*3)
    t = calculate_outcome_trends(col, "u1", REF)
    assert t.stress_change is not None and t.stress_change < 0


def test_trends_energy_improves():
    col = _trends_col([_HI]*7, [_LO]*3)
    t = calculate_outcome_trends(col, "u1", REF)
    assert t.energy_change is not None and t.energy_change > 0


def test_trends_no_previous_week_returns_none():
    docs = [_outcome_doc("u1", "2026-06-10", daily=_daily())]
    col = _mock_col(docs)
    t = calculate_outcome_trends(col, "u1", REF)
    assert t.mood_change is None


def test_trends_empty_all_none():
    col = _mock_col([])
    t = calculate_outcome_trends(col, "u1", REF)
    assert t.mood_change is None
    assert t.weight_change is None


def test_trends_weight_oldest_vs_latest():
    docs = [
        _outcome_doc("u1", "2026-05-01", weekly=_weekly(weight=85.0)),
        _outcome_doc("u1", "2026-06-01", weekly=_weekly(weight=82.0)),
    ]
    col = _mock_col(docs)
    t = calculate_outcome_trends(col, "u1", REF)
    assert t.weight_change == pytest.approx(-3.0)


def test_trends_weight_single_entry_none():
    docs = [_outcome_doc("u1", "2026-06-01", weekly=_weekly(weight=85.0))]
    col = _mock_col(docs)
    t = calculate_outcome_trends(col, "u1", REF)
    assert t.weight_change is None


def test_trends_waist_decrease():
    docs = [
        _outcome_doc("u1", "2026-05-01", weekly=_weekly(waist=95.0)),
        _outcome_doc("u1", "2026-06-01", weekly=_weekly(waist=92.0)),
    ]
    col = _mock_col(docs)
    t = calculate_outcome_trends(col, "u1", REF)
    assert t.waist_change == pytest.approx(-3.0)


def test_trends_exact_values():
    col = _trends_col([_HI]*7, [_LO]*3)
    t = calculate_outcome_trends(col, "u1", REF)
    assert t.mood_change   == pytest.approx(3.0)
    assert t.energy_change == pytest.approx(3.0)
    assert t.stress_change == pytest.approx(-4.0)
    assert t.sleep_change  == pytest.approx(2.0)


# ── generate_outcome_insights ─────────────────────────────────────

def test_insights_wins_when_improving():
    col = _trends_col([_HI]*7, [_LO]*3)
    ins = generate_outcome_insights(col, "u1", REF)
    assert len(ins.wins) > 0


def test_insights_warnings_when_declining():
    col = _trends_col([_LO]*7, [_HI]*3)
    ins = generate_outcome_insights(col, "u1", REF)
    assert len(ins.warnings) > 0


def test_insights_no_data_default_summary():
    col = _mock_col([])
    ins = generate_outcome_insights(col, "u1", REF)
    assert "Not enough data" in ins.summary
    assert ins.wins == [] and ins.warnings == []


def test_insights_positive_summary_more_wins():
    col = _trends_col([_HI]*7, [_LO]*3)
    ins = generate_outcome_insights(col, "u1", REF)
    assert "positive" in ins.summary


def test_insights_attention_summary_more_warnings():
    col = _trends_col([_LO]*7, [_HI]*3)
    ins = generate_outcome_insights(col, "u1", REF)
    assert "attention" in ins.summary or "areas" in ins.summary


def test_insights_weight_win_when_decreasing():
    docs = [
        _outcome_doc("u1", "2026-05-01", weekly=_weekly(weight=90.0)),
        _outcome_doc("u1", "2026-06-01", weekly=_weekly(weight=87.0)),
    ]
    col = _mock_col(docs)
    ins = generate_outcome_insights(col, "u1", REF)
    assert any("Weight" in w for w in ins.wins)


def test_insights_stress_below_threshold_no_win():
    # stress change of 0.1 — below threshold of 0.3
    col = _trends_col(
        [dict(mood=7, energy=7, stress=4.9, sleep_hours=7)]*7,
        [dict(mood=7, energy=7, stress=5.0, sleep_hours=7)]*3,
    )
    ins = generate_outcome_insights(col, "u1", REF)
    assert not any("Stress" in w for w in ins.wins)


# ── evaluate_decision_effectiveness ──────────────────────────────

def _make_dr(date_str, day_type, completed_workout=False, meal_confirmed=False):
    ctx = RecordContext(
        sleep_hours=7, stress_level=5, mood=7, meetings=2,
        travel=False, cycle_phase=None, previous_workout=None,
        goal="fitness", recovery_score=70, energy_score=70,
        stress_score=70, context_flags=[],
    )
    dec = RecordDecision(
        day_type=day_type, workout_type="strength",
        workout_duration_recommended=45, workout_intensity="moderate",
        selected_lunch="Salad", selected_dinner="Bowl",
        meal_calories=800, delivery_location="home",
        workout_time="18:00", sleep_target="23:00",
    )
    outcome = RecordOutcome(
        completed_workout=completed_workout,
        workout_duration_completed=40 if completed_workout else 0,
        workout_completion_percentage=88.9 if completed_workout else 0.0,
        meal_ordered=meal_confirmed,
        meal_confirmed=meal_confirmed,
        sleep_target_achieved=True,
        overall_completion_percentage=80.0,
    )
    return DecisionRecord(user_id="u1", date=date_str, context=ctx, decision=dec, outcome=outcome)


def test_effectiveness_no_data_neutral_50():
    outcomes_col = _mock_col([])
    decisions_col = _decision_col([])
    eff = evaluate_decision_effectiveness(outcomes_col, decisions_col, "u1")
    assert eff.recovery_day_effectiveness == 50
    assert eff.meal_effectiveness == 50
    assert eff.workout_effectiveness == 50


def test_effectiveness_recovery_lowers_stress_100():
    dr = _make_dr("2026-06-09", "recovery")
    today = _outcome_doc("u1", "2026-06-09", daily=_daily(stress=7))
    nxt   = _outcome_doc("u1", "2026-06-10", daily=_daily(stress=4))
    outcomes_col = _mock_col([today, nxt])
    decisions_col = _decision_col([dr])
    eff = evaluate_decision_effectiveness(outcomes_col, decisions_col, "u1")
    assert eff.recovery_day_effectiveness == 100


def test_effectiveness_recovery_stress_unchanged_0():
    dr = _make_dr("2026-06-09", "recovery")
    today = _outcome_doc("u1", "2026-06-09", daily=_daily(stress=4))
    nxt   = _outcome_doc("u1", "2026-06-10", daily=_daily(stress=7))
    outcomes_col = _mock_col([today, nxt])
    decisions_col = _decision_col([dr])
    eff = evaluate_decision_effectiveness(outcomes_col, decisions_col, "u1")
    assert eff.recovery_day_effectiveness == 0


def test_effectiveness_meal_confirmed_energy_up_100():
    dr = _make_dr("2026-06-09", "normal", meal_confirmed=True)
    today = _outcome_doc("u1", "2026-06-09", daily=_daily(energy=5))
    nxt   = _outcome_doc("u1", "2026-06-10", daily=_daily(energy=8))
    outcomes_col = _mock_col([today, nxt])
    decisions_col = _decision_col([dr])
    eff = evaluate_decision_effectiveness(outcomes_col, decisions_col, "u1")
    assert eff.meal_effectiveness == 100


def test_effectiveness_workout_mood_up_100():
    dr = _make_dr("2026-06-09", "performance", completed_workout=True)
    today = _outcome_doc("u1", "2026-06-09", daily=_daily(mood=5))
    nxt   = _outcome_doc("u1", "2026-06-10", daily=_daily(mood=8))
    outcomes_col = _mock_col([today, nxt])
    decisions_col = _decision_col([dr])
    eff = evaluate_decision_effectiveness(outcomes_col, decisions_col, "u1")
    assert eff.workout_effectiveness == 100


def test_effectiveness_missing_next_day_skipped():
    dr = _make_dr("2026-06-09", "recovery")
    today = _outcome_doc("u1", "2026-06-09", daily=_daily(stress=7))
    # no next-day outcome → skipped → neutral
    outcomes_col = _mock_col([today])
    decisions_col = _decision_col([dr])
    eff = evaluate_decision_effectiveness(outcomes_col, decisions_col, "u1")
    assert eff.recovery_day_effectiveness == 50


def test_effectiveness_partial_score():
    dr1 = _make_dr("2026-06-08", "recovery")
    dr2 = _make_dr("2026-06-09", "recovery")
    # day1: stress drops (win), day2: stress rises (loss)
    docs = [
        _outcome_doc("u1", "2026-06-08", daily=_daily(stress=7)),
        _outcome_doc("u1", "2026-06-09", daily=_daily(stress=4)),
        _outcome_doc("u1", "2026-06-10", daily=_daily(stress=8)),
    ]
    outcomes_col = _mock_col(docs)
    decisions_col = _decision_col([dr1, dr2])
    eff = evaluate_decision_effectiveness(outcomes_col, decisions_col, "u1")
    assert eff.recovery_day_effectiveness == 50


# ── ML export extension ───────────────────────────────────────────

def _decision_doc(user_id, date_str, day_type="normal"):
    ctx = RecordContext(
        sleep_hours=7, stress_level=5, mood=7, meetings=2,
        travel=False, cycle_phase=None, previous_workout=None,
        goal="fitness", recovery_score=70, energy_score=70,
        stress_score=70, context_flags=[],
    )
    dec = RecordDecision(
        day_type=day_type, workout_type="strength",
        workout_duration_recommended=45, workout_intensity="moderate",
        selected_lunch="Salad", selected_dinner="Bowl",
        meal_calories=800, delivery_location="home",
        workout_time="18:00", sleep_target="23:00",
    )
    outcome = RecordOutcome(
        completed_workout=True, workout_duration_completed=40,
        workout_completion_percentage=88.9, meal_ordered=True,
        meal_confirmed=True, sleep_target_achieved=True,
        overall_completion_percentage=80.0,
    )
    return DecisionRecord(
        user_id=user_id, date=date_str, context=ctx, decision=dec, outcome=outcome
    ).model_dump()


def _decision_mock_col(docs):
    col = MagicMock()
    col.find = MagicMock(return_value=iter(docs))
    return col


def _outcome_mock_col(docs):
    col = MagicMock()
    col.find = MagicMock(return_value=iter(docs))
    return col


def test_ml_export_includes_outcome_fields_when_col_provided():
    dec_doc = _decision_doc("u1", "2026-06-09")
    out_doc = _outcome_doc("u1", "2026-06-09", daily=_daily(mood=8, energy=7, stress=3, sleep=8.0))
    dec_col = _decision_mock_col([dec_doc])
    out_col = _outcome_mock_col([out_doc])
    rows = export_training_dataset(dec_col, out_col)
    assert len(rows) == 1
    row = rows[0]
    assert row["outcome_mood"] == 8
    assert row["outcome_energy"] == 7
    assert row["outcome_stress"] == 3
    assert row["outcome_sleep_hours"] == 8.0


def test_ml_export_next_day_fields():
    dec_doc = _decision_doc("u1", "2026-06-09")
    out_today = _outcome_doc("u1", "2026-06-09", daily=_daily(mood=5))
    out_next  = _outcome_doc("u1", "2026-06-10", daily=_daily(mood=9))
    dec_col = _decision_mock_col([dec_doc])
    out_col = _outcome_mock_col([out_today, out_next])
    rows = export_training_dataset(dec_col, out_col)
    assert rows[0]["mood_next_day"] == 9


def test_ml_export_weight_field():
    dec_doc = _decision_doc("u1", "2026-06-09")
    out_doc = _outcome_doc("u1", "2026-06-09", weekly=_weekly(weight=82.5))
    dec_col = _decision_mock_col([dec_doc])
    out_col = _outcome_mock_col([out_doc])
    rows = export_training_dataset(dec_col, out_col)
    assert rows[0]["weight_kg"] == 82.5


def test_ml_export_outcome_trend_score_computed():
    dec_doc = _decision_doc("u1", "2026-06-09")
    out_doc = _outcome_doc("u1", "2026-06-09", daily=_daily(mood=8, energy=7, stress=3))
    dec_col = _decision_mock_col([dec_doc])
    out_col = _outcome_mock_col([out_doc])
    rows = export_training_dataset(dec_col, out_col)
    # composite = (8 + 7 + (10-3)) / 3 = 22/3 ≈ 7.33
    assert rows[0]["outcome_trend_score"] == pytest.approx(7.33, abs=0.01)


def test_ml_export_no_outcome_col_fields_are_none():
    dec_doc = _decision_doc("u1", "2026-06-09")
    dec_col = _decision_mock_col([dec_doc])
    rows = export_training_dataset(dec_col, None)
    assert rows[0]["outcome_mood"] is None
    assert rows[0]["mood_next_day"] is None
    assert rows[0]["outcome_trend_score"] is None


def test_ml_export_missing_outcome_doc_fields_none():
    dec_doc = _decision_doc("u1", "2026-06-09")
    # outcome for different date — no match for 2026-06-09
    out_doc = _outcome_doc("u1", "2026-06-01", daily=_daily())
    dec_col = _decision_mock_col([dec_doc])
    out_col = _outcome_mock_col([out_doc])
    rows = export_training_dataset(dec_col, out_col)
    assert rows[0]["outcome_mood"] is None
    assert rows[0]["mood_next_day"] is None


def test_ml_export_running_trend_score_accumulates():
    dec1 = _decision_doc("u1", "2026-06-08")
    dec2 = _decision_doc("u1", "2026-06-09")
    out1 = _outcome_doc("u1", "2026-06-08", daily=_daily(mood=6, energy=6, stress=6))
    out2 = _outcome_doc("u1", "2026-06-09", daily=_daily(mood=8, energy=8, stress=2))
    dec_col = _decision_mock_col([dec1, dec2])
    out_col = _outcome_mock_col([out1, out2])
    rows = export_training_dataset(dec_col, out_col)
    # row1 composite = (6+6+4)/3 = 5.33, row2 composite = (8+8+8)/3 = 8.0
    # running avg after row2 = (5.33 + 8.0) / 2 ≈ 6.67
    assert rows[0]["outcome_trend_score"] == pytest.approx(16/3, abs=0.01)
    assert rows[1]["outcome_trend_score"] == pytest.approx((16/3 + 8.0) / 2, abs=0.02)
