"""
Tests for the Decision Tracking System.

Covers:
- DecisionRecord creation
- Outcome updates and completion percentage calculations
- Adherence metrics
- ML dataset export
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from decision_record_service import (
    RecordContext,
    RecordDecision,
    RecordOutcome,
    DecisionRecord,
    OutcomeInput,
    AdherenceMetrics,
    calculate_workout_completion,
    calculate_overall_completion,
    build_outcome,
    create_record,
    get_record,
    update_record_outcome,
    get_user_history,
    get_user_adherence,
    export_training_dataset,
)


# ── Fixtures ──────────────────────────────────────────────────────

def _make_context(**kwargs) -> RecordContext:
    defaults = dict(
        sleep_hours=7.5,
        stress_level=4,
        mood=7,
        meetings=3,
        travel=False,
        cycle_phase="unknown",
        previous_workout=None,
        goal="Muskelaufbau",
        recovery_score=72,
        energy_score=68,
        stress_score=75,
        context_flags=[],
    )
    defaults.update(kwargs)
    return RecordContext(**defaults)


def _make_decision(**kwargs) -> RecordDecision:
    defaults = dict(
        day_type="normal",
        workout_type="strength",
        workout_duration_recommended=45,
        workout_intensity="moderate",
        selected_lunch="Chicken Bowl",
        selected_dinner="Salmon Salad",
        meal_calories=1200,
        delivery_location="home",
        workout_time="18:00",
        sleep_target="22:30",
    )
    defaults.update(kwargs)
    return RecordDecision(**defaults)


def _make_record(user_id: str = "user_123", outcome=None) -> DecisionRecord:
    return DecisionRecord(
        user_id=user_id,
        date="2026-06-10",
        context=_make_context(),
        decision=_make_decision(),
        outcome=outcome,
    )


def _mock_collection(docs: list | None = None) -> MagicMock:
    docs = docs or []
    col = MagicMock()
    col.insert_one = MagicMock()
    col.find_one = MagicMock(return_value=None)
    col.update_one = MagicMock()
    # find(...).sort(...) must return an iterable of docs
    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=iter(docs))
    cursor.__iter__ = MagicMock(return_value=iter(docs))
    col.find = MagicMock(return_value=cursor)
    return col


# ── Workout completion percentage ─────────────────────────────────

def test_workout_completion_exact():
    assert calculate_workout_completion(20, 15) == 75.0


def test_workout_completion_full():
    assert calculate_workout_completion(30, 30) == 100.0


def test_workout_completion_over_100_capped():
    assert calculate_workout_completion(20, 25) == 100.0


def test_workout_completion_zero_recommended():
    assert calculate_workout_completion(0, 10) == 100.0
    assert calculate_workout_completion(0, 0) == 0.0


def test_workout_completion_zero_completed():
    assert calculate_workout_completion(45, 0) == 0.0


# ── Overall completion percentage ─────────────────────────────────

def test_overall_completion_example_from_spec():
    # Workout 75%, Meal 100%, Sleep 0% → 67.5%
    result = calculate_overall_completion(75.0, True, True, False)
    assert result == 67.5


def test_overall_completion_perfect():
    result = calculate_overall_completion(100.0, True, True, True)
    assert result == 100.0


def test_overall_completion_nothing_done():
    result = calculate_overall_completion(0.0, False, False, False)
    assert result == 0.0


def test_overall_completion_meal_only_ordered():
    # meal_ordered=True, meal_confirmed=False → 50% meal score
    # 0*0.5 + 50*0.3 + 0*0.2 = 15.0
    result = calculate_overall_completion(0.0, True, False, False)
    assert result == 15.0


def test_overall_completion_weights():
    # Workout 100%, Meal 0%, Sleep 100%
    # 100*0.5 + 0*0.3 + 100*0.2 = 70.0
    result = calculate_overall_completion(100.0, False, False, True)
    assert result == 70.0


# ── build_outcome ─────────────────────────────────────────────────

def test_build_outcome_basic():
    inp = OutcomeInput(
        completed_workout=True,
        workout_duration_completed=15,
        meal_ordered=True,
        meal_confirmed=True,
        sleep_target_achieved=False,
    )
    outcome = build_outcome(inp, recommended_duration=20)
    assert outcome.workout_completion_percentage == 75.0
    assert outcome.overall_completion_percentage == 67.5


def test_build_outcome_incomplete_workout():
    inp = OutcomeInput(
        completed_workout=False,
        workout_duration_completed=0,
        meal_ordered=False,
        meal_confirmed=False,
        sleep_target_achieved=False,
    )
    outcome = build_outcome(inp, recommended_duration=45)
    assert outcome.workout_completion_percentage == 0.0
    assert outcome.overall_completion_percentage == 0.0


def test_build_outcome_perfect_day():
    inp = OutcomeInput(
        completed_workout=True,
        workout_duration_completed=45,
        meal_ordered=True,
        meal_confirmed=True,
        sleep_target_achieved=True,
    )
    outcome = build_outcome(inp, recommended_duration=45)
    assert outcome.workout_completion_percentage == 100.0
    assert outcome.overall_completion_percentage == 100.0


# ── DecisionRecord creation ───────────────────────────────────────

def test_create_record_returns_id():
    col = _mock_collection()
    record = _make_record()
    record_id = create_record(col, record)
    assert record_id == record.id
    col.insert_one.assert_called_once()


def test_create_record_inserts_correct_doc():
    col = _mock_collection()
    record = _make_record(user_id="alice")
    create_record(col, record)
    inserted_doc = col.insert_one.call_args[0][0]
    assert inserted_doc["user_id"] == "alice"
    assert inserted_doc["outcome"] is None
    assert "context" in inserted_doc
    assert "decision" in inserted_doc


def test_get_record_found():
    record = _make_record()
    doc = record.model_dump()
    col = _mock_collection()
    col.find_one = MagicMock(return_value=doc)
    result = get_record(col, record.id)
    assert result is not None
    assert result.id == record.id
    assert result.user_id == record.user_id


def test_get_record_not_found():
    col = _mock_collection()
    col.find_one = MagicMock(return_value=None)
    result = get_record(col, "nonexistent-id")
    assert result is None


# ── Outcome updates ───────────────────────────────────────────────

def test_update_record_outcome():
    record = _make_record()
    outcome = RecordOutcome(
        completed_workout=True,
        workout_duration_completed=30,
        workout_completion_percentage=100.0,
        meal_ordered=True,
        meal_confirmed=True,
        sleep_target_achieved=True,
        overall_completion_percentage=100.0,
    )
    updated_doc = {**record.model_dump(), "outcome": outcome.model_dump()}
    col = _mock_collection()
    col.find_one = MagicMock(return_value=updated_doc)
    result = update_record_outcome(col, record.id, outcome)
    col.update_one.assert_called_once()
    assert result is not None
    assert result.outcome.overall_completion_percentage == 100.0  # type: ignore[union-attr]


# ── User history ──────────────────────────────────────────────────

def test_get_user_history_returns_records():
    record = _make_record(user_id="bob")
    col = _mock_collection(docs=[record.model_dump()])
    records = get_user_history(col, "bob")
    assert len(records) == 1
    assert records[0].user_id == "bob"


def test_get_user_history_empty():
    col = _mock_collection(docs=[])
    records = get_user_history(col, "nobody")
    assert records == []


def test_get_user_history_period_filter_7d():
    col = _mock_collection(docs=[])
    get_user_history(col, "user_1", period="7d")
    call_args = col.find.call_args[0][0]
    assert "date" in call_args
    assert "$gte" in call_args["date"]


def test_get_user_history_period_filter_all():
    col = _mock_collection(docs=[])
    get_user_history(col, "user_1", period="all")
    call_args = col.find.call_args[0][0]
    # No date filter for "all"
    assert "date" not in call_args


# ── Adherence metrics ─────────────────────────────────────────────

def _record_with_outcome(workout_pct, meal_ordered, meal_confirmed, sleep_achieved) -> dict:
    overall = calculate_overall_completion(workout_pct, meal_ordered, meal_confirmed, sleep_achieved)
    record = _make_record()
    outcome = RecordOutcome(
        completed_workout=workout_pct > 0,
        workout_duration_completed=int(workout_pct * 0.45),
        workout_completion_percentage=workout_pct,
        meal_ordered=meal_ordered,
        meal_confirmed=meal_confirmed,
        sleep_target_achieved=sleep_achieved,
        overall_completion_percentage=overall,
    )
    return {**record.model_dump(), "outcome": outcome.model_dump()}


def test_adherence_no_records():
    col = _mock_collection(docs=[])
    metrics = get_user_adherence(col, "user_1")
    assert metrics.total_days_tracked == 0
    assert metrics.overall_adherence == 0.0


def test_adherence_single_perfect_day():
    doc = _record_with_outcome(100.0, True, True, True)
    col = _mock_collection(docs=[doc])
    metrics = get_user_adherence(col, "user_1")
    assert metrics.total_days_tracked == 1
    assert metrics.workout_adherence == 100.0
    assert metrics.meal_adherence == 100.0
    assert metrics.sleep_adherence == 100.0
    assert metrics.overall_adherence == 100.0


def test_adherence_single_partial_day():
    # workout 75%, meal 100%, sleep 0% → overall 67.5
    doc = _record_with_outcome(75.0, True, True, False)
    col = _mock_collection(docs=[doc])
    metrics = get_user_adherence(col, "user_1")
    assert metrics.workout_adherence == 75.0
    assert metrics.meal_adherence == 100.0
    assert metrics.sleep_adherence == 0.0
    assert metrics.overall_adherence == 67.5


def test_adherence_ignores_records_without_outcome():
    # Record without outcome should not count toward total_days_tracked
    record_no_outcome = _make_record()
    col = _mock_collection(docs=[record_no_outcome.model_dump()])
    metrics = get_user_adherence(col, "user_1")
    assert metrics.total_days_tracked == 0


def test_adherence_averages_multiple_days():
    doc1 = _record_with_outcome(100.0, True, True, True)   # 100%
    doc2 = _record_with_outcome(0.0, False, False, False)  # 0%
    col = _mock_collection(docs=[doc1, doc2])
    metrics = get_user_adherence(col, "user_1")
    assert metrics.total_days_tracked == 2
    assert metrics.workout_adherence == 50.0
    assert metrics.overall_adherence == 50.0


# ── ML dataset export ─────────────────────────────────────────────

def test_export_training_dataset_empty():
    col = _mock_collection(docs=[])
    result = export_training_dataset(col)
    assert result == []


def test_export_training_dataset_structure():
    doc = _record_with_outcome(75.0, True, True, False)
    col = _mock_collection(docs=[doc])
    dataset = export_training_dataset(col)
    assert len(dataset) == 1
    row = dataset[0]
    # Context features
    assert "sleep_hours" in row
    assert "stress_level" in row
    assert "mood" in row
    assert "meetings" in row
    assert "travel" in row
    assert "cycle_phase" in row
    assert "recovery_score" in row
    # Decision features
    assert "day_type" in row
    assert "workout_type" in row
    assert "workout_duration_recommended" in row
    assert "workout_intensity" in row
    # Outcome labels
    assert "completed_workout" in row
    assert "workout_duration_completed" in row
    assert "workout_completion_percentage" in row
    assert "meal_ordered" in row
    assert "meal_confirmed" in row
    assert "sleep_target_achieved" in row
    assert "overall_completion_percentage" in row


def test_export_training_dataset_values():
    doc = _record_with_outcome(75.0, True, True, False)
    col = _mock_collection(docs=[doc])
    dataset = export_training_dataset(col)
    row = dataset[0]
    assert row["sleep_hours"] == 7.5
    assert row["stress_level"] == 4
    assert row["workout_completion_percentage"] == 75.0
    assert row["meal_ordered"] is True
    assert row["sleep_target_achieved"] is False


def test_export_only_includes_records_with_outcomes():
    col = _mock_collection(docs=[])
    # The query filters {outcome: {$ne: None}} — verified by checking the find call
    export_training_dataset(col)
    call_args = col.find.call_args[0][0]
    assert call_args == {"outcome": {"$ne": None}}
