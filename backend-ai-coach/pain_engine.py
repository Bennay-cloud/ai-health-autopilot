"""
Pain Engine — maps pain areas to PainAreaProfile.

PainInput supports a severity field (1–10) that downstream engines
use to weight health priority ranking and risk score computation.

All contributors are occupational / training-relevant only.
This module contains NO medical advice or diagnoses.
"""
from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Dict, List, Optional


class PainInput(BaseModel):
    area: str
    severity: int = Field(..., ge=1, le=10, description="Pain severity: 1 = mild, 10 = severe")


class PainAreaProfile(BaseModel):
    area: str
    display_name: str
    occupational_contributors: List[str]   # training-relevant factors only
    relief_training_focuses: List[str]
    aggravating_factors: List[str]
    human_priority_label: str


PAIN_DATABASE: Dict[str, PainAreaProfile] = {
    "neck": PainAreaProfile(
        area="neck",
        display_name="Neck",
        occupational_contributors=[
            "sustained forward head posture from screen work",
            "weak upper back and scapular stabilizer muscles",
            "poor monitor or device positioning",
            "high work stress increasing upper trapezius tension",
        ],
        relief_training_focuses=[
            "scapular stabilizers (rhomboids, rear deltoids, mid-trapezius)",
            "deep neck flexor activation",
            "thoracic extension mobility",
            "upper trapezius release through targeted movement",
        ],
        aggravating_factors=[
            "prolonged screen use without postural breaks",
            "forward head posture",
            "high stress levels",
        ],
        human_priority_label="Reduce Neck Tension",
    ),
    "shoulder": PainAreaProfile(
        area="shoulder",
        display_name="Shoulder",
        occupational_contributors=[
            "repetitive overhead reaching or lifting",
            "weak rotator cuff from sedentary work",
            "poor scapular control",
            "sustained internal rotation from keyboard and mouse use",
        ],
        relief_training_focuses=[
            "rotator cuff strengthening",
            "scapular stability and retraction",
            "shoulder external rotation",
            "thoracic extension mobility",
        ],
        aggravating_factors=[
            "overhead repetitive tasks",
            "sustained internal rotation",
            "weak upper back",
        ],
        human_priority_label="Reduce Shoulder Discomfort",
    ),
    "upper_back": PainAreaProfile(
        area="upper_back",
        display_name="Upper Back",
        occupational_contributors=[
            "rounded shoulder posture from computer and desk work",
            "weak rhomboids and mid-trapezius",
            "thoracic immobility from prolonged sitting",
            "sustained thoracic flexion posture",
        ],
        relief_training_focuses=[
            "pull training (rows, face pulls, band pull-aparts)",
            "thoracic extension and rotation",
            "scapular retraction",
            "upper back muscular endurance",
        ],
        aggravating_factors=[
            "prolonged sitting without movement breaks",
            "rounded shoulder posture",
            "inadequate upper back strength",
        ],
        human_priority_label="Improve Upper-Back Strength",
    ),
    "lower_back": PainAreaProfile(
        area="lower_back",
        display_name="Lower Back",
        occupational_contributors=[
            "weak glutes and core from sedentary or standing demands",
            "tight hip flexors altering pelvic alignment",
            "repetitive forward bending without hip hinge mechanics",
            "prolonged static posture — sitting or standing",
        ],
        relief_training_focuses=[
            "glute activation and progressive strengthening",
            "core stability (anti-flexion and anti-rotation patterns)",
            "hip flexor mobility and release",
            "hip hinge mechanics and deadhinge patterns",
        ],
        aggravating_factors=[
            "weak glutes",
            "tight hip flexors",
            "poor lifting mechanics",
        ],
        human_priority_label="Relieve Lower-Back Pain",
    ),
    "wrist": PainAreaProfile(
        area="wrist",
        display_name="Wrist",
        occupational_contributors=[
            "repetitive keyboard and mouse use",
            "sustained wrist extension during desk work",
            "grip-intensive manual tasks",
            "poor ergonomic setup increasing wrist load",
        ],
        relief_training_focuses=[
            "wrist flexor and extensor mobility",
            "forearm strength balance",
            "varied grip strengthening",
            "wrist neutral positioning during training",
        ],
        aggravating_factors=[
            "repetitive gripping and typing",
            "sustained wrist extension",
            "high-volume keyboard work without breaks",
        ],
        human_priority_label="Reduce Wrist Strain",
    ),
    "hip": PainAreaProfile(
        area="hip",
        display_name="Hip",
        occupational_contributors=[
            "prolonged sitting causing hip flexor shortening",
            "poor glute activation from sedentary patterns",
            "driving posture restricting hip range of motion",
            "asymmetric standing and weight-shifting patterns",
        ],
        relief_training_focuses=[
            "hip flexor stretching and progressive mobility",
            "glute activation and strengthening",
            "hip external rotation",
            "single-leg stability and balance",
        ],
        aggravating_factors=[
            "prolonged sitting",
            "tight hip flexors",
            "weak glutes",
        ],
        human_priority_label="Improve Hip Mobility",
    ),
    "knee": PainAreaProfile(
        area="knee",
        display_name="Knee",
        occupational_contributors=[
            "prolonged standing on hard surfaces",
            "repetitive kneeling or squatting during occupational tasks",
            "weak VMO and hip stabilizers increasing joint load",
            "impact loading from occupational movement patterns",
        ],
        relief_training_focuses=[
            "VMO and quad strengthening",
            "hip abductor and stabilizer strength",
            "single-leg balance and neuromuscular control",
            "low-impact progressive strengthening",
        ],
        aggravating_factors=[
            "prolonged standing",
            "kneeling on hard surfaces",
            "weak hip stabilizers",
        ],
        human_priority_label="Protect Your Knees",
    ),
    "ankle": PainAreaProfile(
        area="ankle",
        display_name="Ankle",
        occupational_contributors=[
            "prolonged standing reducing ankle dorsiflexion mobility",
            "impact from occupational movement on hard surfaces",
            "footwear restricting natural ankle range of motion",
        ],
        relief_training_focuses=[
            "ankle dorsiflexion mobility",
            "calf and Achilles capacity",
            "single-leg balance and proprioception",
            "foot and ankle progressive strengthening",
        ],
        aggravating_factors=[
            "prolonged standing",
            "high-impact occupational tasks",
            "restrictive footwear",
        ],
        human_priority_label="Support Ankle Stability",
    ),
}


def get_pain_profile(area: str) -> Optional[PainAreaProfile]:
    return PAIN_DATABASE.get(area)


def list_pain_areas() -> List[dict]:
    return [
        {
            "id": k,
            "display": v.display_name,
            "priority_label": v.human_priority_label,
        }
        for k, v in PAIN_DATABASE.items()
    ]
