"""
Health Priority Engine.

Combines OccupationProfile + PainInput (with severity) + goal + context
to generate an ordered list of human-centric health priorities.

Severity weighting:
  - Pain severity >= 7  → urgency "high",   base score 90 + severity
  - Pain severity 4–6   → urgency "medium",  base score 60 + severity
  - Pain severity 1–3   → urgency "medium",  base score 40 + severity
  - Occupation risk     → urgency "medium",  base score 50
  - Elevated stress     → urgency "high"     (bumped if stress >= 7)
  - Goal                → urgency "supporting", base score 30
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel

from occupation_engine import OccupationProfile
from pain_engine import PainInput, get_pain_profile


class HumanCentricPriority(BaseModel):
    rank: int
    human_label: str
    technical_label: str
    reason: str
    urgency: str    # "high" | "medium" | "supporting"


# ── Technical → Human label mapping ──────────────────────────────────────────

TECHNICAL_TO_HUMAN: Dict[str, str] = {
    "Scapular Stability":           "Reduce Neck & Shoulder Tension",
    "Posture Restoration":          "Improve Sitting Posture",
    "Lumbar Stability":             "Relieve Lower-Back Pain",
    "Knee Stability":               "Protect Your Knees",
    "Hip Mobility":                 "Improve Hip Mobility",
    "Wrist and Forearm Health":     "Reduce Wrist Strain",
    "Shoulder Stability":           "Reduce Shoulder Discomfort",
    "Ankle Stability":              "Support Ankle Stability",
    "Metabolic Health":             "Increase Daily Energy",
    "Body Composition":             "Support Fat Loss",
    "Stress Resilience":            "Manage Work Stress Better",
    "Work Capacity":                "Maintain Energy Through Your Day",
    "Recovery Optimization":        "Recover Faster Between Shifts",
    "Posterior Chain Strength":     "Lift Safely at Work",
    "Upper Back Strength":          "Improve Upper-Back Strength",
    "Sleep Quality":                "Improve Sleep Quality",
    "Thoracic Mobility":            "Move Freely Throughout the Day",
}

# Pain area → technical priority label
PAIN_TO_TECHNICAL: Dict[str, str] = {
    "neck":       "Scapular Stability",
    "shoulder":   "Shoulder Stability",
    "upper_back": "Posture Restoration",
    "lower_back": "Lumbar Stability",
    "wrist":      "Wrist and Forearm Health",
    "hip":        "Hip Mobility",
    "knee":       "Knee Stability",
    "ankle":      "Ankle Stability",
}

# Goal keyword → (primary technical, secondary technical)
GOAL_TO_TECHNICAL: Dict[str, Tuple[str, str]] = {
    "fettabbau":    ("Body Composition",  "Metabolic Health"),
    "muskelaufbau": ("Body Composition",  "Work Capacity"),
    "gesund":       ("Metabolic Health",  "Stress Resilience"),
}


def _severity_to_urgency(severity: int) -> Tuple[str, int]:
    """Returns (urgency_label, base_score) for a given pain severity."""
    if severity >= 7:
        return "high", 90 + severity
    if severity >= 4:
        return "medium", 60 + severity
    return "medium", 40 + severity


def generate_health_priorities(
    occupation_profile: Optional[OccupationProfile],
    pain_inputs: List[PainInput],
    goal: str,
    stress_level: int,
    recovery_score: int,
) -> List[HumanCentricPriority]:
    """
    Returns up to 5 ordered human-centric health priorities.

    Ordering logic:
      1. Active pain areas — sorted by severity descending
      2. Occupation-specific risks not already covered
      3. Stress resilience boost if stress >= 7
      4. Goal-aligned priorities last
    """
    priorities: List[dict] = []
    used_technical: set = set()

    # ── 1. Pain-driven priorities ─────────────────────────────────────────────
    sorted_pain = sorted(pain_inputs, key=lambda p: p.severity, reverse=True)
    for pain in sorted_pain:
        technical = PAIN_TO_TECHNICAL.get(pain.area)
        if not technical or technical in used_technical:
            continue

        pain_profile = get_pain_profile(pain.area)
        human = (
            pain_profile.human_priority_label
            if pain_profile
            else TECHNICAL_TO_HUMAN.get(technical, technical)
        )
        urgency, score = _severity_to_urgency(pain.severity)

        occ_context = ""
        if occupation_profile and pain_profile:
            for contrib in pain_profile.occupational_contributors[:1]:
                occ_context = f" — {contrib}"

        reason = (
            f"{pain_profile.display_name if pain_profile else pain.area.title()} pain "
            f"(severity {pain.severity}/10){occ_context}"
        )

        priorities.append({
            "technical": technical,
            "human": human,
            "reason": reason,
            "urgency": urgency,
            "score": score,
        })
        used_technical.add(technical)

    # ── 2. Occupation-driven priorities ──────────────────────────────────────
    if occupation_profile:
        for technical in occupation_profile.health_priorities:
            if technical in used_technical:
                continue

            human = TECHNICAL_TO_HUMAN.get(technical, technical)
            urgency = "medium"
            score = 50

            # Stress resilience escalation
            if technical == "Stress Resilience" and stress_level >= 7:
                urgency = "high"
                score = 75
                reason = (
                    f"Stress level {stress_level}/10 — high work stress detected "
                    f"for {occupation_profile.profession_display}"
                )
            else:
                reason = (
                    f"Common occupational risk pattern for "
                    f"{occupation_profile.profession_display}"
                )

            priorities.append({
                "technical": technical,
                "human": human,
                "reason": reason,
                "urgency": urgency,
                "score": score,
            })
            used_technical.add(technical)

    # ── 3. Goal-driven priorities ─────────────────────────────────────────────
    goal_lower = goal.lower()
    for key, (primary_tech, secondary_tech) in GOAL_TO_TECHNICAL.items():
        if key in goal_lower:
            for technical in [primary_tech, secondary_tech]:
                if technical not in used_technical:
                    human = TECHNICAL_TO_HUMAN.get(technical, technical)
                    priorities.append({
                        "technical": technical,
                        "human": human,
                        "reason": f"Aligned with your stated goal: {goal}",
                        "urgency": "supporting",
                        "score": 30,
                    })
                    used_technical.add(technical)
            break

    # Sort by score descending, take top 5
    priorities.sort(key=lambda x: x["score"], reverse=True)
    priorities = priorities[:5]

    return [
        HumanCentricPriority(
            rank=i + 1,
            human_label=p["human"],
            technical_label=p["technical"],
            reason=p["reason"],
            urgency=p["urgency"],
        )
        for i, p in enumerate(priorities)
    ]
