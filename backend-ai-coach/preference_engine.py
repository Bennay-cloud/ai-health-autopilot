"""
Preference Engine.

Learns what individual users actually enjoy and prefer, complementing
the Personal Learning Engine (which answers "what works physiologically").
This engine answers: "what does the user actually like?"

Three signal sources:
  1. Implicit signals  — workout completion rates, repeat selections
  2. Explicit feedback — thumbs up/down ratings with optional reason codes
  3. Location adherence — which delivery context produces best meal adherence

Preference score formula (per workout type):
  preference_score = completion_rate * 0.7 + explicit_factor * 0.3

  completion_rate  = avg(workout_completion_pct) / 100          (0–1)
  explicit_factor  = 0.5 + (net_score / total_feedback) * 0.5  (0–1)
                   → 0.5 when no feedback (neutral)
                   → 1.0 when all feedback is positive
                   → 0.0 when all feedback is negative

Classification thresholds:
  preferred : score >= 0.65
  neutral   : 0.35 < score < 0.65
  disliked  : score <= 0.35

Minimum 2 occurrences required before classifying a workout type.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from decision_record_service import DecisionRecord


# ── Constants ─────────────────────────────────────────────────────

PREFERRED_THRESHOLD = 0.65
DISLIKED_THRESHOLD  = 0.35
MIN_OCCURRENCES     = 2

COACHING_STYLES = ("motivational", "scientific", "direct", "supportive")

WORKOUT_REASONS = ("too_hard", "too_easy", "boring", "no_time", "enjoyed_it")
MEAL_REASONS    = ("tasty", "expensive", "wrong_cuisine", "too_much_food", "too_little_food")

LOW_THRESHOLD    = 7
MEDIUM_THRESHOLD = 30


# ── Feedback Models ───────────────────────────────────────────────

class WorkoutFeedback(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    workout_type: str
    score: int          # 1 = positive (👍), -1 = negative (👎)
    reason: Optional[str] = None   # one of WORKOUT_REASONS
    coaching_style: Optional[str] = None  # one of COACHING_STYLES (if applicable)
    date: str
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class MealFeedback(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    meal_id: str
    meal_name: Optional[str] = None
    provider: Optional[str] = None
    category: Optional[str] = None   # diet_tag or cuisine style
    score: int                         # 1 = positive, -1 = negative
    reason: Optional[str] = None       # one of MEAL_REASONS
    date: str
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ── Preference Profile Models ─────────────────────────────────────

class WorkoutTypePreference(BaseModel):
    workout_type: str
    preference_score: float    # 0.0–1.0
    completion_rate: float     # 0.0–1.0
    times_selected: int
    explicit_factor: float     # 0.0–1.0 (0.5 = neutral/no feedback)
    classification: str        # preferred | neutral | disliked


class UserPreferenceProfile(BaseModel):
    user_id: str
    confidence_level: str          # low | medium | high
    total_decisions_analyzed: int
    # Workout
    preferred_workout_types: List[str]
    disliked_workout_types: List[str]
    workout_type_scores: List[WorkoutTypePreference]
    # Timing & duration
    preferred_workout_time: Optional[str]     # morning | afternoon | evening
    preferred_duration_bucket: Optional[str]  # 0-15 min | 16-30 min | …
    # Meals
    preferred_delivery_location: Optional[str]  # home | office | travel
    preferred_meal_categories: List[str]
    preferred_providers: List[str]
    # Coaching
    preferred_coaching_style: Optional[str]
    # Insights & actions
    preference_insights: List[str]
    recommendation_boosts: List[str]
    generated_at: str


# ── Feedback CRUD ─────────────────────────────────────────────────

def save_workout_feedback(collection: Any, feedback: WorkoutFeedback) -> str:
    collection.insert_one({"feedback_type": "workout", **feedback.model_dump()})
    return feedback.id


def save_meal_feedback(collection: Any, feedback: MealFeedback) -> str:
    collection.insert_one({"feedback_type": "meal", **feedback.model_dump()})
    return feedback.id


def get_workout_feedbacks(collection: Any, user_id: str) -> List[WorkoutFeedback]:
    docs = list(collection.find(
        {"user_id": user_id, "feedback_type": "workout"},
        {"_id": 0},
    ))
    return [WorkoutFeedback(**{k: v for k, v in d.items() if k != "feedback_type"})
            for d in docs]


def get_meal_feedbacks(collection: Any, user_id: str) -> List[MealFeedback]:
    docs = list(collection.find(
        {"user_id": user_id, "feedback_type": "meal"},
        {"_id": 0},
    ))
    return [MealFeedback(**{k: v for k, v in d.items() if k != "feedback_type"})
            for d in docs]


# ── Duration and time helpers ─────────────────────────────────────

def _duration_bucket(minutes: int) -> str:
    if minutes <= 15:  return "0-15 min"
    if minutes <= 30:  return "16-30 min"
    if minutes <= 45:  return "31-45 min"
    if minutes <= 60:  return "46-60 min"
    return "60+ min"


def _time_category(workout_time: str) -> str:
    wt = (workout_time or "").lower().strip()
    if wt in ("morning", "afternoon", "evening"):
        return wt
    try:
        hour = int(wt.replace(".", ":").split(":")[0])
        if 5 <= hour < 12:   return "morning"
        if 12 <= hour < 17:  return "afternoon"
        return "evening"
    except (ValueError, IndexError):
        return "unknown"


def _avg(vals: list) -> Optional[float]:
    return round(sum(vals) / len(vals), 3) if vals else None


def _confidence_level(n: int) -> str:
    if n < LOW_THRESHOLD:    return "low"
    if n < MEDIUM_THRESHOLD: return "medium"
    return "high"


# ── Step 3: Workout Type Preference ──────────────────────────────

def _compute_workout_type_preferences(
    records: List[DecisionRecord],
    feedbacks: List[WorkoutFeedback],
) -> List[WorkoutTypePreference]:
    """
    For each workout type with >= MIN_OCCURRENCES in history, compute
    a preference score combining implicit (completion) and explicit (feedback).
    """
    # Implicit: group completion rates by workout type
    type_completions: Dict[str, List[float]] = {}
    for r in records:
        if r.outcome is None:
            continue
        wt = r.decision.workout_type
        type_completions.setdefault(wt, []).append(
            r.outcome.workout_completion_percentage
        )

    # Explicit: group feedback scores by workout type
    type_feedback: Dict[str, List[int]] = {}
    for fb in feedbacks:
        type_feedback.setdefault(fb.workout_type, []).append(fb.score)

    results: List[WorkoutTypePreference] = []
    for wt, completions in type_completions.items():
        if len(completions) < MIN_OCCURRENCES:
            continue

        completion_rate = (_avg(completions) or 0.0) / 100.0
        completion_rate = max(0.0, min(1.0, completion_rate))

        fb_scores = type_feedback.get(wt, [])
        if fb_scores:
            net = sum(fb_scores)
            explicit_factor = 0.5 + (net / len(fb_scores)) * 0.5
            explicit_factor = max(0.0, min(1.0, explicit_factor))
        else:
            explicit_factor = 0.5  # neutral when no feedback

        preference_score = round(
            completion_rate * 0.7 + explicit_factor * 0.3, 3
        )

        if preference_score >= PREFERRED_THRESHOLD:
            classification = "preferred"
        elif preference_score <= DISLIKED_THRESHOLD:
            classification = "disliked"
        else:
            classification = "neutral"

        results.append(WorkoutTypePreference(
            workout_type=wt,
            preference_score=preference_score,
            completion_rate=round(completion_rate, 3),
            times_selected=len(completions),
            explicit_factor=round(explicit_factor, 3),
            classification=classification,
        ))

    return sorted(results, key=lambda x: x.preference_score, reverse=True)


# ── Step 4: Duration Preference ───────────────────────────────────

def _analyze_duration_preference(
    records: List[DecisionRecord],
) -> Optional[str]:
    """Return the duration bucket with the highest average completion rate."""
    bucket_completions: Dict[str, List[float]] = {}
    for r in records:
        if r.outcome is None:
            continue
        bucket = _duration_bucket(r.decision.workout_duration_recommended)
        bucket_completions.setdefault(bucket, []).append(
            r.outcome.workout_completion_percentage
        )

    eligible = {b: v for b, v in bucket_completions.items() if len(v) >= MIN_OCCURRENCES}
    if not eligible:
        return None

    return max(eligible, key=lambda b: _avg(eligible[b]) or 0)


# ── Step 5: Time Preference ───────────────────────────────────────

def _analyze_time_preference(
    records: List[DecisionRecord],
) -> Optional[str]:
    """Return the time-of-day with the highest workout completion rate."""
    time_completions: Dict[str, List[bool]] = {}
    for r in records:
        if r.outcome is None:
            continue
        cat = _time_category(r.decision.workout_time)
        if cat == "unknown":
            continue
        time_completions.setdefault(cat, []).append(r.outcome.completed_workout)

    eligible = {t: v for t, v in time_completions.items() if len(v) >= MIN_OCCURRENCES}
    if not eligible:
        return None

    return max(eligible, key=lambda t: sum(eligible[t]) / len(eligible[t]))


# ── Step 7: Delivery Location Preference ─────────────────────────

def _analyze_delivery_preference(
    records: List[DecisionRecord],
) -> Optional[str]:
    """Return the delivery location with the highest meal adherence."""
    loc_scores: Dict[str, List[float]] = {}
    for r in records:
        if r.outcome is None:
            continue
        loc = r.decision.delivery_location
        score = (
            100.0 if (r.outcome.meal_ordered and r.outcome.meal_confirmed)
            else 50.0 if r.outcome.meal_ordered
            else 0.0
        )
        loc_scores.setdefault(loc, []).append(score)

    eligible = {loc: v for loc, v in loc_scores.items() if len(v) >= MIN_OCCURRENCES}
    if not eligible:
        return None

    return max(eligible, key=lambda l: _avg(eligible[l]) or 0)


# ── Step 6: Meal Category + Provider Preference ───────────────────

def _analyze_meal_preferences(
    feedbacks: List[MealFeedback],
) -> tuple[List[str], List[str]]:
    """
    Returns (preferred_categories, preferred_providers) from positive feedback.
    """
    cat_scores: Dict[str, List[int]] = {}
    provider_scores: Dict[str, List[int]] = {}

    for fb in feedbacks:
        if fb.category:
            cat_scores.setdefault(fb.category, []).append(fb.score)
        if fb.provider:
            provider_scores.setdefault(fb.provider, []).append(fb.score)

    preferred_cats = [
        c for c, scores in cat_scores.items()
        if sum(scores) / len(scores) > 0 and len(scores) >= 2
    ]
    preferred_providers = [
        p for p, scores in provider_scores.items()
        if sum(scores) / len(scores) > 0 and len(scores) >= 2
    ]

    return preferred_cats, preferred_providers


# ── Step 8: Coaching Style Preference ────────────────────────────

def _infer_coaching_style(
    feedbacks: List[WorkoutFeedback],
) -> Optional[str]:
    """
    Return the coaching style that produced the most positive feedback.
    Returns None if no coaching style feedback exists.
    """
    style_scores: Dict[str, List[int]] = {}
    for fb in feedbacks:
        if fb.coaching_style and fb.coaching_style in COACHING_STYLES:
            style_scores.setdefault(fb.coaching_style, []).append(fb.score)

    eligible = {s: v for s, v in style_scores.items() if len(v) >= 2}
    if not eligible:
        return None

    best = max(eligible, key=lambda s: sum(eligible[s]) / len(eligible[s]))
    avg_score = sum(eligible[best]) / len(eligible[best])
    return best if avg_score > 0 else None


# ── Insights builder ──────────────────────────────────────────────

def _build_insights(
    type_prefs: List[WorkoutTypePreference],
    preferred_time: Optional[str],
    preferred_bucket: Optional[str],
    preferred_location: Optional[str],
    preferred_categories: List[str],
    preferred_coaching: Optional[str],
) -> tuple[List[str], List[str]]:
    """Returns (preference_insights, recommendation_boosts)."""
    insights: List[str] = []
    boosts: List[str] = []

    preferred = [p for p in type_prefs if p.classification == "preferred"]
    disliked  = [p for p in type_prefs if p.classification == "disliked"]

    for p in preferred[:3]:
        insights.append(
            f"You complete {p.workout_type.replace('_', ' ')} workouts "
            f"{p.completion_rate*100:.0f}% of the time — one of your highest adherence types."
        )
    for p in disliked[:2]:
        insights.append(
            f"Your adherence to {p.workout_type.replace('_', ' ')} workouts is low "
            f"({p.completion_rate*100:.0f}%) — the AI will deprioritize this type."
        )
    if preferred_time:
        insights.append(
            f"You perform best with {preferred_time} workouts based on your completion history."
        )
    if preferred_bucket:
        insights.append(
            f"Your preferred workout duration is {preferred_bucket} based on adherence data."
        )
    if preferred_location:
        insights.append(
            f"You adhere best to {preferred_location} meal deliveries."
        )
    if preferred_categories:
        insights.append(
            f"Preferred meal styles based on your feedback: {', '.join(preferred_categories[:3])}."
        )
    if preferred_coaching:
        insights.append(
            f"You respond best to a {preferred_coaching} coaching style."
        )

    boosts = [
        f"Prioritize {p.workout_type.replace('_', ' ')} sessions"
        for p in preferred[:3]
    ]
    if preferred_time:
        boosts.append(f"Schedule workouts in the {preferred_time}")
    if preferred_location:
        boosts.append(f"Default meal delivery to {preferred_location}")

    return insights, boosts


# ── Main entry point ──────────────────────────────────────────────

def compute_preference_profile(
    user_id: str,
    records: List[DecisionRecord],
    workout_feedbacks: List[WorkoutFeedback],
    meal_feedbacks: List[MealFeedback],
) -> UserPreferenceProfile:
    """
    Computes a full UserPreferenceProfile from historical records and feedback.
    All failures are non-critical — the profile always returns.
    """
    records_with_outcomes = [r for r in records if r.outcome is not None]
    total = len(records_with_outcomes)
    confidence = _confidence_level(total)

    type_prefs: List[WorkoutTypePreference] = []
    preferred_time: Optional[str] = None
    preferred_bucket: Optional[str] = None
    preferred_location: Optional[str] = None
    preferred_categories: List[str] = []
    preferred_providers: List[str] = []
    preferred_coaching: Optional[str] = None

    try:
        type_prefs = _compute_workout_type_preferences(records_with_outcomes, workout_feedbacks)
    except Exception:
        pass

    try:
        preferred_bucket = _analyze_duration_preference(records_with_outcomes)
    except Exception:
        pass

    try:
        preferred_time = _analyze_time_preference(records_with_outcomes)
    except Exception:
        pass

    try:
        preferred_location = _analyze_delivery_preference(records_with_outcomes)
    except Exception:
        pass

    try:
        preferred_categories, preferred_providers = _analyze_meal_preferences(meal_feedbacks)
    except Exception:
        pass

    try:
        preferred_coaching = _infer_coaching_style(workout_feedbacks)
    except Exception:
        pass

    preferred_types = [p.workout_type for p in type_prefs if p.classification == "preferred"]
    disliked_types  = [p.workout_type for p in type_prefs if p.classification == "disliked"]

    insights, boosts = _build_insights(
        type_prefs, preferred_time, preferred_bucket,
        preferred_location, preferred_categories, preferred_coaching,
    )

    return UserPreferenceProfile(
        user_id=user_id,
        confidence_level=confidence,
        total_decisions_analyzed=total,
        preferred_workout_types=preferred_types,
        disliked_workout_types=disliked_types,
        workout_type_scores=type_prefs,
        preferred_workout_time=preferred_time,
        preferred_duration_bucket=preferred_bucket,
        preferred_delivery_location=preferred_location,
        preferred_meal_categories=preferred_categories,
        preferred_providers=preferred_providers,
        preferred_coaching_style=preferred_coaching,
        preference_insights=insights,
        recommendation_boosts=boosts,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


# ── Preference note for DailyDecisionEngine ───────────────────────

def build_preference_note(
    profile: UserPreferenceProfile,
    selected_workout_type: str,
    recommended_duration: int,
) -> Optional[str]:
    """
    Returns a human-readable note explaining preference-driven adjustments.
    Returns None when no actionable preference applies.
    """
    if profile.confidence_level == "low":
        return None

    # Was a preferred type selected?
    if selected_workout_type in profile.preferred_workout_types:
        matching = next(
            (p for p in profile.workout_type_scores if p.workout_type == selected_workout_type),
            None,
        )
        if matching and matching.completion_rate >= 0.65:
            return (
                f"Selected {selected_workout_type.replace('_', ' ')} because your adherence "
                f"and feedback are consistently higher for this workout type "
                f"({matching.completion_rate*100:.0f}% completion rate)."
            )

    # Was a disliked type selected (unavoidable)?
    if selected_workout_type in profile.disliked_workout_types:
        return (
            f"Note: {selected_workout_type.replace('_', ' ')} was selected based on today's "
            f"physiological conditions. This type has lower adherence in your history — "
            f"a shorter session may help."
        )

    return None
