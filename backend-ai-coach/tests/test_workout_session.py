"""
Tests for workout_session_service.py.

Covers: session creation, set tracking, progress persistence,
completion logic, calorie estimation, and edge cases.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import workout_session_service as wss
from workout_session_service import (
    start_session,
    record_progress,
    complete_session,
    get_session,
    estimate_calories,
)


# ── Helpers ───────────────────────────────────────────────────────

def fresh_session(total_sets: int = 6) -> wss.WorkoutSession:
    """Start a new session with unique workout_id to avoid state bleed."""
    import uuid
    return start_session(f"WO-{uuid.uuid4().hex[:6]}", "Test Workout", total_sets)


# ── Session start ─────────────────────────────────────────────────

def test_workout_session_starts():
    s = fresh_session(12)
    assert s.session_id.startswith("WS-")
    assert s.status == "in_progress"
    assert s.total_sets == 12
    assert s.completed_sets == 0
    assert s.completed_exercises == []
    assert s.completed_at is None
    assert s.duration_seconds is None
    assert s.calories_estimate is None


def test_session_id_is_unique():
    ids = {fresh_session().session_id for _ in range(20)}
    assert len(ids) == 20


def test_session_stored_in_store():
    s = fresh_session()
    fetched = get_session(s.session_id)
    assert fetched is not None
    assert fetched.session_id == s.session_id


def test_started_at_is_iso_string():
    s = fresh_session()
    # Should be parseable ISO 8601 with timezone
    from datetime import datetime
    dt = datetime.fromisoformat(s.started_at)
    assert dt.tzinfo is not None


# ── Set completion tracking ───────────────────────────────────────

def test_set_completion_tracked():
    s = fresh_session(6)
    updated = record_progress(s.session_id, "Squat", 2)
    assert updated.completed_sets == 2


def test_multiple_sets_accumulate():
    s = fresh_session(9)
    record_progress(s.session_id, "Squat", 3)
    record_progress(s.session_id, "Squat", 3)
    updated = record_progress(s.session_id, "Squat", 3)
    assert updated.completed_sets == 9


def test_exercise_added_to_list_once():
    s = fresh_session(6)
    record_progress(s.session_id, "Plank", 1)
    updated = record_progress(s.session_id, "Plank", 1)
    # "Plank" should appear exactly once
    assert updated.completed_exercises.count("Plank") == 1


def test_multiple_exercises_all_recorded():
    s = fresh_session(9)
    record_progress(s.session_id, "Squat", 3)
    record_progress(s.session_id, "Lunge", 3)
    updated = record_progress(s.session_id, "Deadlift", 3)
    assert set(updated.completed_exercises) == {"Squat", "Lunge", "Deadlift"}


# ── Progress persistence ──────────────────────────────────────────

def test_progress_persists():
    s = fresh_session(6)
    record_progress(s.session_id, "Squat", 1)
    fetched = get_session(s.session_id)
    assert fetched.completed_sets == 1
    assert "Squat" in fetched.completed_exercises


def test_progress_persists_across_multiple_calls():
    s = fresh_session(9)
    record_progress(s.session_id, "Press", 3)
    record_progress(s.session_id, "Row", 3)
    fetched = get_session(s.session_id)
    assert fetched.completed_sets == 6
    assert len(fetched.completed_exercises) == 2


def test_get_session_returns_none_for_unknown():
    result = get_session("WS-DOESNOTEXIST")
    assert result is None


# ── Completion ────────────────────────────────────────────────────

def test_completion_endpoint_works():
    s = fresh_session(6)
    completed = complete_session(s.session_id, 1800, "moderate")
    assert completed.status == "completed"
    assert completed.duration_seconds == 1800
    assert completed.calories_estimate == 210   # 7 kcal/min × 30 min


def test_completion_sets_completed_at():
    s = fresh_session(6)
    completed = complete_session(s.session_id, 600, "low")
    assert completed.completed_at is not None
    from datetime import datetime
    dt = datetime.fromisoformat(completed.completed_at)
    assert dt.tzinfo is not None


def test_completion_accepts_exercise_override():
    s = fresh_session(6)
    completed = complete_session(
        s.session_id, 900, "high",
        completed_exercises=["Squat", "Press"],
        completed_sets=6,
    )
    assert completed.completed_exercises == ["Squat", "Press"]
    assert completed.completed_sets == 6


def test_completion_persists_in_store():
    s = fresh_session(6)
    complete_session(s.session_id, 600, "moderate")
    fetched = get_session(s.session_id)
    assert fetched.status == "completed"


# ── Edge cases ────────────────────────────────────────────────────

def test_unknown_session_raises_value_error():
    with pytest.raises(ValueError, match="Session not found"):
        record_progress("WS-GHOST", "Squat", 1)


def test_unknown_session_complete_raises_value_error():
    with pytest.raises(ValueError, match="Session not found"):
        complete_session("WS-GHOST", 600, "moderate")


# ── Calorie estimation ────────────────────────────────────────────

def test_estimate_calories_low():
    assert estimate_calories("low", 3600) == 240    # 4 × 60

def test_estimate_calories_moderate():
    assert estimate_calories("moderate", 1800) == 210  # 7 × 30

def test_estimate_calories_high():
    assert estimate_calories("high", 600) == 100    # 10 × 10

def test_estimate_calories_unknown_intensity_uses_default():
    # Unknown intensity falls back to 6 kcal/min
    result = estimate_calories("ultra", 60)
    assert result == 6

def test_estimate_calories_zero_duration():
    assert estimate_calories("high", 0) == 0

def test_estimate_calories_case_insensitive():
    assert estimate_calories("LOW", 60) == estimate_calories("low", 60)
    assert estimate_calories("Moderate", 60) == estimate_calories("moderate", 60)
    assert estimate_calories("HIGH", 60) == estimate_calories("high", 60)
