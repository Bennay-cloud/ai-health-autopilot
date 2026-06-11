"""
Integration tests: calendar_events flow from DailyDecisionRequest → schedule.

These tests verify that calendar events sent in daily_context reach the
schedule engine and produce avoidance behaviour in the final response.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from daily_decision_engine import (
    DailyContext,
    UserProfileInput,
    DailyDecisionRequest,
    generate_daily_decision,
)
from schedule_service import CalendarEvent, _to_min


# ── Helpers ───────────────────────────────────────────────────────

def make_request(
    sleep_hours: float = 8.0,
    stress_level: int = 3,
    meetings_count: int = 2,
    calendar_events: list = None,
) -> DailyDecisionRequest:
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
            calendar_events=calendar_events or [],
        ),
    )


def event(title: str, start: str, end: str) -> CalendarEvent:
    return CalendarEvent(title=title, start_time=start, end_time=end)


# ── calendar_events flows through to response ─────────────────────

def test_no_calendar_events_no_warnings():
    """Empty calendar → schedule engine should produce no warnings."""
    result = make_request()
    response = generate_daily_decision(result)
    workout_warnings = [w for w in response.schedule_warnings if "Training" in w]
    assert len(workout_warnings) == 0


def test_calendar_events_reach_schedule_engine():
    """calendar_events in request should be reflected in schedule_warnings when day is fully blocked."""
    req = make_request(
        calendar_events=[event("Ganztag", "06:00", "21:00")],
    )
    response = generate_daily_decision(req)
    # Full-day block → schedule engine cannot find a workout slot → warning issued
    assert any("Training" in w or "Trainingsslot" in w for w in response.schedule_warnings)


def test_response_has_schedule_warning_fields():
    """schedule_warnings must always be present in the response (even if empty)."""
    response = generate_daily_decision(make_request())
    assert hasattr(response, "schedule_warnings")
    assert isinstance(response.schedule_warnings, list)


def test_response_has_explicit_time_fields():
    """lunch_delivery_time, dinner_delivery_time, workout_time are present."""
    response = generate_daily_decision(make_request())
    assert response.lunch_delivery_time is not None
    assert response.dinner_delivery_time is not None
    assert response.workout_time is not None
    # All are valid HH:MM strings
    for t in [response.lunch_delivery_time, response.dinner_delivery_time, response.workout_time]:
        assert len(t) == 5
        assert t[2] == ":"


# ── Busy Meeting Day preset ───────────────────────────────────────

def test_busy_day_lunch_avoids_meetings():
    """
    'Busy Meeting Day' preset blocks lunch window (12:00–13:30).
    The returned lunch_delivery_time should not place eating during the meeting.
    """
    busy_events = [
        event("Standup",         "09:00", "09:30"),
        event("Sprint Planning", "10:00", "11:30"),
        event("Business Lunch",  "12:00", "13:30"),
        event("Client Call",     "14:00", "15:30"),
        event("Retrospektive",   "16:00", "17:00"),
    ]
    response = generate_daily_decision(make_request(calendar_events=busy_events))

    lunch_eating_min = _to_min(response.lunch_delivery_time) + 20
    meeting_start    = _to_min("12:00")
    meeting_end      = _to_min("13:30")

    # Eating slot (30 min) must not overlap with the Business Lunch meeting
    overlaps = lunch_eating_min < meeting_end and (lunch_eating_min + 30) > meeting_start
    assert not overlaps, (
        f"Lunch eating at {response.lunch_delivery_time} (+20min) overlaps meeting 12:00–13:30"
    )


# ── Lunch Blocked preset ──────────────────────────────────────────

def test_lunch_blocked_preset_moves_lunch_time():
    """'Lunch Blocked' (11:30–14:00) should move lunch outside that window."""
    lunch_blocked = [event("Business Lunch", "11:30", "14:00")]
    response_blocked = generate_daily_decision(make_request(calendar_events=lunch_blocked))
    response_clear   = generate_daily_decision(make_request())

    eating_blocked = _to_min(response_blocked.lunch_delivery_time) + 20
    eating_clear   = _to_min(response_clear.lunch_delivery_time) + 20

    # Blocked case: eating must be outside 11:30–14:00
    block_start = _to_min("11:30")
    block_end   = _to_min("14:00")
    overlaps = eating_blocked < block_end and (eating_blocked + 30) > block_start
    assert not overlaps

    # Clear case: eating at default (12:30)
    assert eating_clear == _to_min("12:30")


# ── No Workout Window preset ──────────────────────────────────────

def test_no_workout_window_generates_warning():
    """Blocking the full day (06:00–21:00) must trigger a workout slot warning."""
    no_workout = [event("Ganztagesblock", "06:00", "21:00")]
    response = generate_daily_decision(make_request(calendar_events=no_workout))
    assert len(response.schedule_warnings) > 0
    assert any("Training" in w or "Trainingsslot" in w for w in response.schedule_warnings)


def test_no_workout_window_uses_fallback_time():
    """With a full-day block, workout_time should fall back to 17:30."""
    no_workout = [event("Ganztagesblock", "06:00", "21:00")]
    response = generate_daily_decision(make_request(calendar_events=no_workout))
    assert response.workout_time == "17:30"


# ── Light Day preset ──────────────────────────────────────────────

def test_light_day_no_warnings():
    """'Light Day' (one 30-min morning meeting) should not cause any schedule warnings."""
    light = [event("Kurzes Check-in", "09:00", "09:30")]
    response = generate_daily_decision(make_request(calendar_events=light))
    assert len(response.schedule_warnings) == 0


# ── Schedule items reflect events ────────────────────────────────

def test_schedule_items_include_workout_entry():
    """The schedule list must always contain a workout/recovery item."""
    response = generate_daily_decision(make_request())
    workout_items = [i for i in response.schedule if i.type == "workout"]
    assert len(workout_items) == 1


def test_schedule_items_are_sorted():
    """Schedule items must arrive in chronological order."""
    busy_events = [
        event("Morning Block", "08:00", "12:00"),
        event("Afternoon Block", "13:00", "17:00"),
    ]
    response = generate_daily_decision(make_request(calendar_events=busy_events))
    times = [_to_min(item.time) for item in response.schedule]
    assert times == sorted(times), "Schedule items must be sorted chronologically"


def test_calendar_events_do_not_break_existing_fields():
    """Adding calendar_events must not corrupt any existing response fields."""
    events = [event("Meeting", "12:00", "13:00")]
    response = generate_daily_decision(make_request(calendar_events=events))

    assert response.day_type in ("recovery", "normal", "performance")
    assert response.selected_workout is not None
    assert response.selected_lunch is not None
    assert response.selected_dinner is not None
    assert response.recovery_score >= 0
    assert isinstance(response.coaching_message, str)
