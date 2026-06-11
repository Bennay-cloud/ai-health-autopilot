"""
Decision Tracking Service.

Captures the full lifecycle:  Context → Decision → User Action → Outcome

Used to build an ML-ready dataset for future compliance/churn prediction models.
"""
from __future__ import annotations

from typing import List, Optional, Any
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, Field
import uuid


# ── Sub-models ────────────────────────────────────────────────────

class RecordContext(BaseModel):
    sleep_hours: float
    stress_level: int
    mood: int
    meetings: int
    travel: bool
    cycle_phase: Optional[str]
    previous_workout: Optional[str]
    goal: str
    recovery_score: int
    energy_score: int
    stress_score: int
    context_flags: List[str]


class RecordDecision(BaseModel):
    day_type: str
    workout_type: str
    workout_duration_recommended: int
    workout_intensity: str
    selected_lunch: str
    selected_dinner: str
    meal_calories: int
    delivery_location: str
    workout_time: str
    sleep_target: str


class RecordOutcome(BaseModel):
    completed_workout: bool
    workout_duration_completed: int
    workout_completion_percentage: float
    meal_ordered: bool
    meal_confirmed: bool
    sleep_target_achieved: bool
    overall_completion_percentage: float


class DecisionRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    date: str
    context: RecordContext
    decision: RecordDecision
    outcome: Optional[RecordOutcome] = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class OutcomeInput(BaseModel):
    completed_workout: bool
    workout_duration_completed: int
    meal_ordered: bool
    meal_confirmed: bool
    sleep_target_achieved: bool


# ── Calculation helpers ───────────────────────────────────────────

def calculate_workout_completion(recommended: int, completed: int) -> float:
    if recommended <= 0:
        return 100.0 if completed > 0 else 0.0
    return round(min((completed / recommended) * 100, 100), 1)


def calculate_overall_completion(
    workout_pct: float,
    meal_ordered: bool,
    meal_confirmed: bool,
    sleep_achieved: bool,
) -> float:
    """
    Weights: Workout 50%, Meals 30%, Sleep 20%.
    Meal score = 100 if ordered+confirmed, 50 if only ordered, 0 otherwise.
    """
    meal_score = 100.0 if (meal_ordered and meal_confirmed) else (50.0 if meal_ordered else 0.0)
    sleep_score = 100.0 if sleep_achieved else 0.0
    return round(workout_pct * 0.5 + meal_score * 0.3 + sleep_score * 0.2, 1)


def build_outcome(inp: OutcomeInput, recommended_duration: int) -> RecordOutcome:
    workout_pct = calculate_workout_completion(
        recommended_duration, inp.workout_duration_completed
    )
    overall_pct = calculate_overall_completion(
        workout_pct, inp.meal_ordered, inp.meal_confirmed, inp.sleep_target_achieved
    )
    return RecordOutcome(
        completed_workout=inp.completed_workout,
        workout_duration_completed=inp.workout_duration_completed,
        workout_completion_percentage=workout_pct,
        meal_ordered=inp.meal_ordered,
        meal_confirmed=inp.meal_confirmed,
        sleep_target_achieved=inp.sleep_target_achieved,
        overall_completion_percentage=overall_pct,
    )


# ── MongoDB CRUD ──────────────────────────────────────────────────

def create_record(collection: Any, record: DecisionRecord) -> str:
    doc = record.model_dump()
    collection.insert_one(doc)
    return record.id


def get_record(collection: Any, record_id: str) -> Optional[DecisionRecord]:
    doc = collection.find_one({"id": record_id}, {"_id": 0})
    if doc is None:
        return None
    return DecisionRecord(**doc)


def update_record_outcome(
    collection: Any,
    record_id: str,
    outcome: RecordOutcome,
) -> Optional[DecisionRecord]:
    collection.update_one(
        {"id": record_id},
        {"$set": {"outcome": outcome.model_dump()}},
    )
    return get_record(collection, record_id)


def _period_filter(period: str) -> Optional[dict]:
    now = datetime.now(timezone.utc)
    if period == "7d":
        cutoff = (now - timedelta(days=7)).date().isoformat()
    elif period == "30d":
        cutoff = (now - timedelta(days=30)).date().isoformat()
    else:
        return None   # all time
    return {"date": {"$gte": cutoff}}


def get_user_history(
    collection: Any,
    user_id: str,
    period: str = "all",
) -> List[DecisionRecord]:
    query: dict = {"user_id": user_id}
    date_filter = _period_filter(period)
    if date_filter:
        query.update(date_filter)
    docs = list(collection.find(query, {"_id": 0}).sort("date", -1))
    return [DecisionRecord(**d) for d in docs]


# ── Adherence metrics ─────────────────────────────────────────────

class AdherenceMetrics(BaseModel):
    workout_adherence: float
    meal_adherence: float
    sleep_adherence: float
    overall_adherence: float
    total_days_tracked: int


def get_user_adherence(collection: Any, user_id: str) -> AdherenceMetrics:
    records = get_user_history(collection, user_id, period="all")
    completed = [r for r in records if r.outcome is not None]
    total = len(completed)

    if total == 0:
        return AdherenceMetrics(
            workout_adherence=0.0,
            meal_adherence=0.0,
            sleep_adherence=0.0,
            overall_adherence=0.0,
            total_days_tracked=0,
        )

    workout_pcts = [r.outcome.workout_completion_percentage for r in completed]  # type: ignore[union-attr]
    meal_scores = [
        100.0
        if (r.outcome.meal_ordered and r.outcome.meal_confirmed)  # type: ignore[union-attr]
        else (50.0 if r.outcome.meal_ordered else 0.0)  # type: ignore[union-attr]
        for r in completed
    ]
    sleep_scores = [100.0 if r.outcome.sleep_target_achieved else 0.0 for r in completed]  # type: ignore[union-attr]
    overall_scores = [r.outcome.overall_completion_percentage for r in completed]  # type: ignore[union-attr]

    return AdherenceMetrics(
        workout_adherence=round(sum(workout_pcts) / total, 1),
        meal_adherence=round(sum(meal_scores) / total, 1),
        sleep_adherence=round(sum(sleep_scores) / total, 1),
        overall_adherence=round(sum(overall_scores) / total, 1),
        total_days_tracked=total,
    )


# ── ML-ready dataset export ───────────────────────────────────────

def export_training_dataset(collection: Any, outcomes_collection: Any = None) -> List[dict]:
    """
    Returns a flat list of dicts, one per day with a recorded outcome.
    Suitable for XGBoost / LightGBM / RandomForest / Deep Learning.

    Per-row running stats (computed chronologically per user, no data leakage):
      adherence_score   — running average overall_completion_percentage
      current_streak    — consecutive qualifying days up to this record
      best_streak       — longest qualifying run up to this record
      at_risk           — adherence < 40 OR last 3 outcomes all < 50%

    When outcomes_collection is provided, each row is enriched with:
      outcome_mood / outcome_energy / outcome_stress / outcome_sleep_hours
        — same-day check-in values
      weight_kg / waist_cm / body_fat_percentage
        — same-day physical measurements
      mood_next_day / energy_next_day / stress_next_day
        — next-day check-in values (for ML target variables)
      outcome_trend_score
        — running per-user composite health score (1-10)
    """
    from collections import defaultdict
    from datetime import date as _date_cls

    # Build outcome lookup: {user_id: {date: doc}} when available
    outcomes_lookup: dict = {}
    if outcomes_collection is not None:
        for od in outcomes_collection.find({}, {"_id": 0}):
            uid = od.get("user_id", "")
            dt  = od.get("date", "")
            outcomes_lookup.setdefault(uid, {})[dt] = od

    docs = list(collection.find({"outcome": {"$ne": None}}, {"_id": 0}))

    # Group by user and sort each user's records chronologically
    user_docs: dict = defaultdict(list)
    for doc in docs:
        user_docs[doc.get("user_id", "unknown")].append(doc)

    def _duration_bucket_label(minutes: int) -> str:
        if minutes <= 15:  return "0-15 min"
        if minutes <= 30:  return "16-30 min"
        if minutes <= 45:  return "31-45 min"
        if minutes <= 60:  return "46-60 min"
        return "60+ min"

    def _time_cat(workout_time: str) -> str:
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

    rows = []
    for user_id_key, user_records in user_docs.items():
        user_records.sort(key=lambda d: d.get("date", ""))
        running_pcts: List[float] = []
        running_outcome_composites: List[float] = []
        user_outcomes = outcomes_lookup.get(user_id_key, {})
        # Personal learning running state (reset per user)
        bucket_data_map: dict = {}
        time_data_map: dict = {}
        stress_pcts: List[float] = []
        travel_pcts: List[float] = []
        running_meal_scores: List[float] = []
        running_sleep_scores: List[float] = []

        for doc in user_records:
            ctx = doc.get("context", {})
            dec = doc.get("decision", {})
            out = doc.get("outcome", {})
            overall = out.get("overall_completion_percentage", 0.0)
            running_pcts.append(overall)

            # Running adherence score
            adherence_score = round(sum(running_pcts) / len(running_pcts), 1)

            # Current streak ending at this record
            current_streak = 0
            for pct in reversed(running_pcts):
                if pct >= 50:
                    current_streak += 1
                else:
                    break

            # Best streak up to this record
            best_streak = 0
            run = 0
            for pct in running_pcts:
                if pct >= 50:
                    run += 1
                    best_streak = max(best_streak, run)
                else:
                    run = 0

            # AT_RISK flag
            at_risk = adherence_score < 40 or (
                len(running_pcts) >= 3
                and all(p < 50 for p in running_pcts[-3:])
            )

            # --- Outcome record enrichment ---
            doc_date = doc.get("date", "")
            today_outcome_doc = user_outcomes.get(doc_date, {})
            today_daily  = (today_outcome_doc or {}).get("daily_outcomes") or {}
            today_weekly = (today_outcome_doc or {}).get("weekly_outcomes") or {}

            try:
                next_date_str = (
                    _date_cls.fromisoformat(doc_date) + timedelta(days=1)
                ).isoformat() if doc_date else None
            except (ValueError, AttributeError):
                next_date_str = None
            next_outcome_doc = user_outcomes.get(next_date_str, {}) if next_date_str else {}
            next_daily = (next_outcome_doc or {}).get("daily_outcomes") or {}

            # Running outcome trend score (composite 1-10, no data leakage)
            if today_daily:
                composite = (
                    today_daily.get("mood", 5)
                    + today_daily.get("energy", 5)
                    + (10 - today_daily.get("stress", 5))
                ) / 3
                running_outcome_composites.append(composite)
            outcome_trend_score = (
                round(sum(running_outcome_composites) / len(running_outcome_composites), 2)
                if running_outcome_composites else None
            )

            # --- Personal Learning features (running per-user, no data leakage) ---
            # Duration bucket adherence: track best bucket by running avg completion
            wo_dur = dec.get("workout_duration_recommended") or 0
            dur_bucket = _duration_bucket_label(wo_dur)
            bucket_data_map.setdefault(dur_bucket, []).append(
                out.get("workout_completion_percentage") or 0.0
            )
            best_dur_bucket = max(
                bucket_data_map,
                key=lambda b: sum(bucket_data_map[b]) / len(bucket_data_map[b])
                if bucket_data_map[b] else 0,
            )

            # Time-of-day adherence: track completion by time category
            wt_cat = _time_cat(dec.get("workout_time") or "")
            time_data_map.setdefault(wt_cat, []).append(
                bool(out.get("completed_workout"))
            )
            best_workout_time = max(
                (t for t in time_data_map if t != "unknown"),
                key=lambda t: sum(time_data_map[t]) / len(time_data_map[t])
                if time_data_map.get(t) else 0,
                default=wt_cat,
            )

            # Stress adherence rate: running avg completion on high-stress days
            sl = ctx.get("stress_level") or 0
            stress_pcts.append(out.get("workout_completion_percentage") or 0.0) if sl >= 7 else None
            stress_adherence_rate = (
                round(sum(stress_pcts) / len(stress_pcts), 1) if stress_pcts else None
            )

            # Travel adherence rate
            if ctx.get("travel"):
                travel_pcts.append(out.get("overall_completion_percentage") or 0.0)
            travel_adherence_rate = (
                round(sum(travel_pcts) / len(travel_pcts), 1) if travel_pcts else None
            )

            # Meal adherence rate (running)
            meal_score = (
                100.0 if (out.get("meal_ordered") and out.get("meal_confirmed"))
                else 50.0 if out.get("meal_ordered") else 0.0
            )
            running_meal_scores.append(meal_score)
            meal_adherence_rate = round(sum(running_meal_scores) / len(running_meal_scores), 1)

            # Sleep adherence rate (running)
            sleep_score = 100.0 if out.get("sleep_target_achieved") else 0.0
            running_sleep_scores.append(sleep_score)
            sleep_adherence_rate = round(sum(running_sleep_scores) / len(running_sleep_scores), 1)

            # Personal learning confidence tier
            n = len(running_pcts)
            personal_learning_confidence = (
                "high" if n >= 30 else "medium" if n >= 7 else "low"
            )

            rows.append({
                # --- Context features ---
                "sleep_hours": ctx.get("sleep_hours"),
                "stress_level": ctx.get("stress_level"),
                "mood": ctx.get("mood"),
                "meetings": ctx.get("meetings"),
                "travel": ctx.get("travel"),
                "cycle_phase": ctx.get("cycle_phase"),
                "previous_workout": ctx.get("previous_workout"),
                "recovery_score": ctx.get("recovery_score"),
                "energy_score": ctx.get("energy_score"),
                "stress_score": ctx.get("stress_score"),
                # --- Decision features ---
                "day_type": dec.get("day_type"),
                "workout_type": dec.get("workout_type"),
                "workout_duration_recommended": dec.get("workout_duration_recommended"),
                "workout_intensity": dec.get("workout_intensity"),
                # --- Outcome labels ---
                "completed_workout": out.get("completed_workout"),
                "workout_duration_completed": out.get("workout_duration_completed"),
                "workout_completion_percentage": out.get("workout_completion_percentage"),
                "meal_ordered": out.get("meal_ordered"),
                "meal_confirmed": out.get("meal_confirmed"),
                "sleep_target_achieved": out.get("sleep_target_achieved"),
                "overall_completion_percentage": overall,
                # --- ML adherence features ---
                "adherence_score": adherence_score,
                "current_streak": current_streak,
                "best_streak": best_streak,
                "at_risk": at_risk,
                # --- Outcome tracking features ---
                "outcome_mood": today_daily.get("mood") if today_daily else None,
                "outcome_energy": today_daily.get("energy") if today_daily else None,
                "outcome_stress": today_daily.get("stress") if today_daily else None,
                "outcome_sleep_hours": today_daily.get("sleep_hours") if today_daily else None,
                "weight_kg": today_weekly.get("weight_kg") if today_weekly else None,
                "waist_cm": today_weekly.get("waist_cm") if today_weekly else None,
                "body_fat_percentage": today_weekly.get("body_fat_percentage") if today_weekly else None,
                "mood_next_day": next_daily.get("mood") if next_daily else None,
                "energy_next_day": next_daily.get("energy") if next_daily else None,
                "stress_next_day": next_daily.get("stress") if next_daily else None,
                "outcome_trend_score": outcome_trend_score,
                # --- Personal learning features (Step 14) ---
                "best_workout_duration_bucket": best_dur_bucket,
                "best_workout_time": best_workout_time,
                "stress_adherence_rate": stress_adherence_rate,
                "travel_adherence_rate": travel_adherence_rate,
                "meal_adherence_rate": meal_adherence_rate,
                "sleep_adherence_rate": sleep_adherence_rate,
                "personal_learning_confidence": personal_learning_confidence,
            })
    return rows
