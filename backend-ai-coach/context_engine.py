"""
Health Context Engine.

Single point of truth for calculating a user's daily health state.
All downstream services (workout selection, meal selection, schedule building,
coaching) consume a HealthContext rather than raw input variables.

Architecture:
    DailyDecisionRequest
         ↓
    calculate_health_context(ContextInput)
         ↓
    HealthContext  ──→  DailyDecisionEngine  ──→  DailyDecisionResponse
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


# ── Context Flags ─────────────────────────────────────────────────

class ContextFlag(str, Enum):
    LOW_SLEEP                = "LOW_SLEEP"                # sleep < 6 h
    HIGH_STRESS              = "HIGH_STRESS"              # stress_level >= 8
    TRAVEL_DAY               = "TRAVEL_DAY"               # travel_today = True
    MENSTRUATION             = "MENSTRUATION"             # cycle_phase == "menstruation"
    FOLLICULAR_PHASE         = "FOLLICULAR_PHASE"         # cycle_phase == "follicular"
    OVULATION                = "OVULATION"                # cycle_phase == "ovulation"
    LUTEAL_PHASE             = "LUTEAL_PHASE"             # cycle_phase == "luteal"
    HEAVY_TRAINING_YESTERDAY = "HEAVY_TRAINING_YESTERDAY" # prev workout intensity >= 8
    HIGH_MEETING_LOAD        = "HIGH_MEETING_LOAD"        # meetings_count >= 7
    LOW_MOOD                 = "LOW_MOOD"                 # mood_level <= 3
    PERFORMANCE_READY        = "PERFORMANCE_READY"        # sleep>=7, stress<=5, meetings<=4, no blockers


# ── Input / Output Models ─────────────────────────────────────────

class ContextInput(BaseModel):
    sleep_hours: float = Field(..., ge=0, le=24)
    stress_level: int = Field(..., ge=1, le=10)
    meetings_count: int = Field(..., ge=0)
    mood_level: int = Field(5, ge=1, le=10)
    cycle_phase: Optional[str] = None    # menstruation|follicular|ovulation|luteal|unknown
    travel_today: bool = False
    previous_day_workout_intensity: Optional[int] = Field(None, ge=0, le=10)
    user_goal: Optional[str] = None      # Muskelaufbau | Fettabbau | Gesund bleiben


class HealthContext(BaseModel):
    # ── Scores (0-100, higher = better) ──
    health_score: int
    recovery_score: int
    energy_score: int
    stress_score: int           # 100 = no stress, 0 = maximum stress

    # ── Day classification ─────────────
    day_type: str               # "recovery" | "normal" | "performance"

    # ── Flags ─────────────────────────
    context_flags: List[str]

    # ── Explanations ───────────────────
    explanation: str
    positive_factors: List[str]
    negative_factors: List[str]


# ── Score Calculations ────────────────────────────────────────────

def _compute_recovery_score(inp: ContextInput) -> int:
    """
    How well the body has recovered from yesterday.
    Components: sleep (40), stress inverse (30), meetings inverse (15),
                previous workout inverse (15).
    """
    sleep_pts    = min(inp.sleep_hours / 8.0, 1.0) * 40
    stress_pts   = ((10 - inp.stress_level) / 9) * 30
    meetings_pts = max(0.0, (10 - inp.meetings_count) / 10) * 15

    prev = inp.previous_day_workout_intensity
    workout_pts = 15.0 if (prev is None or prev == 0) else max(0.0, (10 - prev) / 10) * 15

    return min(round(sleep_pts + stress_pts + meetings_pts + workout_pts), 100)


def _compute_energy_score(inp: ContextInput) -> int:
    """
    Available energy for training and focus today.
    Components: sleep (35), mood (25), stress inverse (20),
                cycle bonus (10), travel penalty (10).
    """
    sleep_pts  = min(inp.sleep_hours / 8.0, 1.0) * 35
    mood_pts   = ((inp.mood_level - 1) / 9) * 25
    stress_pts = ((10 - inp.stress_level) / 9) * 20

    cycle_bonus = {
        "ovulation":    10,
        "follicular":    7,
        "luteal":        3,
        "menstruation":  0,
    }.get(inp.cycle_phase or "", 5)

    travel_pts = 0.0 if inp.travel_today else 10.0

    return min(round(sleep_pts + mood_pts + stress_pts + cycle_bonus + travel_pts), 100)


def _compute_stress_score(inp: ContextInput) -> int:
    """
    Absence of stress signals. Higher = less stressed = better.
    Components: stress level inverse (50), meetings inverse (30),
                sleep adequacy (10), travel (10).
    """
    stress_pts   = ((10 - inp.stress_level) / 9) * 50
    meetings_pts = max(0.0, (10 - inp.meetings_count) / 10) * 30
    sleep_pts    = 10.0 if inp.sleep_hours >= 7 else (inp.sleep_hours / 7) * 10
    travel_pts   = 0.0 if inp.travel_today else 10.0

    return min(round(stress_pts + meetings_pts + sleep_pts + travel_pts), 100)


# ── Flag Detection ────────────────────────────────────────────────

def _detect_flags(inp: ContextInput) -> List[str]:
    flags: List[ContextFlag] = []

    if inp.sleep_hours < 6:
        flags.append(ContextFlag.LOW_SLEEP)

    if inp.stress_level >= 8:
        flags.append(ContextFlag.HIGH_STRESS)

    if inp.travel_today:
        flags.append(ContextFlag.TRAVEL_DAY)

    phase = (inp.cycle_phase or "").lower()
    if phase == "menstruation":
        flags.append(ContextFlag.MENSTRUATION)
    elif phase == "follicular":
        flags.append(ContextFlag.FOLLICULAR_PHASE)
    elif phase == "ovulation":
        flags.append(ContextFlag.OVULATION)
    elif phase == "luteal":
        flags.append(ContextFlag.LUTEAL_PHASE)

    if inp.previous_day_workout_intensity is not None and inp.previous_day_workout_intensity >= 8:
        flags.append(ContextFlag.HEAVY_TRAINING_YESTERDAY)

    if inp.meetings_count >= 7:
        flags.append(ContextFlag.HIGH_MEETING_LOAD)

    if inp.mood_level <= 3:
        flags.append(ContextFlag.LOW_MOOD)

    # Performance ready: all positive conditions, no blockers
    blocking = {ContextFlag.LOW_SLEEP, ContextFlag.HIGH_STRESS, ContextFlag.HIGH_MEETING_LOAD}
    if not any(f in flags for f in blocking):
        if inp.sleep_hours >= 7 and inp.stress_level <= 5 and inp.meetings_count <= 4:
            flags.append(ContextFlag.PERFORMANCE_READY)

    return [f.value for f in flags]


# ── Day Classification ────────────────────────────────────────────

_ORDER = ["recovery", "normal", "performance"]

def _classify_day(flags: List[str]) -> str:
    """
    Classify the day type from flags, including cycle-phase intensity caps.

    Blocking flags → recovery:  LOW_SLEEP | HIGH_STRESS | HIGH_MEETING_LOAD
    Performance flag:           PERFORMANCE_READY
    Cycle caps:                 MENSTRUATION caps to recovery, LUTEAL caps to normal
    """
    # Base classification
    blocking = {ContextFlag.LOW_SLEEP.value, ContextFlag.HIGH_STRESS.value, ContextFlag.HIGH_MEETING_LOAD.value}
    if any(f in flags for f in blocking):
        base = "recovery"
    elif ContextFlag.PERFORMANCE_READY.value in flags:
        base = "performance"
    else:
        base = "normal"

    # Cycle-phase intensity cap (replaces CYCLE_INTENSITY_CAP dict in decision engine)
    cap: Optional[str] = None
    if ContextFlag.MENSTRUATION.value in flags:
        cap = "recovery"
    elif ContextFlag.LUTEAL_PHASE.value in flags:
        cap = "normal"

    if cap is not None:
        return _ORDER[min(_ORDER.index(base), _ORDER.index(cap))]
    return base


# ── Explanation ───────────────────────────────────────────────────

def _generate_explanation(day_type: str, inp: ContextInput, flags: List[str]) -> str:
    if day_type == "recovery":
        if ContextFlag.LOW_SLEEP.value in flags:
            return (
                f"Sleep was only {inp.sleep_hours}h — below the 6h recovery threshold. "
                "Low-intensity protocol activated to protect your central nervous system."
            )
        if ContextFlag.HIGH_STRESS.value in flags:
            return (
                f"Stress level at {inp.stress_level}/10 — high cortisol signals recovery day. "
                "Intense training would compound physiological stress rather than build fitness."
            )
        if ContextFlag.HIGH_MEETING_LOAD.value in flags:
            return (
                f"{inp.meetings_count} meetings scheduled — cognitive load is too high for performance training. "
                "Recovery protocol keeps your body ready without adding mental fatigue."
            )
        if ContextFlag.MENSTRUATION.value in flags:
            return (
                "Menstruation phase detected — intensity capped to recovery to support "
                "your body's natural healing process."
            )
        return (
            f"Recovery conditions: {inp.sleep_hours}h sleep, stress {inp.stress_level}/10, "
            f"{inp.meetings_count} meetings."
        )
    if day_type == "performance":
        return (
            f"Optimal conditions detected: {inp.sleep_hours}h sleep, stress {inp.stress_level}/10, "
            f"{inp.meetings_count} meetings. Full performance protocol activated."
        )
    return (
        f"Moderate conditions: {inp.sleep_hours}h sleep, stress {inp.stress_level}/10, "
        f"{inp.meetings_count} meetings. Standard training and nutrition protocol."
    )


# ── Factor Generation ─────────────────────────────────────────────

def _generate_factors(inp: ContextInput, flags: List[str]) -> tuple[List[str], List[str]]:
    positive: List[str] = []
    negative: List[str] = []

    # Sleep
    if inp.sleep_hours >= 8:
        positive.append(f"Exzellenter Schlaf: {inp.sleep_hours}h – ideale Erholung")
    elif inp.sleep_hours >= 7:
        positive.append(f"Guter Schlaf: {inp.sleep_hours}h")
    elif inp.sleep_hours < 6:
        negative.append(f"Schlaf nur {inp.sleep_hours}h – unter dem Minimum von 6h")
    else:
        negative.append(f"Schlaf unter Optimal: {inp.sleep_hours}h (Ziel: 7–8h)")

    # Stress
    if inp.stress_level <= 3:
        positive.append("Niedriger Stress – ideale Erholungsbedingungen")
    elif inp.stress_level <= 5:
        positive.append(f"Moderater Stress: {inp.stress_level}/10")
    elif inp.stress_level >= 8:
        negative.append(f"Hoher Stress: {inp.stress_level}/10 – Cortisol erhöht")
    else:
        negative.append(f"Erhöhter Stress: {inp.stress_level}/10")

    # Meetings
    if inp.meetings_count == 0:
        positive.append("Kein Meeting heute – minimale kognitive Belastung")
    elif inp.meetings_count <= 2:
        positive.append(f"Leichter Terminplan: {inp.meetings_count} Meeting(s)")
    elif inp.meetings_count <= 4:
        positive.append(f"Überschaubarer Terminplan: {inp.meetings_count} Meetings")
    elif inp.meetings_count >= 7:
        negative.append(f"{inp.meetings_count} Meetings – hohe kognitive Belastung")
    else:
        negative.append(f"Voller Terminplan: {inp.meetings_count} Meetings")

    # Mood
    if inp.mood_level >= 8:
        positive.append(f"Hohe Stimmung: {inp.mood_level}/10")
    elif inp.mood_level <= 3:
        negative.append(f"Niedrige Stimmung: {inp.mood_level}/10")

    # Travel
    if inp.travel_today:
        negative.append("Reisetag – erhöhter physischer und mentaler Stressfaktor")

    # Previous workout
    prev = inp.previous_day_workout_intensity
    if prev is not None and prev >= 8:
        negative.append(f"Intensives Training gestern ({prev}/10) – Erholung priorisieren")
    elif prev is not None and prev <= 3 and prev > 0:
        positive.append("Leichtes oder regeneratives Training gestern – Körper gut erholt")

    # Cycle phase
    phase = (inp.cycle_phase or "").lower()
    if phase == "ovulation":
        positive.append("Eisprungphase – mögliches Performance-Hoch")
    elif phase == "follicular":
        positive.append("Follikelphase – Energie und Kraft steigen")
    elif phase == "menstruation":
        negative.append("Menstruationsphase – sanftere Belastung empfohlen")
    elif phase == "luteal":
        negative.append("Lutealphase – Erholungsunterstützung wichtig")

    return positive, negative


# ── Public API ────────────────────────────────────────────────────

def calculate_health_context(inp: ContextInput) -> HealthContext:
    """
    Main entry point. Given raw daily inputs, returns a fully computed
    HealthContext that all downstream decision-making services consume.
    """
    recovery_score = _compute_recovery_score(inp)
    energy_score   = _compute_energy_score(inp)
    stress_score   = _compute_stress_score(inp)
    health_score   = min(round(0.4 * recovery_score + 0.35 * energy_score + 0.25 * stress_score), 100)

    flags          = _detect_flags(inp)
    day_type       = _classify_day(flags)
    explanation    = _generate_explanation(day_type, inp, flags)
    positive, negative = _generate_factors(inp, flags)

    return HealthContext(
        health_score=health_score,
        recovery_score=recovery_score,
        energy_score=energy_score,
        stress_score=stress_score,
        day_type=day_type,
        context_flags=flags,
        explanation=explanation,
        positive_factors=positive,
        negative_factors=negative,
    )
