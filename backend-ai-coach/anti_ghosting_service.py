"""
Anti-Ghosting Engine & Adherence Intelligence.

Responsibilities:
  - Streak calculation (current + best)
  - Weekly trend analysis (this week vs previous week)
  - AT_RISK detection (low adherence, consecutive skips, meal ghosting)
  - Adaptive recommendations (reduce friction when at-risk, progress when thriving)
  - Adherence insights (strengths, weaknesses, recommendations)
  - Dashboard data composition
"""
from __future__ import annotations

from typing import List, Optional
from datetime import date, timedelta
from pydantic import BaseModel

from decision_record_service import DecisionRecord, AdherenceMetrics


# ── Constants ─────────────────────────────────────────────────────

_INTENSITY_LEVELS = ["low", "moderate", "high"]

ADHERENCE_BADGE_THRESHOLDS = {"excellent": 85, "good": 70, "needs_attention": 50}


def adherence_badge(pct: float) -> str:
    if pct >= ADHERENCE_BADGE_THRESHOLDS["excellent"]:
        return "Excellent"
    if pct >= ADHERENCE_BADGE_THRESHOLDS["good"]:
        return "Good"
    if pct >= ADHERENCE_BADGE_THRESHOLDS["needs_attention"]:
        return "Needs Attention"
    return "At Risk"


def _reduce_intensity(intensity: str) -> str:
    idx = _INTENSITY_LEVELS.index(intensity) if intensity in _INTENSITY_LEVELS else 1
    return _INTENSITY_LEVELS[max(0, idx - 1)]


def _increase_intensity(intensity: str) -> str:
    idx = _INTENSITY_LEVELS.index(intensity) if intensity in _INTENSITY_LEVELS else 1
    return _INTENSITY_LEVELS[min(len(_INTENSITY_LEVELS) - 1, idx + 1)]


# ── Models ────────────────────────────────────────────────────────

class StreakResult(BaseModel):
    current_streak: int
    best_streak: int


class WeeklyTrends(BaseModel):
    workout_trend: float
    meal_trend: float
    sleep_trend: float
    overall_trend: float


class AdherenceInsights(BaseModel):
    strengths: List[str]
    weaknesses: List[str]
    recommendations: List[str]


class AtRiskResult(BaseModel):
    at_risk: bool
    reasons: List[str]
    adaptation_level: int   # 0=none 1=reduce 2=minimal 3=minimum_viable


class AdaptiveRecommendation(BaseModel):
    adjusted_workout_duration: int
    adjusted_intensity: str
    reason: str
    at_risk: bool
    adaptation_level: str   # maintain | reduce | minimal | minimum_viable | progress


class DashboardData(BaseModel):
    adherence: AdherenceMetrics
    streaks: StreakResult
    trends: WeeklyTrends
    insights: AdherenceInsights
    at_risk: AtRiskResult
    ai_insight: str


# ── Streak Calculation ────────────────────────────────────────────

def calculate_streak(records: List[DecisionRecord]) -> StreakResult:
    """
    A day counts toward the streak when overall_completion_percentage >= 50.
    current_streak: consecutive qualifying days counting backwards from most recent.
    best_streak: longest qualifying run ever.
    """
    completed = sorted(
        [r for r in records if r.outcome is not None],
        key=lambda r: r.date,
        reverse=True,
    )

    # Current streak (from most recent, backward)
    current_streak = 0
    for r in completed:
        if r.outcome.overall_completion_percentage >= 50:   # type: ignore[union-attr]
            current_streak += 1
        else:
            break

    # Best streak (scan ascending for longest contiguous run)
    best_streak = 0
    running = 0
    for r in reversed(completed):
        if r.outcome.overall_completion_percentage >= 50:   # type: ignore[union-attr]
            running += 1
            best_streak = max(best_streak, running)
        else:
            running = 0

    return StreakResult(current_streak=current_streak, best_streak=best_streak)


# ── Weekly Trends ─────────────────────────────────────────────────

def generate_weekly_trends(
    records: List[DecisionRecord],
    reference_date: Optional[date] = None,
) -> WeeklyTrends:
    """
    Compare last 7 days vs the previous 7 days.
    Positive delta = improvement; negative = decline.
    """
    today = reference_date or date.today()
    this_week_start = (today - timedelta(days=6)).isoformat()
    last_week_start = (today - timedelta(days=13)).isoformat()
    last_week_end   = (today - timedelta(days=7)).isoformat()

    completed = [r for r in records if r.outcome is not None]
    this_week = [r for r in completed if r.date >= this_week_start]
    last_week = [r for r in completed if last_week_start <= r.date <= last_week_end]

    def _avg(recs: list, fn) -> float:
        vals = [fn(r) for r in recs]
        return sum(vals) / len(vals) if vals else 0.0

    def _w(r): return r.outcome.workout_completion_percentage          # type: ignore[union-attr]
    def _m(r): return 100.0 if (r.outcome.meal_ordered and r.outcome.meal_confirmed) else (50.0 if r.outcome.meal_ordered else 0.0)  # type: ignore[union-attr]
    def _s(r): return 100.0 if r.outcome.sleep_target_achieved else 0.0  # type: ignore[union-attr]
    def _o(r): return r.outcome.overall_completion_percentage          # type: ignore[union-attr]

    return WeeklyTrends(
        workout_trend=round(_avg(this_week, _w) - _avg(last_week, _w), 1),
        meal_trend=round(_avg(this_week, _m) - _avg(last_week, _m), 1),
        sleep_trend=round(_avg(this_week, _s) - _avg(last_week, _s), 1),
        overall_trend=round(_avg(this_week, _o) - _avg(last_week, _o), 1),
    )


# ── AT_RISK Detection ─────────────────────────────────────────────

def detect_at_risk(
    records: List[DecisionRecord],
    adherence: AdherenceMetrics,
    reference_date: Optional[date] = None,
) -> AtRiskResult:
    """
    Triggers AT_RISK on any of:
      1. overall_adherence < 40 (with at least some tracked days)
      2. 3+ consecutive most-recent outcomes < 50%
      3. 7 days without a single meal_confirmed
    """
    today = reference_date or date.today()
    reasons: List[str] = []

    # Condition 1
    if adherence.total_days_tracked > 0 and adherence.overall_adherence < 40:
        reasons.append("Overall adherence below 40%")

    completed = sorted(
        [r for r in records if r.outcome is not None],
        key=lambda r: r.date,
        reverse=True,
    )

    # Condition 2: consecutive low days from most recent
    consecutive_low = 0
    for r in completed:
        if r.outcome.overall_completion_percentage < 50:    # type: ignore[union-attr]
            consecutive_low += 1
        else:
            break
    if consecutive_low >= 3:
        reasons.append(f"{consecutive_low} consecutive low-adherence days")

    # Condition 3: no meal confirmation in last 7 days
    cutoff = (today - timedelta(days=7)).isoformat()
    recent = [r for r in completed if r.date >= cutoff]
    if recent and not any(r.outcome.meal_confirmed for r in recent):  # type: ignore[union-attr]
        reasons.append("No meal confirmations in the last 7 days")

    # Determine adaptation level
    if consecutive_low >= 10:
        level = 3
    elif consecutive_low >= 6:
        level = 2
    elif reasons:
        level = 1
    else:
        level = 0

    return AtRiskResult(at_risk=bool(reasons), reasons=reasons, adaptation_level=level)


# ── Adherence Insights ────────────────────────────────────────────

def generate_adherence_insights(
    records: List[DecisionRecord],
    adherence: AdherenceMetrics,
) -> AdherenceInsights:
    completed = [r for r in records if r.outcome is not None]
    strengths: List[str] = []
    weaknesses: List[str] = []
    recommendations: List[str] = []

    # Workout
    if adherence.workout_adherence >= 80:
        strengths.append("Strong workout consistency")
    elif adherence.workout_adherence < 50:
        weaknesses.append("Low workout completion rate")
        recommendations.append("Schedule workouts at a fixed daily time")

    # Meals
    if adherence.meal_adherence >= 80:
        strengths.append("Excellent meal adherence")
    elif adherence.meal_adherence < 50:
        weaknesses.append("Meals frequently unconfirmed")
        recommendations.append("Pre-confirm meals the evening before")

    # Sleep
    if adherence.sleep_adherence >= 80:
        strengths.append("Consistent sleep habits")
    elif adherence.sleep_adherence < 50:
        weaknesses.append("Sleep targets frequently missed")
        recommendations.append("Set a wind-down alarm 30 minutes before sleep target")

    # Travel analysis
    travel_recs = [r for r in completed if r.context.travel]
    if travel_recs:
        travel_avg = sum(r.outcome.overall_completion_percentage for r in travel_recs) / len(travel_recs)  # type: ignore[union-attr]
        non_travel = [r for r in completed if not r.context.travel]
        if non_travel:
            non_travel_avg = sum(r.outcome.overall_completion_percentage for r in non_travel) / len(non_travel)  # type: ignore[union-attr]
            if travel_avg < non_travel_avg - 20:
                weaknesses.append("Low workout completion on travel days")
                recommendations.append("Schedule a 15-min walk on travel days — counts fully")

    # Streak bonus
    streak = calculate_streak(records)
    if streak.current_streak >= 7:
        strengths.append(f"{streak.current_streak}-day consistency streak")

    # Overall excellence
    if adherence.overall_adherence >= 80:
        strengths.append("Excellent overall health consistency")

    return AdherenceInsights(
        strengths=strengths or ["Keep going — every tracked day builds the habit"],
        weaknesses=weaknesses or ["No major weaknesses identified yet"],
        recommendations=recommendations or ["Maintain your current habits"],
    )


# ── Adaptive Recommendation ───────────────────────────────────────

def generate_adaptive_recommendation(
    records: List[DecisionRecord],
    adherence: AdherenceMetrics,
    current_duration: int,
    current_intensity: str,
    reference_date: Optional[date] = None,
) -> AdaptiveRecommendation:
    """
    Anti-ghosting adaptation engine.

    AT_RISK:   reduce friction (shorter workout, lower intensity)
    Thriving:  allow progressive overload (+10% after 14 high-adherence days)
    Default:   maintain recommendation unchanged
    """
    at_risk_result = detect_at_risk(records, adherence, reference_date)

    # Check for high-adherence progression eligibility
    completed_desc = sorted(
        [r for r in records if r.outcome is not None],
        key=lambda r: r.date,
        reverse=True,
    )
    high_streak = 0
    for r in completed_desc:
        if r.outcome.overall_completion_percentage >= 80:   # type: ignore[union-attr]
            high_streak += 1
        else:
            break

    if at_risk_result.at_risk:
        level = at_risk_result.adaptation_level
        if level >= 3:
            return AdaptiveRecommendation(
                adjusted_workout_duration=10,
                adjusted_intensity="low",
                reason="Minimum viable day: 10-min walk, 1 healthy meal, sleep target",
                at_risk=True,
                adaptation_level="minimum_viable",
            )
        if level >= 2:
            adj = max(15, round(current_duration * 0.25))
            return AdaptiveRecommendation(
                adjusted_workout_duration=adj,
                adjusted_intensity="low",
                reason="Reduced friction: minimal workout to protect the habit",
                at_risk=True,
                adaptation_level="minimal",
            )
        # Level 1
        adj = max(30, round(current_duration * 0.5))
        return AdaptiveRecommendation(
            adjusted_workout_duration=adj,
            adjusted_intensity=_reduce_intensity(current_intensity),
            reason="Reduced friction: low adherence detected — shorter workout scheduled",
            at_risk=True,
            adaptation_level="reduce",
        )

    if high_streak >= 14 and adherence.overall_adherence > 80:
        adj = round(current_duration * 1.1)
        return AdaptiveRecommendation(
            adjusted_workout_duration=adj,
            adjusted_intensity=_increase_intensity(current_intensity),
            reason=f"Progressive overload: {high_streak}-day high-adherence streak",
            at_risk=False,
            adaptation_level="progress",
        )

    return AdaptiveRecommendation(
        adjusted_workout_duration=current_duration,
        adjusted_intensity=current_intensity,
        reason="Adherence on track — recommendation unchanged",
        at_risk=False,
        adaptation_level="maintain",
    )


# ── AI Insight Generator ──────────────────────────────────────────

def _ai_insight(
    trends: WeeklyTrends,
    adherence: AdherenceMetrics,
    streak: StreakResult,
    at_risk: AtRiskResult,
) -> str:
    if at_risk.at_risk:
        reason = at_risk.reasons[0] if at_risk.reasons else "low adherence"
        return (
            f"Plan adapted to reduce friction: {reason}. "
            "Small consistent steps will rebuild momentum."
        )
    if trends.overall_trend > 5:
        return (
            f"Your consistency improved by {trends.overall_trend:.0f}% vs last week. "
            "Keep building on this momentum."
        )
    if trends.overall_trend < -5:
        return (
            f"Consistency dropped by {abs(trends.overall_trend):.0f}% vs last week. "
            "Your plan has been adjusted to help you get back on track."
        )
    if streak.current_streak >= 7:
        return (
            f"Outstanding — {streak.current_streak}-day streak active! "
            "You're building a real health habit."
        )
    if adherence.overall_adherence >= 80:
        return (
            "Excellent overall adherence. "
            "Stay consistent and progressive overload will unlock soon."
        )
    return "You're making steady progress. Every logged day compounds into long-term results."


# ── Dashboard ─────────────────────────────────────────────────────

def generate_dashboard(
    records: List[DecisionRecord],
    adherence: AdherenceMetrics,
    reference_date: Optional[date] = None,
) -> DashboardData:
    streaks  = calculate_streak(records)
    trends   = generate_weekly_trends(records, reference_date)
    insights = generate_adherence_insights(records, adherence)
    at_risk  = detect_at_risk(records, adherence, reference_date)
    insight  = _ai_insight(trends, adherence, streaks, at_risk)

    return DashboardData(
        adherence=adherence,
        streaks=streaks,
        trends=trends,
        insights=insights,
        at_risk=at_risk,
        ai_insight=insight,
    )
