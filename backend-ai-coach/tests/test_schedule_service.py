import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from schedule_service import (
    CalendarEvent,
    ScheduleItem,
    DailySchedule,
    build_daily_schedule,
    _to_min,
    _to_str,
    _is_blocked,
    _find_free_slot,
)


# ── Helpers ───────────────────────────────────────────────────────

def event(title: str, start: str, end: str) -> CalendarEvent:
    return CalendarEvent(title=title, start_time=start, end_time=end)


def schedule(**kwargs) -> DailySchedule:
    defaults = dict(day_type="normal", workout_duration_minutes=45)
    defaults.update(kwargs)
    return build_daily_schedule(**defaults)


# ── Internal helpers ──────────────────────────────────────────────

def test_to_min_and_back():
    assert _to_min("07:30") == 450
    assert _to_str(450) == "07:30"
    assert _to_str(_to_min("00:00")) == "00:00"
    assert _to_str(_to_min("23:59")) == "23:59"


def test_is_blocked_overlap():
    events = [event("Meeting", "12:00", "13:00")]
    assert _is_blocked(_to_min("12:00"), 30, events)   # starts at meeting start
    assert _is_blocked(_to_min("12:30"), 30, events)   # within meeting
    assert _is_blocked(_to_min("11:45"), 30, events)   # overlaps start


def test_is_blocked_no_overlap():
    events = [event("Meeting", "12:00", "13:00")]
    assert not _is_blocked(_to_min("11:00"), 30, events)  # ends exactly at 11:30
    assert not _is_blocked(_to_min("13:00"), 30, events)  # starts at meeting end
    assert not _is_blocked(_to_min("10:00"), 60, events)  # ends at 11:00


def test_find_free_slot_returns_preferred_when_clear():
    slot = _find_free_slot(11 * 60 + 30, 14 * 60 + 30, 30, [], preferred=12 * 60 + 30)
    assert slot == 12 * 60 + 30


def test_find_free_slot_skips_blocked_preferred():
    events = [event("Meeting", "12:00", "13:30")]
    # preferred 12:30 is blocked (12:30+30=13:00 overlaps 12:00-13:30)
    slot = _find_free_slot(11 * 60 + 30, 14 * 60 + 30, 30, events, preferred=12 * 60 + 30)
    # Should fall back to 11:30 (first free slot from window_start)
    assert slot == 11 * 60 + 30


def test_find_free_slot_returns_none_when_fully_blocked():
    events = [event("Block", "05:00", "23:00")]
    slot = _find_free_slot(6 * 60, 21 * 60, 60, events)
    assert slot is None


# ── Empty calendar — default schedule ────────────────────────────

def test_empty_calendar_returns_valid_schedule():
    s = schedule()
    assert isinstance(s, DailySchedule)
    assert len(s.items) > 0
    assert len(s.warnings) == 0


def test_empty_calendar_lunch_in_window():
    s = schedule()
    # lunch_delivery_time is 20 min before eating; eating should be in 11:30-14:30
    eating_min = _to_min(s.lunch_delivery_time) + 20
    assert 11 * 60 + 30 <= eating_min <= 14 * 60 + 30


def test_empty_calendar_schedule_is_sorted():
    s = schedule(wake_time="06:30")
    times = [_to_min(item.time) for item in s.items]
    assert times == sorted(times)


def test_empty_calendar_has_required_types():
    s = schedule()
    types = {item.type for item in s.items}
    assert "meal" in types        # breakfast
    assert "delivery" in types    # lunch + dinner deliveries
    assert "workout" in types     # workout/regeneration
    assert "recovery" in types    # sleep target


def test_empty_calendar_default_lunch_near_1230():
    s = schedule()
    # With no events, lunch delivery should be around 12:10 (12:30 eating - 20 min)
    assert s.lunch_delivery_time == "12:10"


# ── Lunch avoids meeting ──────────────────────────────────────────

def test_lunch_avoids_meeting_at_1230():
    """A meeting during the preferred lunch time should push lunch to a free slot."""
    events = [event("Standup", "12:00", "13:30")]
    s = schedule(calendar_events=events)
    eating_min = _to_min(s.lunch_delivery_time) + 20
    # The eating slot (30 min) must not overlap with the meeting
    assert not (_is_blocked(eating_min, 30, events))


def test_lunch_avoids_all_day_meeting():
    """If the entire lunch window is blocked, a warning is issued and 12:30 is used."""
    events = [event("Offsite", "11:00", "15:00")]
    s = schedule(calendar_events=events)
    assert any("Mittagsslot" in w for w in s.warnings)
    # Fallback time used
    assert s.lunch_delivery_time == "12:10"


# ── Workout fits available free window ───────────────────────────

def test_workout_fits_within_unblocked_window():
    """With morning and late evening blocked, workout should land in the free afternoon window."""
    events = [
        event("Morning block", "06:00", "16:00"),
        event("Evening block", "19:00", "21:00"),
    ]
    s = schedule(calendar_events=events, workout_duration_minutes=45)
    workout_min = _to_min(s.workout_time)
    # Free window is 16:00-19:00; workout (45 min) must fit there
    assert 16 * 60 <= workout_min < 19 * 60
    # And it must not overlap any event
    assert not _is_blocked(workout_min, 45, events)


def test_workout_time_in_response_matches_schedule_item():
    s = schedule()
    workout_item = next((i for i in s.items if i.type == "workout"), None)
    assert workout_item is not None
    assert workout_item.time == s.workout_time


# ── Workout respects preferred time ──────────────────────────────

def test_workout_prefers_evening():
    s = schedule(preferred_workout_time="evening")
    workout_min = _to_min(s.workout_time)
    assert 17 * 60 <= workout_min <= 21 * 60


def test_workout_prefers_morning():
    s = schedule(preferred_workout_time="morning")
    workout_min = _to_min(s.workout_time)
    assert 6 * 60 <= workout_min <= 11 * 60


def test_workout_prefers_afternoon():
    s = schedule(preferred_workout_time="afternoon")
    workout_min = _to_min(s.workout_time)
    assert 12 * 60 + 30 <= workout_min <= 16 * 60


def test_workout_anytime_tries_evening_first():
    """With no events, anytime preference should land in the evening window."""
    s = schedule(preferred_workout_time="anytime")
    workout_min = _to_min(s.workout_time)
    assert 17 * 60 <= workout_min <= 21 * 60


# ── Dinner scheduled after workout ───────────────────────────────

def test_dinner_delivery_after_workout_start():
    s = schedule(preferred_workout_time="evening", workout_duration_minutes=60)
    dinner_min  = _to_min(s.dinner_delivery_time)
    workout_min = _to_min(s.workout_time)
    assert dinner_min > workout_min


def test_dinner_prefers_slot_after_workout_plus_buffer():
    """With a 60-min evening workout at 17:30, dinner should be around 19:30 (17:30+60+60)."""
    s = schedule(preferred_workout_time="evening", workout_duration_minutes=60)
    dinner_eating_min = _to_min(s.dinner_delivery_time) + 20
    # workout ends ~18:30, after_workout = 19:30 → dinner eating at 19:30
    assert dinner_eating_min >= 19 * 60


# ── Warnings when no suitable workout slot exists ─────────────────

def test_warning_when_no_workout_slot():
    """Fully blocked day should trigger a workout warning and use fallback time."""
    events = [event("Full day", "05:00", "23:00")]
    s = schedule(calendar_events=events, workout_duration_minutes=60)
    assert any("Trainingsslot" in w or "Training" in w for w in s.warnings)
    assert s.workout_time == "17:30"


def test_no_warning_when_slot_found():
    s = schedule(workout_duration_minutes=45)
    workout_warnings = [w for w in s.warnings if "Training" in w]
    assert len(workout_warnings) == 0


# ── Recovery day labels workout as Regeneration ───────────────────

def test_recovery_day_labels_workout_regeneration():
    s = build_daily_schedule(day_type="recovery", workout_duration_minutes=30)
    workout_item = next(i for i in s.items if i.type == "workout")
    assert workout_item.title == "Regeneration"


def test_normal_day_labels_workout_training():
    s = build_daily_schedule(day_type="normal", workout_duration_minutes=45)
    workout_item = next(i for i in s.items if i.type == "workout")
    assert workout_item.title == "Training"


# ── Wake time and sleep target are respected ─────────────────────

def test_wake_time_shifts_breakfast():
    s_early = build_daily_schedule(day_type="normal", workout_duration_minutes=45, wake_time="06:00")
    s_late  = build_daily_schedule(day_type="normal", workout_duration_minutes=45, wake_time="09:00")
    breakfast_early = next(i for i in s_early.items if i.type == "meal")
    breakfast_late  = next(i for i in s_late.items  if i.type == "meal")
    assert _to_min(breakfast_early.time) < _to_min(breakfast_late.time)


def test_sleep_target_appears_in_schedule():
    s = build_daily_schedule(day_type="normal", workout_duration_minutes=45, sleep_target_time="23:00")
    sleep_item = next(i for i in s.items if i.type == "recovery")
    assert sleep_item.time == "23:00"
