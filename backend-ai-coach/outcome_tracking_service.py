"""
Outcome Tracking Engine.

Tracks whether AI recommendations are actually improving health outcomes.
Measures real results: stress, energy, weight, mood, sleep trends.
"""
from __future__ import annotations

from typing import List, Optional, Any
from datetime import datetime, timedelta, timezone, date as _date
from pydantic import BaseModel, Field
import uuid


# ── Models ────────────────────────────────────────────────────────

class DailyOutcomes(BaseModel):
    mood: float = Field(..., ge=1, le=10)
    energy: float = Field(..., ge=1, le=10)
    stress: float = Field(..., ge=1, le=10)
    sleep_hours: float = Field(..., ge=0, le=24)
    notes: Optional[str] = None


class WeeklyOutcomes(BaseModel):
    weight_kg: Optional[float] = None
    waist_cm: Optional[float] = None
    body_fat_percentage: Optional[float] = None


class OutcomeRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    date: str  # YYYY-MM-DD
    daily_outcomes: Optional[DailyOutcomes] = None
    weekly_outcomes: Optional[WeeklyOutcomes] = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class OutcomeTrends(BaseModel):
    mood_change: Optional[float] = None
    energy_change: Optional[float] = None
    stress_change: Optional[float] = None
    sleep_change: Optional[float] = None
    weight_change: Optional[float] = None
    waist_change: Optional[float] = None
    body_fat_change: Optional[float] = None


class OutcomeInsights(BaseModel):
    wins: List[str]
    warnings: List[str]
    summary: str


class DecisionEffectiveness(BaseModel):
    recovery_day_effectiveness: int  # 0-100
    meal_effectiveness: int
    workout_effectiveness: int


# ── CRUD ──────────────────────────────────────────────────────────

def _today_str() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def save_daily_outcome(
    collection: Any,
    user_id: str,
    daily: DailyOutcomes,
    date: Optional[str] = None,
) -> OutcomeRecord:
    target_date = date or _today_str()
    existing = collection.find_one({"user_id": user_id, "date": target_date}, {"_id": 0})
    if existing:
        record = OutcomeRecord(**existing)
        record.daily_outcomes = daily
    else:
        record = OutcomeRecord(user_id=user_id, date=target_date, daily_outcomes=daily)
    collection.update_one(
        {"user_id": user_id, "date": target_date},
        {"$set": record.model_dump()},
        upsert=True,
    )
    return record


def save_weekly_outcome(
    collection: Any,
    user_id: str,
    weekly: WeeklyOutcomes,
    date: Optional[str] = None,
) -> OutcomeRecord:
    target_date = date or _today_str()
    existing = collection.find_one({"user_id": user_id, "date": target_date}, {"_id": 0})
    if existing:
        record = OutcomeRecord(**existing)
        record.weekly_outcomes = weekly
    else:
        record = OutcomeRecord(user_id=user_id, date=target_date, weekly_outcomes=weekly)
    collection.update_one(
        {"user_id": user_id, "date": target_date},
        {"$set": record.model_dump()},
        upsert=True,
    )
    return record


def get_user_outcomes(
    collection: Any,
    user_id: str,
    days: Optional[int] = None,
) -> List[OutcomeRecord]:
    query: dict = {"user_id": user_id}
    if days is not None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
        query["date"] = {"$gte": cutoff}
    cursor = collection.find(query, {"_id": 0})
    docs = list(cursor.sort("date", 1))
    return [OutcomeRecord(**d) for d in docs]


# ── Analytics ─────────────────────────────────────────────────────

def _avg(vals: list) -> Optional[float]:
    if not vals:
        return None
    return sum(vals) / len(vals)


def calculate_outcome_trends(
    collection: Any,
    user_id: str,
    reference_date: Optional[_date] = None,
) -> OutcomeTrends:
    ref = reference_date or datetime.now(timezone.utc).date()

    this_end   = ref.isoformat()
    this_start = (ref - timedelta(days=6)).isoformat()
    prev_end   = (ref - timedelta(days=7)).isoformat()
    prev_start = (ref - timedelta(days=13)).isoformat()

    records = get_user_outcomes(collection, user_id)

    this_week = [r for r in records if r.daily_outcomes and this_start <= r.date <= this_end]
    prev_week = [r for r in records if r.daily_outcomes and prev_start <= r.date <= prev_end]

    def daily_change(attr: str) -> Optional[float]:
        curr = _avg([getattr(r.daily_outcomes, attr) for r in this_week])
        prev = _avg([getattr(r.daily_outcomes, attr) for r in prev_week])
        if curr is None or prev is None:
            return None
        return round(curr - prev, 2)

    # Physical metrics: oldest vs latest available value
    all_weekly = [r for r in records if r.weekly_outcomes is not None]
    weight_vals = [r.weekly_outcomes.weight_kg for r in all_weekly if r.weekly_outcomes.weight_kg is not None]
    waist_vals  = [r.weekly_outcomes.waist_cm  for r in all_weekly if r.weekly_outcomes.waist_cm  is not None]
    bf_vals     = [r.weekly_outcomes.body_fat_percentage for r in all_weekly if r.weekly_outcomes.body_fat_percentage is not None]

    def oldest_latest_change(vals: list) -> Optional[float]:
        if len(vals) < 2:
            return None
        return round(vals[-1] - vals[0], 2)

    return OutcomeTrends(
        mood_change=daily_change("mood"),
        energy_change=daily_change("energy"),
        stress_change=daily_change("stress"),
        sleep_change=daily_change("sleep_hours"),
        weight_change=oldest_latest_change(weight_vals),
        waist_change=oldest_latest_change(waist_vals),
        body_fat_change=oldest_latest_change(bf_vals),
    )


def generate_outcome_insights(
    collection: Any,
    user_id: str,
    reference_date: Optional[_date] = None,
) -> OutcomeInsights:
    trends = calculate_outcome_trends(collection, user_id, reference_date)
    wins: List[str] = []
    warnings: List[str] = []

    # (field, label, higher_is_better)
    checks = [
        ("mood_change",     "Mood",     True),
        ("energy_change",   "Energy",   True),
        ("stress_change",   "Stress",   False),
        ("sleep_change",    "Sleep",    True),
        ("weight_change",   "Weight",   False),
        ("waist_change",    "Waist",    False),
        ("body_fat_change", "Body fat", False),
    ]
    PHYSICAL = {"weight_change", "waist_change", "body_fat_change"}

    for field, label, higher_is_better in checks:
        val = getattr(trends, field)
        if val is None:
            continue
        threshold = 0.1 if field in PHYSICAL else 0.3
        improved = (val > 0) if higher_is_better else (val < 0)
        declined = (val < 0) if higher_is_better else (val > 0)

        if improved and abs(val) >= threshold:
            direction = "increased" if val > 0 else "decreased"
            wins.append(f"{label} {direction} by {abs(val):.1f}")
        elif declined and abs(val) >= threshold:
            direction = "decreased" if val < 0 else "increased"
            warnings.append(f"{label} {direction} by {abs(val):.1f} — keep an eye on this")

    if len(wins) > len(warnings):
        summary = "Overall health trend is positive."
    elif len(warnings) > len(wins):
        summary = "Some areas need attention — focus on consistency."
    elif wins:
        summary = "Mixed results — some improvements with areas to watch."
    else:
        summary = "Not enough data yet to assess your trend."

    return OutcomeInsights(wins=wins, warnings=warnings, summary=summary)


def evaluate_decision_effectiveness(
    outcomes_collection: Any,
    decisions_collection: Any,
    user_id: str,
) -> DecisionEffectiveness:
    """
    Measures if specific AI recommendations produce better next-day outcomes.
      - Recovery day  → lower stress next day
      - Meal confirmed → higher energy next day
      - Workout completed → better mood next day
    Score = percentage of qualifying days with a positive outcome (0-100).
    Returns 50 when no data is available (neutral).
    """
    from decision_record_service import get_user_history

    decisions = get_user_history(decisions_collection, user_id)
    outcomes  = get_user_outcomes(outcomes_collection, user_id)
    outcome_by_date = {r.date: r for r in outcomes}

    def _next_day_str(date_str: str) -> str:
        return (_date.fromisoformat(date_str) + timedelta(days=1)).isoformat()

    def _score(wins: int, total: int) -> int:
        return 50 if total == 0 else round((wins / total) * 100)

    rec_win = rec_total = 0
    meal_win = meal_total = 0
    wo_win = wo_total = 0

    for d in decisions:
        today_out = outcome_by_date.get(d.date)
        next_out  = outcome_by_date.get(_next_day_str(d.date))
        has_both  = (
            today_out and today_out.daily_outcomes and
            next_out  and next_out.daily_outcomes
        )
        if not has_both:
            continue
        today_daily = today_out.daily_outcomes  # type: ignore[union-attr]
        next_daily  = next_out.daily_outcomes   # type: ignore[union-attr]

        if d.decision.day_type == "recovery":
            rec_total += 1
            if next_daily.stress < today_daily.stress:
                rec_win += 1

        if d.outcome and d.outcome.meal_confirmed:
            meal_total += 1
            if next_daily.energy > today_daily.energy:
                meal_win += 1

        if d.outcome and d.outcome.completed_workout:
            wo_total += 1
            if next_daily.mood > today_daily.mood:
                wo_win += 1

    return DecisionEffectiveness(
        recovery_day_effectiveness=_score(rec_win, rec_total),
        meal_effectiveness=_score(meal_win, meal_total),
        workout_effectiveness=_score(wo_win, wo_total),
    )
