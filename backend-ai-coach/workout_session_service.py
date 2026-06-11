"""
Workout Session Service.

In-memory session store for workout execution tracking (Phase 1 mock).
No database required — sessions live for the lifetime of the server process.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from pydantic import BaseModel


# ── Models ────────────────────────────────────────────────────────

class WorkoutSession(BaseModel):
    session_id: str
    workout_id: str
    workout_name: str
    started_at: str                    # ISO 8601
    completed_at: Optional[str] = None
    completed_exercises: List[str] = []
    completed_sets: int = 0
    total_sets: int = 0
    status: str = "in_progress"        # "in_progress" | "completed" | "abandoned"
    duration_seconds: Optional[int] = None
    calories_estimate: Optional[int] = None


# ── In-memory store ───────────────────────────────────────────────

_store: Dict[str, WorkoutSession] = {}


# ── Calorie Estimation ────────────────────────────────────────────

_KCAL_PER_MIN: Dict[str, int] = {
    "low":      4,
    "moderate": 7,
    "high":     10,
}


def estimate_calories(intensity: str, duration_seconds: int) -> int:
    """Estimate kcal burned based on intensity and duration."""
    rate = _KCAL_PER_MIN.get(intensity.lower(), 6)
    return round(rate * duration_seconds / 60)


# ── CRUD ──────────────────────────────────────────────────────────

def start_session(
    workout_id: str,
    workout_name: str,
    total_sets: int,
) -> WorkoutSession:
    """Create and store a new in-progress session. Returns the session."""
    session_id = f"WS-{uuid.uuid4().hex[:8].upper()}"
    session = WorkoutSession(
        session_id=session_id,
        workout_id=workout_id,
        workout_name=workout_name,
        started_at=datetime.now(timezone.utc).isoformat(),
        total_sets=total_sets,
    )
    _store[session_id] = session
    return session


def record_progress(
    session_id: str,
    exercise_name: str,
    sets_completed: int,
) -> WorkoutSession:
    """
    Record set completion for a given exercise.
    Adds the exercise name to completed_exercises (once) and increments
    completed_sets by sets_completed.
    """
    session = _store.get(session_id)
    if session is None:
        raise ValueError(f"Session not found: {session_id}")
    if session.status != "in_progress":
        raise ValueError(f"Session {session_id} is not in progress (status={session.status})")

    if exercise_name not in session.completed_exercises:
        session.completed_exercises = [*session.completed_exercises, exercise_name]
    session.completed_sets += sets_completed
    _store[session_id] = session
    return session


def complete_session(
    session_id: str,
    duration_seconds: int,
    intensity: str,
    completed_exercises: Optional[List[str]] = None,
    completed_sets: Optional[int] = None,
) -> WorkoutSession:
    """
    Mark a session as completed and calculate calories.
    Accepts final exercise/set counts to reconcile any sync gaps.
    """
    session = _store.get(session_id)
    if session is None:
        raise ValueError(f"Session not found: {session_id}")

    if completed_exercises is not None:
        session.completed_exercises = completed_exercises
    if completed_sets is not None:
        session.completed_sets = completed_sets

    session.completed_at = datetime.now(timezone.utc).isoformat()
    session.duration_seconds = duration_seconds
    session.calories_estimate = estimate_calories(intensity, duration_seconds)
    session.status = "completed"
    _store[session_id] = session
    return session


def get_session(session_id: str) -> Optional[WorkoutSession]:
    return _store.get(session_id)
