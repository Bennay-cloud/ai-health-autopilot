"""
Personal Learning Engine.

Analyzes historical decision and outcome records to detect behavioral
patterns, generate evidence-backed insights, and produce personalization
recommendations for each individual user.

Confidence levels (based on total records with outcomes):
  low    = < 7 records
  medium = 7–29 records
  high   = 30+ records

Every LearnedPattern includes:
  insight            — human-readable finding
  evidence           — what data produced this finding
  confidence_score   — 0.0–1.0, drives language calibration
  recommended_action — concrete next step

Low-confidence patterns use cautious language ("early data suggests…").
High-confidence patterns use assertive language ("you consistently…").
"""
from __future__ import annotations

from datetime import date as _date_cls, timedelta, datetime, timezone
from typing import Dict, List, Optional
from pydantic import BaseModel

from decision_record_service import DecisionRecord
from outcome_tracking_service import OutcomeRecord


# ── Thresholds ────────────────────────────────────────────────────

LOW_THRESHOLD    = 7
MEDIUM_THRESHOLD = 30


def _confidence_level(total_with_outcomes: int) -> str:
    if total_with_outcomes < LOW_THRESHOLD:
        return "low"
    if total_with_outcomes < MEDIUM_THRESHOLD:
        return "medium"
    return "high"


def _pattern_confidence(sample_size: int) -> float:
    """Score 0.0–1.0 based on number of samples supporting this pattern."""
    return round(min(1.0, sample_size / 10.0), 2)


# ── Language calibration ──────────────────────────────────────────

def _lang_style(confidence_score: float) -> str:
    if confidence_score < 0.4:
        return "early"
    if confidence_score < 0.7:
        return "tendency"
    return "consistent"


def _prefix(style: str) -> str:
    return {
        "early":     "Early data suggests",
        "tendency":  "You tend to",
        "consistent": "You consistently",
    }[style]


# ── Output Models ─────────────────────────────────────────────────

class LearnedPattern(BaseModel):
    pattern_type: str       # duration | time_of_day | stress_response | travel_response
                            # meal_adherence | sleep_response | recovery_effectiveness
    insight: str
    evidence: str
    confidence_score: float  # 0.0–1.0
    recommended_action: str


class PersonalLearningProfile(BaseModel):
    user_id: str
    total_days_analyzed: int
    confidence_level: str     # low | medium | high
    learned_patterns: List[LearnedPattern]
    recommended_adaptations: List[str]
    generated_at: str


class LearningInsightView(BaseModel):
    """Flattened view for the frontend panel."""
    confidence_level: str
    total_days_analyzed: int
    insights: List[str]
    actions: List[str]
    has_sufficient_data: bool


# ── Duration bucket helpers ───────────────────────────────────────

_DURATION_BUCKETS = ["0-15 min", "16-30 min", "31-45 min", "46-60 min", "60+ min"]


def _duration_bucket(minutes: int) -> str:
    if minutes <= 15:  return "0-15 min"
    if minutes <= 30:  return "16-30 min"
    if minutes <= 45:  return "31-45 min"
    if minutes <= 60:  return "46-60 min"
    return "60+ min"


def _time_category(workout_time: str) -> str:
    """Maps a workout_time string (HH:MM or label) to morning/afternoon/evening."""
    wt = workout_time.lower().strip()
    if wt in ("morning", "afternoon", "evening"):
        return wt
    try:
        parts = wt.replace(".", ":").split(":")
        hour = int(parts[0])
        if 5 <= hour < 12:
            return "morning"
        if 12 <= hour < 17:
            return "afternoon"
        return "evening"
    except (ValueError, IndexError):
        return "unknown"


def _avg(vals: list) -> Optional[float]:
    return round(sum(vals) / len(vals), 1) if vals else None


def _next_date(date_str: str) -> str:
    try:
        return (_date_cls.fromisoformat(date_str) + timedelta(days=1)).isoformat()
    except (ValueError, AttributeError):
        return ""


# ── Step 3: Workout Duration Learning ────────────────────────────

def _analyze_workout_duration(
    records: List[DecisionRecord],
) -> Optional[LearnedPattern]:
    """Find the recommended-duration bucket with the highest average completion."""
    bucket_completions: Dict[str, List[float]] = {b: [] for b in _DURATION_BUCKETS}
    for r in records:
        bucket = _duration_bucket(r.decision.workout_duration_recommended)
        bucket_completions[bucket].append(r.outcome.workout_completion_percentage)  # type: ignore[union-attr]

    non_empty = {b: v for b, v in bucket_completions.items() if len(v) >= 2}
    if not non_empty:
        return None

    best = max(non_empty, key=lambda b: _avg(non_empty[b]) or 0)
    best_avg = _avg(non_empty[best]) or 0.0
    best_count = len(non_empty[best])
    confidence = _pattern_confidence(best_count)
    style = _lang_style(confidence)

    total_sessions = sum(len(v) for v in non_empty.values())

    if style == "consistent":
        insight = f"You consistently complete {best} workouts (avg {best_avg:.0f}% completion)."
    elif style == "tendency":
        insight = f"You tend to complete {best} workouts more fully (avg {best_avg:.0f}%)."
    else:
        insight = f"Early data suggests {best} workouts work best for you ({best_avg:.0f}% completion)."

    evidence = (
        f"Analyzed {total_sessions} workout sessions across "
        f"{len(non_empty)} duration categories. "
        f"{best} bucket: {best_count} sessions, avg completion {best_avg:.0f}%."
    )

    sorted_buckets = sorted(
        non_empty.items(), key=lambda x: _avg(x[1]) or 0, reverse=True
    )
    action = f"Default to {best} workout durations for maximum adherence."
    if len(sorted_buckets) >= 2:
        second_avg = _avg(sorted_buckets[1][1]) or 0.0
        if best_avg - second_avg >= 10:
            action = (
                f"Prioritize {best} workouts. Completion drops to "
                f"{second_avg:.0f}% for {sorted_buckets[1][0]} sessions."
            )

    return LearnedPattern(
        pattern_type="duration",
        insight=insight,
        evidence=evidence,
        confidence_score=confidence,
        recommended_action=action,
    )


# ── Step 4: Workout Time Learning ────────────────────────────────

def _analyze_workout_time(
    records: List[DecisionRecord],
) -> Optional[LearnedPattern]:
    """Find the time-of-day with the highest workout completion rate."""
    time_data: Dict[str, List[bool]] = {"morning": [], "afternoon": [], "evening": []}
    for r in records:
        cat = _time_category(r.decision.workout_time)
        if cat in time_data:
            time_data[cat].append(r.outcome.completed_workout)  # type: ignore[union-attr]

    non_empty = {t: v for t, v in time_data.items() if len(v) >= 2}
    if not non_empty:
        return None

    rates = {t: sum(v) / len(v) for t, v in non_empty.items()}
    best = max(rates, key=rates.get)  # type: ignore[arg-type]
    best_rate = rates[best]
    best_count = len(non_empty[best])
    confidence = _pattern_confidence(best_count)
    style = _lang_style(confidence)

    if style == "consistent":
        insight = f"You are most consistent with {best} workouts ({best_rate*100:.0f}% completion rate)."
    elif style == "tendency":
        insight = f"You tend to complete {best} workouts more reliably ({best_rate*100:.0f}% rate)."
    else:
        insight = f"Early data points to {best} as your best workout window ({best_rate*100:.0f}% completion)."

    parts = [
        f"{t}: {sum(v)/len(v)*100:.0f}% ({len(v)} sessions)"
        for t, v in non_empty.items()
    ]
    evidence = f"Completion rates by time of day — {', '.join(parts)}."
    action = f"Schedule workouts in the {best} where possible for maximum consistency."

    return LearnedPattern(
        pattern_type="time_of_day",
        insight=insight,
        evidence=evidence,
        confidence_score=confidence,
        recommended_action=action,
    )


# ── Step 5: Stress Response Learning ─────────────────────────────

def _analyze_stress_response(
    records: List[DecisionRecord],
) -> Optional[LearnedPattern]:
    """Analyze how high stress correlates with workout completion."""
    high = [
        r.outcome.workout_completion_percentage  # type: ignore[union-attr]
        for r in records if r.context.stress_level >= 7
    ]
    low = [
        r.outcome.workout_completion_percentage  # type: ignore[union-attr]
        for r in records if r.context.stress_level < 7
    ]
    if len(high) < 2 or len(low) < 2:
        return None

    avg_high = _avg(high) or 0.0
    avg_low  = _avg(low)  or 0.0
    delta    = avg_low - avg_high

    if abs(delta) < 5:
        return None  # Not a meaningful difference

    confidence = _pattern_confidence(min(len(high), len(low)))
    style = _lang_style(confidence)
    p = _prefix(style)

    if delta > 0:
        if style == "consistent":
            insight = (
                f"High-stress days consistently reduce your workout completion "
                f"by {delta:.0f}% ({avg_high:.0f}% vs {avg_low:.0f}% on lower-stress days)."
            )
        else:
            insight = (
                f"{p} complete fewer workouts on high-stress days "
                f"(−{delta:.0f}% completion vs lower-stress days)."
            )
        action = (
            "On high-stress days (stress ≥7), switch to shorter recovery-style "
            "workouts to protect your adherence streak."
        )
    else:
        if style == "consistent":
            insight = (
                f"Your workout completion holds strong even on high-stress days "
                f"({avg_high:.0f}% vs {avg_low:.0f}% on lower-stress days)."
            )
        else:
            insight = f"{p} show resilience on high-stress days ({avg_high:.0f}% workout completion)."
        action = "Maintain current approach — your consistency under stress is a key strength."

    evidence = (
        f"High-stress days (stress ≥7): {len(high)} sessions, avg completion {avg_high:.0f}%. "
        f"Lower-stress days: {len(low)} sessions, avg completion {avg_low:.0f}%."
    )
    return LearnedPattern(
        pattern_type="stress_response",
        insight=insight,
        evidence=evidence,
        confidence_score=confidence,
        recommended_action=action,
    )


# ── Step 6: Travel Response Learning ─────────────────────────────

def _analyze_travel_response(
    records: List[DecisionRecord],
) -> Optional[LearnedPattern]:
    """Compare workout and meal adherence on travel vs non-travel days."""
    travel     = [r for r in records if r.context.travel]
    non_travel = [r for r in records if not r.context.travel]
    if len(travel) < 2 or len(non_travel) < 2:
        return None

    def _wo_rate(recs: List[DecisionRecord]) -> float:
        vals = [r.outcome.workout_completion_percentage for r in recs]  # type: ignore[union-attr]
        return round(sum(vals) / len(vals), 1)

    def _meal_rate(recs: List[DecisionRecord]) -> float:
        scores = [
            100.0 if (r.outcome.meal_ordered and r.outcome.meal_confirmed)  # type: ignore[union-attr]
            else 50.0 if r.outcome.meal_ordered  # type: ignore[union-attr]
            else 0.0
            for r in recs
        ]
        return round(sum(scores) / len(scores), 1)

    wo_t   = _wo_rate(travel);    wo_nt  = _wo_rate(non_travel)
    ml_t   = _meal_rate(travel);  ml_nt  = _meal_rate(non_travel)
    wo_drop   = wo_nt  - wo_t
    meal_drop = ml_nt  - ml_t

    max_drop = max(wo_drop, meal_drop)
    if max_drop < 5:
        return None

    worst_area = "workout" if wo_drop >= meal_drop else "meal"
    worst_drop = wo_drop   if wo_drop >= meal_drop else meal_drop

    confidence = _pattern_confidence(len(travel))
    style = _lang_style(confidence)
    p = _prefix(style)

    if style == "consistent":
        insight = (
            f"Travel days consistently reduce your {worst_area} adherence by {worst_drop:.0f}%."
        )
    else:
        insight = (
            f"{p} experience a {worst_drop:.0f}% drop in {worst_area} adherence on travel days."
        )

    evidence = (
        f"Travel days ({len(travel)}): workout {wo_t:.0f}%, meals {ml_t:.0f}%. "
        f"Non-travel days ({len(non_travel)}): workout {wo_nt:.0f}%, meals {ml_nt:.0f}%."
    )
    action = (
        "On travel days, pre-select a 20–30 min bodyweight workout and pre-order meals "
        "to your travel location to protect adherence."
    )
    return LearnedPattern(
        pattern_type="travel_response",
        insight=insight,
        evidence=evidence,
        confidence_score=confidence,
        recommended_action=action,
    )


# ── Step 7: Meal Adherence Learning ──────────────────────────────

def _analyze_meal_adherence(
    records: List[DecisionRecord],
) -> Optional[LearnedPattern]:
    """Find delivery location with highest meal adherence rate."""
    location_data: Dict[str, List[float]] = {}
    for r in records:
        loc = r.decision.delivery_location
        score = (
            100.0 if (r.outcome.meal_ordered and r.outcome.meal_confirmed)  # type: ignore[union-attr]
            else 50.0 if r.outcome.meal_ordered  # type: ignore[union-attr]
            else 0.0
        )
        location_data.setdefault(loc, []).append(score)

    non_empty = {loc: v for loc, v in location_data.items() if len(v) >= 2}
    if not non_empty:
        return None

    best_loc = max(non_empty, key=lambda l: _avg(non_empty[l]) or 0)
    best_avg = _avg(non_empty[best_loc]) or 0.0
    best_count = len(non_empty[best_loc])
    confidence = _pattern_confidence(best_count)
    style = _lang_style(confidence)

    if style == "consistent":
        insight = f"You adhere best to {best_loc} meal deliveries ({best_avg:.0f}% adherence)."
    elif style == "tendency":
        insight = f"Your meal adherence tends to be highest for {best_loc} deliveries ({best_avg:.0f}%)."
    else:
        insight = f"Early data suggests {best_loc} deliveries work best for you ({best_avg:.0f}% adherence)."

    parts = [f"{loc}: {_avg(v):.0f}% ({len(v)} days)" for loc, v in non_empty.items()]
    evidence = f"Meal adherence by delivery location — {', '.join(parts)}."
    action = f"Prioritize {best_loc} delivery — it produces your highest meal adherence."

    return LearnedPattern(
        pattern_type="meal_adherence",
        insight=insight,
        evidence=evidence,
        confidence_score=confidence,
        recommended_action=action,
    )


# ── Step 8: Sleep Response Learning ──────────────────────────────

def _analyze_sleep_response(
    records: List[DecisionRecord],
    outcome_map: Dict[str, OutcomeRecord],
) -> Optional[LearnedPattern]:
    """Correlate sleep hours with next-day energy."""
    THRESHOLD = 6.0
    under: List[float] = []
    over:  List[float] = []

    for r in records:
        next_out = outcome_map.get(_next_date(r.date))
        if not (next_out and next_out.daily_outcomes):
            continue
        energy = next_out.daily_outcomes.energy
        if r.context.sleep_hours < THRESHOLD:
            under.append(energy)
        else:
            over.append(energy)

    if len(under) < 2 or len(over) < 2:
        return None

    avg_under = _avg(under) or 0.0
    avg_over  = _avg(over)  or 0.0
    delta = avg_over - avg_under

    if abs(delta) < 0.5:
        return None

    confidence = _pattern_confidence(min(len(under), len(over)))
    style = _lang_style(confidence)

    if delta > 0:
        if style == "consistent":
            insight = (
                f"When your sleep falls below 6h, your next-day energy consistently "
                f"drops by {delta:.1f} points (avg {avg_under:.1f} vs {avg_over:.1f}/10)."
            )
        else:
            insight = (
                f"Sleep below 6h appears to reduce your next-day energy "
                f"by {delta:.1f} points on average."
            )
        action = (
            "Protect 6+ hours of sleep on nights before demanding workouts "
            "or high-stakes work days."
        )
    else:
        insight = (
            "Your next-day energy remains stable across different sleep durations "
            "(based on current data)."
        )
        action = "Continue monitoring — sleep-energy patterns may emerge with more data."

    evidence = (
        f"Sleep <6h ({len(under)} nights): next-day energy avg {avg_under:.1f}/10. "
        f"Sleep ≥6h ({len(over)} nights): next-day energy avg {avg_over:.1f}/10."
    )
    return LearnedPattern(
        pattern_type="sleep_response",
        insight=insight,
        evidence=evidence,
        confidence_score=confidence,
        recommended_action=action,
    )


# ── Step 9: Recovery Effectiveness Learning ───────────────────────

def _analyze_recovery_effectiveness(
    records: List[DecisionRecord],
    outcome_map: Dict[str, OutcomeRecord],
) -> Optional[LearnedPattern]:
    """Measure whether recovery days reduce next-day stress."""
    deltas: List[float] = []

    for r in records:
        if r.decision.day_type != "recovery":
            continue
        today_out = outcome_map.get(r.date)
        next_out  = outcome_map.get(_next_date(r.date))
        if not (
            today_out and today_out.daily_outcomes and
            next_out  and next_out.daily_outcomes
        ):
            continue
        deltas.append(
            next_out.daily_outcomes.stress - today_out.daily_outcomes.stress
        )

    if len(deltas) < 2:
        return None

    avg_delta = _avg(deltas) or 0.0
    improved = sum(1 for d in deltas if d < 0)
    rate = improved / len(deltas)
    confidence = _pattern_confidence(len(deltas))
    style = _lang_style(confidence)

    if avg_delta < 0:
        if style == "consistent":
            insight = (
                f"Recovery days consistently reduce your next-day stress "
                f"({rate*100:.0f}% of recovery days show improvement)."
            )
        else:
            insight = (
                f"Recovery days appear to reduce your next-day stress "
                f"({rate*100:.0f}% of cases show improvement)."
            )
        action = "Trust the recovery protocol — the data confirms it is reducing your stress levels."
    else:
        insight = (
            f"Recovery days show mixed results on next-day stress "
            f"(improvement in {rate*100:.0f}% of cases)."
        )
        action = (
            "Recovery day quality may vary — focus on sleep and nutrition "
            "on recovery days to improve results."
        )

    evidence = (
        f"Analyzed {len(deltas)} recovery days. "
        f"Average next-day stress change: {avg_delta:+.1f} points "
        f"(negative = improvement). "
        f"{improved}/{len(deltas)} days showed stress reduction."
    )
    return LearnedPattern(
        pattern_type="recovery_effectiveness",
        insight=insight,
        evidence=evidence,
        confidence_score=confidence,
        recommended_action=action,
    )


# ── Recommendations builder ───────────────────────────────────────

def _build_adaptations(patterns: List[LearnedPattern]) -> List[str]:
    """Extract recommended actions from medium+ confidence patterns."""
    return [p.recommended_action for p in patterns if p.confidence_score >= 0.4][:5]


# ── Main entry point ──────────────────────────────────────────────

def analyze_learning_profile(
    records: List[DecisionRecord],
    outcome_records: List[OutcomeRecord],
    user_id: str,
) -> PersonalLearningProfile:
    """
    Analyzes all historical records for a user and returns a PersonalLearningProfile.

    - records_with_outcomes are used for completion-based pattern analysis.
    - outcome_records are used for next-day cross-referencing (sleep, recovery).
    - Individual analyzer failures are swallowed — the profile always returns.
    """
    records_with_outcomes = [r for r in records if r.outcome is not None]
    total = len(records_with_outcomes)
    confidence_level = _confidence_level(total)

    outcome_map: Dict[str, OutcomeRecord] = {r.date: r for r in outcome_records}

    patterns: List[LearnedPattern] = []

    analyzers = [
        lambda: _analyze_workout_duration(records_with_outcomes),
        lambda: _analyze_workout_time(records_with_outcomes),
        lambda: _analyze_stress_response(records_with_outcomes),
        lambda: _analyze_travel_response(records_with_outcomes),
        lambda: _analyze_meal_adherence(records_with_outcomes),
        lambda: _analyze_sleep_response(records_with_outcomes, outcome_map),
        lambda: _analyze_recovery_effectiveness(records_with_outcomes, outcome_map),
    ]

    for analyzer in analyzers:
        try:
            result = analyzer()
            if result is not None:
                patterns.append(result)
        except Exception:
            pass  # Non-critical; individual pattern failures do not block the profile

    return PersonalLearningProfile(
        user_id=user_id,
        total_days_analyzed=total,
        confidence_level=confidence_level,
        learned_patterns=patterns,
        recommended_adaptations=_build_adaptations(patterns),
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


# ── Convenience: insights-only view ──────────────────────────────

def get_learning_insights_view(profile: PersonalLearningProfile) -> LearningInsightView:
    return LearningInsightView(
        confidence_level=profile.confidence_level,
        total_days_analyzed=profile.total_days_analyzed,
        insights=[p.insight for p in profile.learned_patterns],
        actions=[
            p.recommended_action
            for p in profile.learned_patterns
            if p.confidence_score >= 0.4
        ],
        has_sufficient_data=profile.total_days_analyzed >= LOW_THRESHOLD,
    )


# ── Personalization note for DailyDecisionEngine ─────────────────

def build_personalization_note(
    profile: PersonalLearningProfile,
    recommended_duration: int,
) -> Optional[str]:
    """
    Returns a personalization note when a high-confidence duration pattern
    suggests a different duration than what was recommended.
    Returns None if no actionable insight exists.
    """
    if profile.confidence_level == "low":
        return None

    duration_pattern = next(
        (p for p in profile.learned_patterns if p.pattern_type == "duration"),
        None,
    )
    if duration_pattern is None or duration_pattern.confidence_score < 0.5:
        return None

    recommended_bucket = _duration_bucket(recommended_duration)

    # Extract best bucket from insight text — look for "X-Y min" in the insight
    import re
    match = re.search(r"(\d+-\d+ min|60\+ min|0-\d+ min)", duration_pattern.insight)
    if not match:
        return None
    best_bucket = match.group(1)

    if best_bucket == recommended_bucket:
        return None  # Recommendation already matches learned preference

    return (
        f"Personalized based on your history: "
        f"you complete {best_bucket} workouts more consistently "
        f"({duration_pattern.confidence_score*100:.0f}% confidence)."
    )
