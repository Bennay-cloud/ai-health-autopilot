"""
Dynamic Schedule Engine.

Builds a personalised daily timeline from health context, selected workout,
calendar events, and user preferences.  All downstream services consume the
returned DailySchedule instead of hardcoded time strings.
"""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel


# ── Models ────────────────────────────────────────────────────────

class CalendarEvent(BaseModel):
    title: str
    start_time: str   # "HH:MM"
    end_time: str     # "HH:MM"


class ScheduleItem(BaseModel):
    time: str
    title: str
    type: str             # "meal" | "delivery" | "workout" | "recovery"
    duration_minutes: int = 0
    reason: str = ""


class DailySchedule(BaseModel):
    items: List[ScheduleItem]
    lunch_delivery_time: str
    dinner_delivery_time: str
    workout_time: str
    warnings: List[str]


# ── Time Helpers ──────────────────────────────────────────────────

def _to_min(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def _to_str(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _is_blocked(start: int, duration: int, events: List[CalendarEvent]) -> bool:
    """Return True if [start, start+duration) overlaps any calendar event."""
    end = start + duration
    for e in events:
        es = _to_min(e.start_time)
        ee = _to_min(e.end_time)
        if start < ee and end > es:
            return True
    return False


def _find_free_slot(
    window_start: int,
    window_end: int,
    duration: int,
    events: List[CalendarEvent],
    preferred: Optional[int] = None,
    step: int = 15,
) -> Optional[int]:
    """
    Find the first available slot of `duration` minutes within
    [window_start, window_end].  Tries `preferred` first; falls back to
    scanning forward in `step`-minute increments.
    """
    if preferred is not None and window_start <= preferred <= window_end - duration:
        if not _is_blocked(preferred, duration, events):
            return preferred
    t = window_start
    while t + duration <= window_end:
        if not _is_blocked(t, duration, events):
            return t
        t += step
    return None


# ── Scheduling Constants ──────────────────────────────────────────

_WORKOUT_WINDOWS = {
    "morning":   (6 * 60,       11 * 60),
    "afternoon": (12 * 60 + 30, 16 * 60),
    "evening":   (17 * 60,      21 * 60),
    "anytime":   (6 * 60,       21 * 60),
}

_WORKOUT_PREFERRED_STARTS = {
    "morning":   7 * 60,
    "afternoon": 13 * 60,
    "evening":   17 * 60 + 30,
}

# Ordered windows tried when preferred == "anytime"
_ANYTIME_SEARCH_ORDER = [
    (17 * 60, 21 * 60, 17 * 60 + 30),   # evening first
    (6 * 60,  11 * 60, 7 * 60),          # then morning
    (12 * 60 + 30, 16 * 60, 13 * 60),   # then afternoon
]


# ── Main Builder ──────────────────────────────────────────────────

def build_daily_schedule(
    day_type: str,
    workout_duration_minutes: int,
    wake_time: str = "07:00",
    sleep_target_time: str = "22:30",
    calendar_events: Optional[List[CalendarEvent]] = None,
    preferred_workout_time: str = "anytime",
    location_today: str = "home",
) -> DailySchedule:
    events = calendar_events or []
    warnings: List[str] = []
    items: List[ScheduleItem] = []

    # ── 1. Breakfast: 30 min after wake ──────────────────────────
    breakfast_min = _to_min(wake_time) + 30
    items.append(ScheduleItem(
        time=_to_str(breakfast_min),
        title="Frühstück",
        type="meal",
        duration_minutes=20,
        reason=f"30 Minuten nach Aufwachen ({wake_time})",
    ))

    # ── 2. Lunch: prefer 12:30, avoid calendar events ────────────
    LUNCH_PREFERRED = 12 * 60 + 30
    LUNCH_WIN_START = 11 * 60 + 30
    LUNCH_WIN_END   = 14 * 60 + 30
    LUNCH_DURATION  = 30

    lunch_eating_min = _find_free_slot(
        LUNCH_WIN_START, LUNCH_WIN_END, LUNCH_DURATION,
        events, preferred=LUNCH_PREFERRED,
    )
    if lunch_eating_min is None:
        lunch_eating_min = LUNCH_PREFERRED
        warnings.append(
            "Kein freier Mittagsslot (11:30–14:30) gefunden – Standardzeit 12:30 gesetzt."
        )

    lunch_delivery_min = max(lunch_eating_min - 20, LUNCH_WIN_START - 30)
    items.append(ScheduleItem(
        time=_to_str(lunch_delivery_min),
        title="Mittagslieferung",
        type="delivery",
        duration_minutes=0,
        reason="Lieferung 20 Minuten vor dem Mittagessen",
    ))

    # ── 3. Workout: respect preferred_workout_time ───────────────
    workout_min: Optional[int] = None

    if preferred_workout_time == "anytime":
        for win_start, win_end, pref in _ANYTIME_SEARCH_ORDER:
            workout_min = _find_free_slot(
                win_start, win_end, workout_duration_minutes, events, preferred=pref
            )
            if workout_min is not None:
                break
    else:
        w_start, w_end = _WORKOUT_WINDOWS.get(preferred_workout_time, _WORKOUT_WINDOWS["anytime"])
        w_pref = _WORKOUT_PREFERRED_STARTS.get(preferred_workout_time)
        workout_min = _find_free_slot(w_start, w_end, workout_duration_minutes, events, preferred=w_pref)
        if workout_min is None:
            # Fallback: search the whole day
            workout_min = _find_free_slot(6 * 60, 21 * 60, workout_duration_minutes, events)

    if workout_min is None:
        workout_min = 17 * 60 + 30   # hard fallback: 17:30
        warnings.append(
            f"Kein freier Trainingsslot ({workout_duration_minutes} min) gefunden – "
            "Standardzeit 17:30 gesetzt."
        )

    workout_title = "Regeneration" if day_type in ("recovery", "deep_recovery") else "Training"
    items.append(ScheduleItem(
        time=_to_str(workout_min),
        title=workout_title,
        type="workout",
        duration_minutes=workout_duration_minutes,
        reason=f"Bevorzugte Zeit: {preferred_workout_time}",
    ))

    # ── 4. Dinner: prefer after workout + buffer ─────────────────
    DINNER_WIN_START = 18 * 60      # 18:00
    DINNER_WIN_END   = 21 * 60      # 21:00
    DINNER_DURATION  = 30

    workout_end      = workout_min + workout_duration_minutes
    after_workout    = workout_end + 60   # 60 min rest

    if DINNER_WIN_START <= after_workout <= DINNER_WIN_END - DINNER_DURATION:
        dinner_preferred = after_workout
    else:
        dinner_preferred = 18 * 60 + 30   # 18:30

    dinner_eating_min = _find_free_slot(
        DINNER_WIN_START, DINNER_WIN_END, DINNER_DURATION,
        events, preferred=dinner_preferred,
    )
    if dinner_eating_min is None:
        dinner_eating_min = 18 * 60 + 30
        warnings.append(
            "Kein freier Abendessensslot (18:00–21:00) gefunden – Standardzeit 18:30 gesetzt."
        )

    dinner_delivery_min = max(dinner_eating_min - 20, DINNER_WIN_START)
    items.append(ScheduleItem(
        time=_to_str(dinner_delivery_min),
        title="Abendlieferung",
        type="delivery",
        duration_minutes=0,
        reason="Lieferung 20 Minuten vor dem Abendessen",
    ))

    # ── 5. Sleep target ──────────────────────────────────────────
    items.append(ScheduleItem(
        time=sleep_target_time,
        title="Schlafziel",
        type="recovery",
        duration_minutes=0,
        reason="Tägliches Erholungsziel",
    ))

    # Sort chronologically
    items.sort(key=lambda x: _to_min(x.time))

    return DailySchedule(
        items=items,
        lunch_delivery_time=_to_str(lunch_delivery_min),
        dinner_delivery_time=_to_str(dinner_delivery_min),
        workout_time=_to_str(workout_min),
        warnings=warnings,
    )
