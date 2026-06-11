from datetime import date
from typing import Optional
from pydantic import BaseModel


class CycleProfile(BaseModel):
    gender: str = "other"                           # male | female | other
    cycle_tracking_enabled: bool = False
    last_period_start_date: Optional[date] = None
    average_cycle_length: int = 28                  # days
    average_period_length: int = 5                  # days


class CyclePhaseResult(BaseModel):
    phase: str                                      # menstruation | follicular | ovulation | luteal | unknown
    cycle_day: Optional[int] = None
    explanation: str


def detect_cycle_phase(
    profile: CycleProfile,
    today: Optional[date] = None,
) -> CyclePhaseResult:
    """
    Returns the current cycle phase based on the user's cycle profile.

    Phase boundaries:
    - menstruation : cycle_day 1 → average_period_length
    - follicular   : after period → day 13
    - ovulation    : day 14 → 16
    - luteal       : day 17 → end of cycle
    - unknown      : tracking disabled or missing data
    """
    if today is None:
        today = date.today()

    if not profile.cycle_tracking_enabled:
        return CyclePhaseResult(
            phase="unknown",
            cycle_day=None,
            explanation="Cycle tracking is disabled.",
        )

    if profile.last_period_start_date is None:
        return CyclePhaseResult(
            phase="unknown",
            cycle_day=None,
            explanation="No period start date provided.",
        )

    days_since = (today - profile.last_period_start_date).days
    cycle_day = (days_since % profile.average_cycle_length) + 1

    if cycle_day <= profile.average_period_length:
        return CyclePhaseResult(
            phase="menstruation",
            cycle_day=cycle_day,
            explanation=f"Day {cycle_day} of your cycle — menstruation phase.",
        )
    if cycle_day <= 13:
        return CyclePhaseResult(
            phase="follicular",
            cycle_day=cycle_day,
            explanation=f"Day {cycle_day} of your cycle — follicular phase.",
        )
    if cycle_day <= 16:
        return CyclePhaseResult(
            phase="ovulation",
            cycle_day=cycle_day,
            explanation=f"Day {cycle_day} of your cycle — ovulation phase.",
        )
    return CyclePhaseResult(
        phase="luteal",
        cycle_day=cycle_day,
        explanation=f"Day {cycle_day} of your cycle — luteal phase.",
    )
