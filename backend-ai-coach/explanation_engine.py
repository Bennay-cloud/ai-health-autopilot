"""
Explanation Engine.

Builds two outputs for the AI Occupational Health Advisor:

1. WhyThisMatters  — structured 6-section object (deterministic, no LLM)
2. HealthAdvisorMessage — expert narrative paragraph (LLM-generated)

Full pipeline:
  Work Profile
  → Risks Detected
  → Pain Areas
  → Today's Priority
  → Today's Intervention
  → Physiological Adaptations
  → Work Performance Benefits
  → Long-Term Health Benefits
  → What Happens If Ignored

The "What Happens If Ignored" section is educational and non-medical.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

from health_priority_engine import HumanCentricPriority
from occupation_engine import OccupationProfile
from pain_engine import PainInput, get_pain_profile
from training_knowledge import TrainingTypeProfile

load_dotenv()


# ── Output Models ─────────────────────────────────────────────────────────────

class WorkPerformanceBenefits(BaseModel):
    profession_display: str
    benefits: List[str]


class IgnoredRiskSection(BaseModel):
    short_term: List[str]
    long_term: List[str]
    educational_note: str


class WhyThisMatters(BaseModel):
    work_profile_summary: str
    risks_detected: List[str]
    todays_priority: str
    todays_priority_reason: str
    physiological_adaptations: List[str]
    work_performance_benefits: WorkPerformanceBenefits
    long_term_benefits: List[str]
    what_if_ignored: IgnoredRiskSection


class HealthAdvisorMessage(BaseModel):
    message: str


# ── What-If-Ignored Knowledge Base ───────────────────────────────────────────

_IGNORED_BY_TECHNICAL: dict = {
    "Scapular Stability": {
        "short_term": [
            "Neck tension may worsen during long work sessions",
            "Upper back fatigue tends to build gradually without targeted training",
        ],
        "long_term": [
            "Chronic postural dysfunction is common when scapular stability is neglected",
            "Cervical spine load increases over time with unaddressed postural imbalances",
        ],
    },
    "Posture Restoration": {
        "short_term": [
            "Sitting discomfort may increase without structural correction",
            "Neck and shoulder tension tends to accumulate over time",
        ],
        "long_term": [
            "Forward head posture can become structurally fixed over years without correction",
            "Reduced thoracic mobility limits movement quality and increases spinal load",
        ],
    },
    "Lumbar Stability": {
        "short_term": [
            "Lower back discomfort often increases with prolonged sitting or standing",
            "Fatigue in the lower back may arrive earlier in the day",
        ],
        "long_term": [
            "Weak glutes and core can lead to compensatory movement patterns that increase disc load",
            "Occupational lower back conditions are one of the most preventable career-ending injuries",
        ],
    },
    "Knee Stability": {
        "short_term": [
            "Knee discomfort during prolonged standing or movement may worsen",
            "End-of-shift fatigue in the knees may increase without supporting strength",
        ],
        "long_term": [
            "Accumulated knee stress without muscular support can affect joint health over time",
            "Weak hip stabilisers and quads increase the rate of joint wear",
        ],
    },
    "Shoulder Stability": {
        "short_term": [
            "Shoulder discomfort during reaching or lifting may increase",
        ],
        "long_term": [
            "Shoulder imbalances can develop into impingement patterns over years",
            "Reduced shoulder function can limit occupational performance and comfort",
        ],
    },
    "Hip Mobility": {
        "short_term": [
            "Hip stiffness after sitting or driving may worsen without mobilisation",
        ],
        "long_term": [
            "Hip flexor tightness contributes to lower back strain over time",
            "Reduced hip mobility affects movement quality and accelerates compensation patterns",
        ],
    },
    "Wrist and Forearm Health": {
        "short_term": [
            "Wrist discomfort during keyboard and mouse work may increase",
        ],
        "long_term": [
            "Repetitive strain patterns can become chronic without forearm strength balance",
            "Grip and wrist function can diminish over a career of unaddressed repetitive strain",
        ],
    },
    "Ankle Stability": {
        "short_term": [
            "Ankle fatigue during prolonged standing may worsen",
        ],
        "long_term": [
            "Reduced ankle mobility affects movement mechanics up the chain over time",
        ],
    },
    "Metabolic Health": {
        "short_term": [
            "Afternoon energy dips may become more frequent",
            "Concentration and cognitive output may decline through the day",
        ],
        "long_term": [
            "Sedentary patterns without aerobic stimulus are associated with progressive metabolic decline",
            "Cardiovascular fitness decreases steadily without regular aerobic training",
        ],
    },
    "Stress Resilience": {
        "short_term": [
            "Work stress may feel harder to manage without physical stress outlets",
            "Sleep quality is often impacted when stress is unmanaged",
        ],
        "long_term": [
            "Chronic unmanaged stress is associated with sustained negative health outcomes",
            "Physical and cognitive performance at work are closely linked to long-term stress resilience",
        ],
    },
    "Body Composition": {
        "short_term": [
            "Progress toward body composition goals slows without structured training",
        ],
        "long_term": [
            "Metabolic health and cardiovascular risk are influenced by long-term inactivity",
        ],
    },
    "Work Capacity": {
        "short_term": [
            "End-of-shift fatigue may increase without targeted capacity training",
        ],
        "long_term": [
            "Occupational capacity and career longevity are supported by sustained physical training",
        ],
    },
    "Recovery Optimization": {
        "short_term": [
            "Recovery between demanding shifts may slow without active recovery protocols",
        ],
        "long_term": [
            "Cumulative fatigue without recovery work increases injury risk over time",
        ],
    },
}

_EDUCATIONAL_NOTE = (
    "These are general educational patterns commonly observed in occupationally demanding "
    "or sedentary lifestyles. They are not medical predictions. "
    "Please consult a qualified healthcare professional for personal medical advice."
)


# ── Builder functions ─────────────────────────────────────────────────────────

def _build_ignored_section(
    priorities: List[HumanCentricPriority],
) -> IgnoredRiskSection:
    short_term: List[str] = []
    long_term: List[str] = []
    for p in priorities[:2]:
        data = _IGNORED_BY_TECHNICAL.get(p.technical_label, {})
        for item in data.get("short_term", [])[:2]:
            if item not in short_term:
                short_term.append(item)
        for item in data.get("long_term", [])[:2]:
            if item not in long_term:
                long_term.append(item)
    return IgnoredRiskSection(
        short_term=short_term[:4],
        long_term=long_term[:4],
        educational_note=_EDUCATIONAL_NOTE,
    )


def _build_work_performance_benefits(
    occupation_profile: OccupationProfile,
    training_profile: Optional[TrainingTypeProfile],
) -> WorkPerformanceBenefits:
    benefits: List[str] = []

    # First from training type (specific to today's training)
    if training_profile:
        for b in training_profile.work_performance_benefits[:2]:
            benefits.append(b)

    # Then from occupation profile (job-specific)
    for b in occupation_profile.work_performance_benefits:
        if b not in benefits:
            benefits.append(b)
        if len(benefits) >= 4:
            break

    return WorkPerformanceBenefits(
        profession_display=occupation_profile.profession_display,
        benefits=benefits[:4],
    )


def build_why_this_matters(
    occupation_profile: OccupationProfile,
    pain_inputs: List[PainInput],
    priorities: List[HumanCentricPriority],
    training_profile: Optional[TrainingTypeProfile],
) -> WhyThisMatters:
    # ── Work profile summary ──────────────────────────────────────────────────
    demands = occupation_profile.work_demands[:3]
    demands_str = ", ".join(demands[:-1]) + f", and {demands[-1]}" if len(demands) > 1 else demands[0]
    work_profile_summary = (
        f"As a {occupation_profile.profession_display}, your work involves {demands_str}. "
        f"These demands create specific physical patterns that affect your body over time."
    )

    # ── Risks detected ────────────────────────────────────────────────────────
    risks: List[str] = list(occupation_profile.health_risks[:3])
    for pain in pain_inputs:
        pain_profile = get_pain_profile(pain.area)
        if pain_profile:
            for contrib in pain_profile.occupational_contributors[:1]:
                if contrib not in risks:
                    risks.append(contrib)
    risks = risks[:6]

    # ── Today's priority ──────────────────────────────────────────────────────
    top = priorities[0] if priorities else None
    todays_priority = top.human_label if top else "General Health"
    todays_priority_reason = top.reason if top else ""

    # ── Physiological adaptations ─────────────────────────────────────────────
    physio: List[str] = []
    if training_profile:
        physio = training_profile.physiological_adaptations[:4]

    # ── Work performance benefits ─────────────────────────────────────────────
    work_benefits = _build_work_performance_benefits(occupation_profile, training_profile)

    # ── Long-term benefits ────────────────────────────────────────────────────
    long_term: List[str] = []
    if training_profile:
        long_term = training_profile.long_term_health_benefits[:4]

    # ── What if ignored ───────────────────────────────────────────────────────
    ignored = _build_ignored_section(priorities)

    return WhyThisMatters(
        work_profile_summary=work_profile_summary,
        risks_detected=risks,
        todays_priority=todays_priority,
        todays_priority_reason=todays_priority_reason,
        physiological_adaptations=physio,
        work_performance_benefits=work_benefits,
        long_term_benefits=long_term,
        what_if_ignored=ignored,
    )


def generate_health_advisor_message(
    occupation_profile: OccupationProfile,
    pain_inputs: List[PainInput],
    priorities: List[HumanCentricPriority],
    training_profile: Optional[TrainingTypeProfile],
    goal: str,
    day_type: str,
    stress_level: int,
    recovery_score: int,
) -> HealthAdvisorMessage:
    """
    Generates a personalised advisor message via the LLM.
    Falls back to a deterministic message if the LLM call fails.
    """
    pain_summary = (
        ", ".join(f"{p.area.replace('_', ' ')} (severity {p.severity}/10)" for p in pain_inputs)
        if pain_inputs
        else "no reported pain areas"
    )
    top_priorities_text = "\n".join(
        f"  - {p.human_label} ({p.urgency} urgency)" for p in priorities[:3]
    )
    training_name = training_profile.display_name if training_profile else "today's session"

    prompt = f"""You are an expert Occupational Health Advisor and Sports Scientist writing a personalised health message.

User profile:
- Profession: {occupation_profile.profession_display}
- Reported pain areas: {pain_summary}
- Goal: {goal}
- Day type: {day_type}
- Stress level: {stress_level}/10
- Recovery score: {recovery_score}/100
- Today's training: {training_name}

Identified health priorities:
{top_priorities_text}

Key occupational risks for this profession:
{chr(10).join(f"  - {r}" for r in occupation_profile.health_risks[:4])}

Write a personalised health advisor message. Requirements:
- 3–4 paragraphs, maximum 200 words
- Open by naming the profession and its specific physical demands on the body
- Connect the pain areas (if any) directly to the occupational demands
- Explain what today's training targets and precisely why it matters for this person
- Close with the long-term perspective — what this builds toward
- Tone: expert, warm, direct — like a trusted health advisor who knows your case
- Every sentence must be specific to this person's profession and situation
- No generic phrases like "great job", "stay motivated", or "keep it up"
- No medical advice or diagnoses
- Write only the message text — no labels, headers, or formatting"""

    try:
        client = OpenAI(
            api_key=os.getenv("GROQ_API_KEY"),
            base_url="https://api.groq.com/openai/v1",
        )
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=320,
        )
        message_text = response.choices[0].message.content or ""
        return HealthAdvisorMessage(message=message_text.strip())
    except Exception as e:
        print(f"[explanation_engine] LLM call failed, using fallback: {e}")
        return _fallback_advisor_message(occupation_profile, pain_inputs, priorities, training_name)


def _fallback_advisor_message(
    occupation_profile: OccupationProfile,
    pain_inputs: List[PainInput],
    priorities: List[HumanCentricPriority],
    training_name: str,
) -> HealthAdvisorMessage:
    """Deterministic fallback when LLM is unavailable."""
    pain_text = (
        f" Combined with the {', '.join(p.area.replace('_', ' ') for p in pain_inputs[:2])} "
        "pain you've reported, this requires direct attention."
        if pain_inputs else ""
    )
    top = priorities[0].human_label if priorities else "your health priorities"

    message = (
        f"As a {occupation_profile.profession_display}, your work creates specific physical demands "
        f"that accumulate over time. "
        f"The key risks associated with your profession include "
        f"{', '.join(occupation_profile.health_risks[:3])}.{pain_text}\n\n"
        f"Today's {training_name} directly addresses your top priority: {top}. "
        f"This intervention is designed around your occupational profile, not a generic template.\n\n"
        f"Consistency with this approach builds the structural resilience your body needs "
        f"to perform at work and stay healthy for the long term."
    )
    return HealthAdvisorMessage(message=message)
