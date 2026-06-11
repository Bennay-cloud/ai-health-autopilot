import json
import os
from datetime import datetime, timezone
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional

from cycle_phase_service import CycleProfile, CyclePhaseResult, detect_cycle_phase
from meal_catalog_service import MealItem, select_daily_meals
from context_engine import ContextInput, HealthContext, ContextFlag, calculate_health_context
from schedule_service import (
    CalendarEvent, ScheduleItem, DailySchedule, build_daily_schedule,
)
from occupation_engine import OccupationProfile, get_occupation_profile
from pain_engine import PainInput, get_pain_profile
from health_priority_engine import HumanCentricPriority, generate_health_priorities
from training_knowledge import TrainingTypeProfile, get_training_profile
from explanation_engine import (
    WhyThisMatters, HealthAdvisorMessage,
    build_why_this_matters, generate_health_advisor_message,
)

WORKOUTS_PATH = os.path.join(os.path.dirname(__file__), "rag", "mock_workouts.json")


def _load_workouts() -> list:
    with open(WORKOUTS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ── Pydantic Models ──────────────────────────────────────────────

class DailyContext(BaseModel):
    sleep_hours: float = Field(..., ge=0, le=24, description="Hours of sleep last night")
    stress_level: int = Field(..., ge=1, le=10, description="Subjective stress level (1=none, 10=extreme)")
    meetings_count: int = Field(..., ge=0, description="Number of meetings scheduled today")
    mood_level: int = Field(5, ge=1, le=10, description="Subjective mood (1=very low, 10=excellent)")
    travel_today: bool = Field(False, description="Whether the user is traveling today")
    previous_day_workout_intensity: Optional[int] = Field(
        None, ge=0, le=10, description="Yesterday's workout intensity (0=none, 10=maximum)"
    )
    available_training_window_minutes: Optional[int] = Field(
        None, ge=5, le=240, description="Available time window for training in minutes"
    )
    # ── Schedule context (all optional, sensible defaults) ─────
    date: Optional[str] = Field(None, description="Date in YYYY-MM-DD format")
    wake_time: str = Field("07:00", description="Wake-up time HH:MM")
    sleep_target_time: str = Field("22:30", description="Target sleep time HH:MM")
    calendar_events: List[CalendarEvent] = Field(default_factory=list)
    preferred_workout_time: str = Field(
        "anytime", description="morning | afternoon | evening | anytime"
    )
    location_today: str = Field("home", description="home | office | travel")


class OccupationalHealthRiskScore(BaseModel):
    """
    Structured data stored per decision for future Occupational Health Risk Score feature.
    No UI rendering yet — enables future analytics, risk tracking, and personalisation.
    """
    posture_risk: int               # 1-10 (profession baseline + pain severity contribution)
    movement_risk: int              # 1-10 (profession baseline)
    recovery_risk: int              # 1-10 (inverse of recovery_score)
    occupational_strain: int        # 1-10 (compound: profession + pain severity + stress)
    risk_factors_detected: int      # count of active occupation risk factors
    high_severity_pain_count: int   # count of pain areas with severity >= 7
    computed_at: str                # ISO 8601 timestamp


class UserProfileInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    ziel: str = Field(..., description="Muskelaufbau | Fettabbau | Gesund bleiben")
    ernaehrung: str = Field(..., description="Mischkost | Vegan | Vegetarisch | Halal")
    level: str = Field(..., description="Einsteiger | Fortgeschrittene | Advanced")
    cycle_profile: Optional[CycleProfile] = None
    # ── Occupational Health fields ─────────────────────────────────────────
    profession: Optional[str] = Field(None, description="Profession ID from /api/health/occupations")
    pain_areas: Optional[List[PainInput]] = Field(default_factory=list, description="Active pain areas with severity")


class DailyDecisionRequest(BaseModel):
    user_profile: UserProfileInput
    daily_context: DailyContext
    user_id: Optional[str] = None


class ExerciseDetail(BaseModel):
    model_config = ConfigDict(extra="ignore")

    exercise_name: str
    sets: int
    reps_or_duration: str
    video_url: str
    instructions: str
    common_mistakes: str


class WorkoutDurationBreakdown(BaseModel):
    total_minutes: int
    warmup_minutes: int
    main_training_minutes: int
    cooldown_minutes: int


class WorkoutPlan(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    day_type: str
    level: str
    duration_min: int
    intensity: str
    workout_type: str = "strength"
    intensity_level: int = 3
    total_duration_minutes: Optional[int] = None
    warmup_minutes: Optional[int] = None
    main_training_minutes: Optional[int] = None
    cooldown_minutes: Optional[int] = None
    exercises: List[ExerciseDetail]
    description: str


class ScoreDrivers(BaseModel):
    positive: List[str]
    negative: List[str]


class DailyDecisionResponse(BaseModel):
    # ── Core decision ──────────────────
    day_type: str
    explanation: str
    # ── Scores ─────────────────────────
    recovery_score: int
    energy_score: int
    stress_score: int
    # ── Context ────────────────────────
    context_flags: List[str]
    cycle_phase: CyclePhaseResult
    # ── Selections ─────────────────────
    selected_workout: WorkoutPlan
    workout_duration_breakdown: WorkoutDurationBreakdown
    coaching_message: str
    selected_lunch: MealItem
    selected_dinner: MealItem
    delivery_recommendation: str
    # ── Explanations ───────────────────
    score_drivers: ScoreDrivers
    schedule: List[ScheduleItem]
    # ── Dynamic schedule ───────────────
    lunch_delivery_time: str
    dinner_delivery_time: str
    workout_time: str
    schedule_warnings: List[str]
    # ── Occupational Health Advisor ────
    occupation_profile: Optional[dict] = None
    health_priorities: List[dict] = []
    why_this_matters: Optional[dict] = None
    health_advisor_message: Optional[str] = None
    occupational_health_risk_score: Optional[dict] = None
    # ── Personal Learning ──────────────
    personalization_note: Optional[str] = None
    # ── Preference Engine ──────────────
    preference_note: Optional[str] = None


# ── Cycle Phase Workout Preferences ──────────────────────────────
# Maps cycle phase → preferred workout types (priority order).
# Intensity caps are no longer here — they live in context_engine._classify_day().

CYCLE_WORKOUT_TYPE_MAP = {
    "menstruation": ["yoga", "walking", "mobility"],
    "follicular":   ["light_strength", "strength", "circuit"],
    "ovulation":    ["circuit", "plyometric", "strength"],
    "luteal":       ["light_strength", "mobility", "yoga"],
    "unknown":      [],
}


def get_cycle_workout_preferences(
    cycle_result: CyclePhaseResult,
) -> tuple[list[str], str]:
    """
    Returns (preferred_workout_types, cycle_note).
    Intensity capping is handled by the HealthContextEngine; this only
    returns type preferences and a human-readable phase note.
    """
    preferred_types = CYCLE_WORKOUT_TYPE_MAP.get(cycle_result.phase, [])
    phase_notes = {
        "menstruation": "Menstruation phase — gentle movement prioritised.",
        "follicular":   "Follicular phase — energy rising, strength work recommended.",
        "ovulation":    "Ovulation phase — peak performance window.",
        "luteal":       "Luteal phase — moderate load, avoid over-training.",
    }
    cycle_note = phase_notes.get(cycle_result.phase, "")
    return preferred_types, cycle_note


# ── Coaching Messages ─────────────────────────────────────────────

COACHING_MESSAGES = {
    ("recovery", "menstruation"): (
        "Your body is doing important work right now. Gentle movement + rest is the most powerful thing you can do today. "
        "Honour the phase — tomorrow's strength is built in today's recovery."
    ),
    ("recovery", "luteal"): (
        "Pre-menstrual and under-recovered — a powerful combination to protect. "
        "Light movement will ease tension without depleting your reserves."
    ),
    ("recovery", "unknown"): (
        "Recovery day activated. Let your nervous system reset — "
        "today's gentle protocol is an investment in tomorrow's performance."
    ),
    ("performance", "follicular"): (
        "Hormones and recovery are aligned — this is your peak window. "
        "Push hard, lift heavy, and trust your body today."
    ),
    ("performance", "ovulation"): (
        "Ovulation phase meets peak conditions: maximum strength and coordination available. "
        "Make the most of this high-energy window."
    ),
    ("performance", "unknown"): (
        "All green: sleep, stress, and schedule are aligned. "
        "Today is a performance day — commit fully to your training."
    ),
    ("normal", "luteal"): (
        "Luteal phase can bring fatigue and mood shifts — listen to your body. "
        "Moderate training keeps momentum without pushing too hard."
    ),
    ("normal", "follicular"): (
        "Energy is building as you move into your follicular phase. "
        "Consistent moderate training today sets the stage for peak performance ahead."
    ),
    ("normal", "unknown"): (
        "Solid day ahead — your nutrition and training are calibrated to your current conditions. "
        "Stay consistent and trust the process."
    ),
}

DEFAULT_COACHING = {
    "recovery":    "Rest is productive. Today's protocol protects your long-term progress.",
    "performance": "Conditions are optimal — give everything you have today.",
    "normal":      "Stay consistent. Every standard day compounds into extraordinary results.",
}


def generate_coaching_message(day_type: str, cycle_phase: str) -> str:
    key = (day_type, cycle_phase)
    if key in COACHING_MESSAGES:
        return COACHING_MESSAGES[key]
    return DEFAULT_COACHING.get(day_type, "Keep going — every day counts.")


# ── Workout Selection ─────────────────────────────────────────────

def select_workout(
    effective_day_type: str,
    level: str,
    preferred_types: list[str],
    available_minutes: Optional[int],
    disliked_types: Optional[list[str]] = None,
) -> dict:
    workouts = _load_workouts()

    candidates = [w for w in workouts if w["day_type"] == effective_day_type]

    if available_minutes is not None:
        time_filtered = [w for w in candidates if w.get("total_duration_minutes", w["duration_min"]) <= available_minutes]
        if time_filtered:
            candidates = time_filtered
        else:
            any_in_window = [w for w in workouts if w.get("total_duration_minutes", w["duration_min"]) <= available_minutes]
            if any_in_window:
                candidates = any_in_window

    if not candidates:
        candidates = workouts

    # Filter out disliked types — only when non-disliked alternatives exist
    if disliked_types:
        non_disliked = [w for w in candidates if w.get("workout_type") not in disliked_types]
        if non_disliked:
            candidates = non_disliked
        # else: all candidates are disliked — fall through to standard selection (safety > preference)

    for wtype in preferred_types:
        for w in candidates:
            if w.get("workout_type") == wtype and w.get("level") == level:
                return w

    for wtype in preferred_types:
        for w in candidates:
            if w.get("workout_type") == wtype:
                return w

    for w in candidates:
        if w.get("level") == level:
            return w

    return candidates[0]


# ── Delivery Recommendation ───────────────────────────────────────

DELIVERY_MESSAGES = {
    "recovery": (
        "Meals pre-ordered for home delivery — lunch at 12:00, dinner at 18:30. "
        "No prep effort required so you can rest and recharge."
    ),
    "performance": (
        "High-protein lunch scheduled for office delivery at 13:00. "
        "Performance dinner auto-ordered for 19:00 to maximize post-workout recovery."
    ),
    "normal": (
        "Standard delivery scheduled: lunch at 12:30, dinner at 18:45. "
        "Meals matched to your goal and dietary preferences."
    ),
}



# ── Main Service Function ─────────────────────────────────────────

def generate_daily_decision(
    request: DailyDecisionRequest,
    user_preferred_workout_types: Optional[List[str]] = None,
    user_disliked_workout_types: Optional[List[str]] = None,
) -> DailyDecisionResponse:
    # 1. Detect cycle phase (needed to feed into context engine)
    cycle_profile = request.user_profile.cycle_profile or CycleProfile()
    from datetime import date as _date
    today_override = (
        _date.fromisoformat(request.daily_context.date)
        if request.daily_context.date
        else None
    )
    cycle_result = detect_cycle_phase(cycle_profile, today=today_override)

    # 2. Build context input — single authoritative representation of today's state
    context_input = ContextInput(
        sleep_hours=request.daily_context.sleep_hours,
        stress_level=request.daily_context.stress_level,
        meetings_count=request.daily_context.meetings_count,
        mood_level=request.daily_context.mood_level,
        cycle_phase=cycle_result.phase,
        travel_today=request.daily_context.travel_today,
        previous_day_workout_intensity=request.daily_context.previous_day_workout_intensity,
        user_goal=request.user_profile.ziel,
    )

    # 3. Calculate health context — day_type, scores, flags, factors
    health_context = calculate_health_context(context_input)

    effective_day_type = health_context.day_type
    explanation        = health_context.explanation

    # 4. Workout type preferences + phase note (cap already applied in context engine)
    preferred_types, cycle_note = get_cycle_workout_preferences(cycle_result)
    if cycle_note:
        explanation = f"{explanation} {cycle_note}"

    # 5. Coaching message
    coaching_message = generate_coaching_message(effective_day_type, cycle_result.phase)

    # 6. Workout selection — merge cycle preferences with user preference boosts
    # Preference-preferred types are prepended so they are tried first,
    # but cycle-phase types still participate in the fallback chain.
    # Safety constraint: day_type (recovery/normal/performance) is NEVER overridden.
    merged_preferred = list(user_preferred_workout_types or []) + [
        t for t in preferred_types if t not in (user_preferred_workout_types or [])
    ]
    workout_data = select_workout(
        effective_day_type,
        request.user_profile.level,
        merged_preferred,
        request.daily_context.available_training_window_minutes,
        disliked_types=user_disliked_workout_types,
    )

    # 7. Meal selection (via shared catalog service)
    lunch, dinner = select_daily_meals(
        request.user_profile.ernaehrung,
        request.user_profile.ziel,
        effective_day_type,
    )

    # 8. Duration breakdown
    duration_breakdown = WorkoutDurationBreakdown(
        total_minutes=workout_data.get("total_duration_minutes", workout_data["duration_min"]),
        warmup_minutes=workout_data.get("warmup_minutes", 5),
        main_training_minutes=workout_data.get("main_training_minutes", workout_data["duration_min"] - 10),
        cooldown_minutes=workout_data.get("cooldown_minutes", 5),
    )

    # 9. Score drivers come directly from the health context
    score_drivers = ScoreDrivers(
        positive=health_context.positive_factors,
        negative=health_context.negative_factors,
    )

    daily_schedule = build_daily_schedule(
        day_type=effective_day_type,
        workout_duration_minutes=workout_data.get("total_duration_minutes", workout_data["duration_min"]),
        wake_time=request.daily_context.wake_time,
        sleep_target_time=request.daily_context.sleep_target_time,
        calendar_events=request.daily_context.calendar_events,
        preferred_workout_time=request.daily_context.preferred_workout_time,
        location_today=request.daily_context.location_today,
    )

    # ── 10. Occupational Health Advisor pipeline ──────────────────────────────
    occ_profile_out: Optional[dict] = None
    health_priorities_out: List[dict] = []
    why_this_matters_out: Optional[dict] = None
    advisor_message_out: Optional[str] = None
    risk_score_out: Optional[dict] = None

    profession = request.user_profile.profession
    pain_inputs = request.user_profile.pain_areas or []

    if profession:
        occ_profile = get_occupation_profile(profession)
        if occ_profile:
            occ_profile_out = {
                "profession": occ_profile.profession,
                "profession_display": occ_profile.profession_display,
                "work_demands": occ_profile.work_demands,
                "health_risks": occ_profile.health_risks,
                "common_pain_patterns": occ_profile.common_pain_patterns,
                "work_performance_benefits": occ_profile.work_performance_benefits,
            }

            # Generate human-centric priorities (severity-weighted)
            priorities = generate_health_priorities(
                occupation_profile=occ_profile,
                pain_inputs=pain_inputs,
                goal=request.user_profile.ziel,
                stress_level=request.daily_context.stress_level,
                recovery_score=health_context.recovery_score,
            )
            health_priorities_out = [p.model_dump() for p in priorities]

            # Get training knowledge profile for explanation
            training_type = workout_data.get("workout_type", "strength")
            training_profile = get_training_profile(training_type)

            # Build WhyThisMatters (deterministic, no LLM)
            why = build_why_this_matters(
                occupation_profile=occ_profile,
                pain_inputs=pain_inputs,
                priorities=priorities,
                training_profile=training_profile,
            )
            why_this_matters_out = why.model_dump()

            # Generate advisor message (LLM — graceful fallback on failure)
            try:
                advisor_msg = generate_health_advisor_message(
                    occupation_profile=occ_profile,
                    pain_inputs=pain_inputs,
                    priorities=priorities,
                    training_profile=training_profile,
                    goal=request.user_profile.ziel,
                    day_type=effective_day_type,
                    stress_level=request.daily_context.stress_level,
                    recovery_score=health_context.recovery_score,
                )
                advisor_message_out = advisor_msg.message
            except Exception as e:
                print(f"[daily_decision] Advisor message failed (non-critical): {e}")

            # Compute Occupational Health Risk Score (stored for future analytics, no UI)
            try:
                avg_pain = (
                    sum(p.severity for p in pain_inputs) / len(pain_inputs)
                    if pain_inputs else 0.0
                )
                posture_risk = min(10, round(occ_profile.posture_risk_baseline + avg_pain * 0.2))
                occ_strain = min(10, round(
                    occ_profile.occupational_strain_baseline
                    + avg_pain * 0.3
                    + (1 if request.daily_context.stress_level >= 7 else 0)
                ))
                recovery_risk = min(10, max(1, round(10 - health_context.recovery_score / 10)))
                risk_score_out = OccupationalHealthRiskScore(
                    posture_risk=posture_risk,
                    movement_risk=occ_profile.movement_risk_baseline,
                    recovery_risk=recovery_risk,
                    occupational_strain=occ_strain,
                    risk_factors_detected=len(occ_profile.health_risks),
                    high_severity_pain_count=sum(1 for p in pain_inputs if p.severity >= 7),
                    computed_at=datetime.now(timezone.utc).isoformat(),
                ).model_dump()
            except Exception as e:
                print(f"[daily_decision] Risk score computation failed (non-critical): {e}")

    return DailyDecisionResponse(
        day_type=effective_day_type,
        explanation=explanation,
        recovery_score=health_context.recovery_score,
        energy_score=health_context.energy_score,
        stress_score=health_context.stress_score,
        context_flags=health_context.context_flags,
        cycle_phase=cycle_result,
        selected_workout=WorkoutPlan(**workout_data),
        workout_duration_breakdown=duration_breakdown,
        coaching_message=coaching_message,
        selected_lunch=lunch,
        selected_dinner=dinner,
        delivery_recommendation=DELIVERY_MESSAGES[effective_day_type],
        score_drivers=score_drivers,
        schedule=daily_schedule.items,
        lunch_delivery_time=daily_schedule.lunch_delivery_time,
        dinner_delivery_time=daily_schedule.dinner_delivery_time,
        workout_time=daily_schedule.workout_time,
        schedule_warnings=daily_schedule.warnings,
        occupation_profile=occ_profile_out,
        health_priorities=health_priorities_out,
        why_this_matters=why_this_matters_out,
        health_advisor_message=advisor_message_out,
        occupational_health_risk_score=risk_score_out,
        personalization_note=None,  # populated by main.py after learning profile lookup
        preference_note=None,       # populated by main.py after preference profile lookup
    )
