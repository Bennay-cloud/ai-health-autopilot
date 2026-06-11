"""
Occupation Engine — maps professions to OccupationProfile.

Each profile captures work demands, posture patterns, movement patterns,
health risks, pain patterns, and future Occupational Health Risk Score
baseline fields (posture_risk_baseline, movement_risk_baseline,
occupational_strain_baseline).
"""
from __future__ import annotations

from pydantic import BaseModel
from typing import Dict, List, Optional


class OccupationProfile(BaseModel):
    profession: str
    profession_display: str
    work_demands: List[str]
    posture_patterns: List[str]
    movement_patterns: List[str]
    health_risks: List[str]
    common_pain_patterns: List[str]
    health_priorities: List[str]            # technical labels — used internally
    work_performance_benefits: List[str]
    recommended_training_focuses: List[str]
    # ── Future Occupational Health Risk Score baselines ────────────────
    posture_risk_baseline: int              # 1-10
    movement_risk_baseline: int             # 1-10
    occupational_strain_baseline: int       # 1-10
    risk_profile_notes: str


OCCUPATION_DATABASE: Dict[str, OccupationProfile] = {
    "software_engineer": OccupationProfile(
        profession="software_engineer",
        profession_display="Software Engineer",
        work_demands=[
            "prolonged sitting (6–10 hours/day)",
            "sustained computer and screen use",
            "low daily movement",
            "high cognitive and deadline-driven load",
        ],
        posture_patterns=[
            "forward head posture from screen work",
            "rounded shoulders from keyboard use",
            "thoracic kyphosis",
            "hip flexor shortening from prolonged sitting",
        ],
        movement_patterns=[
            "minimal walking throughout the day",
            "repetitive small hand and wrist movements",
            "static seated position for long durations",
        ],
        health_risks=[
            "forward head posture",
            "weak posterior chain and glutes",
            "tight hip flexors",
            "neck and upper trapezius tension",
            "reduced thoracic mobility",
            "elevated chronic stress",
        ],
        common_pain_patterns=["neck", "upper_back", "lower_back", "wrist"],
        health_priorities=[
            "Scapular Stability",
            "Posture Restoration",
            "Metabolic Health",
            "Stress Resilience",
        ],
        work_performance_benefits=[
            "improved focus during long coding sessions",
            "less physical discomfort while sitting at a desk",
            "better energy stability through the afternoon",
            "reduced cognitive fatigue caused by physical tension",
        ],
        recommended_training_focuses=[
            "posterior chain strength",
            "scapular stabilizers",
            "thoracic mobility",
            "hip flexor release",
            "aerobic base",
        ],
        posture_risk_baseline=8,
        movement_risk_baseline=9,
        occupational_strain_baseline=7,
        risk_profile_notes="High sedentary risk; primary concerns are postural degradation and metabolic deconditioning.",
    ),
    "nurse": OccupationProfile(
        profession="nurse",
        profession_display="Nurse",
        work_demands=[
            "prolonged standing (8–12 hours/shift)",
            "frequent patient handling and lifting",
            "repetitive bending and reaching",
            "shift work with disrupted sleep cycles",
            "high emotional and physical load",
        ],
        posture_patterns=[
            "anterior pelvic tilt from prolonged standing",
            "lumbar extension under patient load",
            "knee flexion repetition during patient care",
            "forward trunk lean during procedures",
        ],
        movement_patterns=[
            "high daily steps but low-quality movement patterns",
            "repetitive forward bending",
            "asymmetric lifting patterns",
        ],
        health_risks=[
            "lumbar strain from repetitive lifting",
            "knee stress from prolonged standing",
            "shoulder strain from overhead and reaching tasks",
            "shift fatigue reducing recovery capacity",
            "cumulative spinal load",
        ],
        common_pain_patterns=["lower_back", "knee", "shoulder"],
        health_priorities=[
            "Lumbar Stability",
            "Knee Stability",
            "Posterior Chain Strength",
            "Work Capacity",
        ],
        work_performance_benefits=[
            "safer mechanics during patient transfers and lifts",
            "reduced lower-back strain during extended standing",
            "less knee fatigue at the end of long shifts",
            "more energy maintained in the final hours of a shift",
        ],
        recommended_training_focuses=[
            "glute activation and strength",
            "core stability",
            "hip mobility",
            "VMO and knee stabilizers",
            "posterior chain",
        ],
        posture_risk_baseline=6,
        movement_risk_baseline=5,
        occupational_strain_baseline=9,
        risk_profile_notes="High occupational strain from lifting and standing; primary concerns are lumbar and knee integrity.",
    ),
    "teacher": OccupationProfile(
        profession="teacher",
        profession_display="Teacher",
        work_demands=[
            "prolonged standing and classroom movement",
            "frequent voice use and vocal load",
            "high emotional and cognitive demands",
            "variable posture throughout the day",
            "limited structured recovery windows",
        ],
        posture_patterns=[
            "anterior weight shift from prolonged standing",
            "neck strain from board and screen work",
            "asymmetric posture from one-sided demonstration",
        ],
        movement_patterns=[
            "moderate daily movement without intentional structure",
            "frequent positional changes throughout the day",
            "limited time for planned exercise",
        ],
        health_risks=[
            "lower back discomfort from prolonged standing",
            "knee stress from hard floor surfaces",
            "chronic stress from emotional and cognitive load",
            "moderate voice and neck strain",
        ],
        common_pain_patterns=["lower_back", "knee", "neck"],
        health_priorities=[
            "Lumbar Stability",
            "Knee Stability",
            "Stress Resilience",
            "Metabolic Health",
        ],
        work_performance_benefits=[
            "less lower-back fatigue during long teaching blocks",
            "better energy for afternoon classes",
            "reduced knee discomfort from classroom movement",
            "improved stress tolerance for challenging days",
        ],
        recommended_training_focuses=[
            "glute and core strength",
            "knee stabilizers",
            "stress management through movement",
            "aerobic base",
        ],
        posture_risk_baseline=5,
        movement_risk_baseline=4,
        occupational_strain_baseline=7,
        risk_profile_notes="Moderate occupational strain; standing fatigue and stress load are primary risks.",
    ),
    "driver": OccupationProfile(
        profession="driver",
        profession_display="Driver",
        work_demands=[
            "prolonged sitting in vehicle seat",
            "whole-body vibration exposure",
            "repetitive steering and pedal movements",
            "very low physical movement",
            "sustained visual and mental concentration",
        ],
        posture_patterns=[
            "lumbar flexion from vehicle seat curvature",
            "hip flexor shortening",
            "forward head from windscreen position",
            "shoulder internal rotation from sustained steering",
        ],
        movement_patterns=[
            "minimal daily movement",
            "no postural variation for hours",
            "vibration load on the spine",
        ],
        health_risks=[
            "lower back disc pressure from vibration and sustained sitting",
            "hip flexor tightness limiting pelvic mobility",
            "neck tension from driving posture",
            "cardiovascular deconditioning",
        ],
        common_pain_patterns=["lower_back", "hip", "neck", "wrist"],
        health_priorities=[
            "Lumbar Stability",
            "Hip Mobility",
            "Posture Restoration",
            "Metabolic Health",
        ],
        work_performance_benefits=[
            "less lower-back stiffness during and between long drives",
            "improved alertness from better circulation",
            "reduced hip and leg fatigue during extended journeys",
        ],
        recommended_training_focuses=[
            "hip flexor mobility",
            "glute activation",
            "lumbar decompression and stabilization",
            "aerobic base",
        ],
        posture_risk_baseline=8,
        movement_risk_baseline=9,
        occupational_strain_baseline=7,
        risk_profile_notes="High sedentary and spinal vibration risk; similar profile to desk workers but with added vibration load.",
    ),
    "manager": OccupationProfile(
        profession="manager",
        profession_display="Manager",
        work_demands=[
            "prolonged sitting in meetings and at desk",
            "high cognitive and decision-making load",
            "frequent travel disrupting routine",
            "elevated chronic stress",
            "irregular and extended working hours",
        ],
        posture_patterns=[
            "forward head from screen and phone use",
            "rounded shoulders",
            "hip flexor tightening from prolonged sitting",
        ],
        movement_patterns=[
            "low to moderate movement with travel disruptions",
            "meeting-heavy schedule reducing movement breaks",
            "irregular exercise due to work demands",
        ],
        health_risks=[
            "chronic stress with insufficient recovery",
            "forward head posture",
            "weak posterior chain",
            "cardiovascular deconditioning from sedentary patterns",
            "sleep disruption from workload",
        ],
        common_pain_patterns=["neck", "upper_back", "lower_back"],
        health_priorities=[
            "Stress Resilience",
            "Posture Restoration",
            "Metabolic Health",
            "Work Capacity",
        ],
        work_performance_benefits=[
            "better focus and decision quality throughout the day",
            "reduced physical tension during high-pressure situations",
            "more energy available for evening commitments",
            "improved stress tolerance in demanding periods",
        ],
        recommended_training_focuses=[
            "stress management through movement",
            "posterior chain strength",
            "aerobic base",
            "mobility and recovery",
        ],
        posture_risk_baseline=7,
        movement_risk_baseline=8,
        occupational_strain_baseline=8,
        risk_profile_notes="High stress-driven strain; burnout risk and cardiovascular health are primary long-term concerns.",
    ),
    "construction_worker": OccupationProfile(
        profession="construction_worker",
        profession_display="Construction Worker",
        work_demands=[
            "heavy manual labour",
            "frequent overhead and heavy lifting",
            "kneeling, crouching, and squatting",
            "impact and vibration exposure",
            "variable weather and environmental conditions",
        ],
        posture_patterns=[
            "asymmetric loading from one-sided tasks",
            "lumbar extension under heavy load",
            "shoulder impingement risk from overhead work",
        ],
        movement_patterns=[
            "high physical activity but repetitive and asymmetric",
            "minimal intentional mobility work",
            "fatigue-driven deterioration in movement quality",
        ],
        health_risks=[
            "knee joint damage from kneeling and impact",
            "shoulder impingement from repetitive overhead tasks",
            "lumbar injury risk from heavy lifting",
            "cumulative joint wear across career",
        ],
        common_pain_patterns=["knee", "shoulder", "lower_back"],
        health_priorities=[
            "Knee Stability",
            "Shoulder Stability",
            "Lumbar Stability",
            "Recovery Optimization",
        ],
        work_performance_benefits=[
            "safer mechanics during heavy lifts and overhead tasks",
            "reduced joint fatigue by the end of a shift",
            "better recovery between physically demanding days",
            "improved movement quality reducing injury risk",
        ],
        recommended_training_focuses=[
            "joint stability and corrective movement",
            "mobility and active recovery",
            "balanced strength",
            "posterior chain",
        ],
        posture_risk_baseline=5,
        movement_risk_baseline=3,
        occupational_strain_baseline=9,
        risk_profile_notes="Highest occupational strain category; injury prevention and joint longevity are the primary concerns.",
    ),
    "sales_representative": OccupationProfile(
        profession="sales_representative",
        profession_display="Sales Representative",
        work_demands=[
            "frequent driving and travel",
            "prolonged sitting in car and at client sites",
            "client-facing social and presentation demands",
            "standing during client presentations",
            "irregular eating and sleep patterns from travel",
        ],
        posture_patterns=[
            "hip flexor tightness from driving posture",
            "forward head from phone and navigation use",
            "variable posture throughout mixed-activity days",
        ],
        movement_patterns=[
            "mixed — extended sitting alternating with walking",
            "limited structured exercise time due to travel",
            "irregular routine disrupting consistency",
        ],
        health_risks=[
            "lower back strain from driving posture",
            "hip flexor tightness",
            "metabolic impact from irregular eating",
            "moderate chronic stress from targets",
        ],
        common_pain_patterns=["lower_back", "hip", "neck"],
        health_priorities=[
            "Hip Mobility",
            "Lumbar Stability",
            "Metabolic Health",
            "Stress Resilience",
        ],
        work_performance_benefits=[
            "less stiffness when transitioning from driving to client meetings",
            "better posture and presence during presentations",
            "improved energy and mental sharpness in afternoon appointments",
        ],
        recommended_training_focuses=[
            "hip flexor mobility",
            "posterior chain strength",
            "aerobic base",
            "stress management",
        ],
        posture_risk_baseline=7,
        movement_risk_baseline=6,
        occupational_strain_baseline=6,
        risk_profile_notes="Moderate strain with irregular lifestyle patterns; hip health and metabolic function are key concerns.",
    ),
    "chef": OccupationProfile(
        profession="chef",
        profession_display="Chef",
        work_demands=[
            "prolonged standing on hard surfaces",
            "repetitive wrist and hand movements",
            "heat, noise, and time pressure",
            "heavy lifting of equipment and supplies",
            "shift work with irregular hours",
        ],
        posture_patterns=[
            "anterior weight shift from prolonged standing",
            "wrist flexion repetition during prep work",
            "shoulder elevation from sustained arm work",
        ],
        movement_patterns=[
            "high daily movement but limited positional variation",
            "repetitive upper-limb patterns",
            "minimal intentional recovery between shifts",
        ],
        health_risks=[
            "knee and foot fatigue from standing on hard surfaces",
            "wrist strain from repetitive cutting and stirring",
            "lower back stress from standing and lifting",
            "shoulder tension from sustained arm work",
        ],
        common_pain_patterns=["knee", "wrist", "lower_back", "shoulder"],
        health_priorities=[
            "Knee Stability",
            "Wrist and Forearm Health",
            "Lumbar Stability",
            "Recovery Optimization",
        ],
        work_performance_benefits=[
            "less foot and knee fatigue during service",
            "reduced wrist strain during long prep sessions",
            "more energy for dinner service after afternoon preparation",
        ],
        recommended_training_focuses=[
            "knee stabilizers",
            "wrist mobility and strength",
            "glute and core strength",
            "active recovery",
        ],
        posture_risk_baseline=5,
        movement_risk_baseline=3,
        occupational_strain_baseline=8,
        risk_profile_notes="High physical demand with repetitive patterns; joint fatigue and wrist health are primary concerns.",
    ),
    "office_worker": OccupationProfile(
        profession="office_worker",
        profession_display="Office Worker",
        work_demands=[
            "prolonged sitting",
            "computer and screen use",
            "low daily movement",
            "moderate cognitive load",
            "meeting-heavy schedule",
        ],
        posture_patterns=[
            "forward head posture",
            "rounded shoulders",
            "hip flexor shortening from prolonged sitting",
        ],
        movement_patterns=[
            "minimal movement throughout the day",
            "static seated position",
            "short walking distances within the office only",
        ],
        health_risks=[
            "forward head posture",
            "weak posterior chain",
            "tight hip flexors",
            "metabolic deconditioning from inactivity",
        ],
        common_pain_patterns=["neck", "upper_back", "lower_back"],
        health_priorities=[
            "Posture Restoration",
            "Metabolic Health",
            "Scapular Stability",
            "Stress Resilience",
        ],
        work_performance_benefits=[
            "less physical discomfort during desk work",
            "better energy levels in the afternoon",
            "improved focus and concentration",
        ],
        recommended_training_focuses=[
            "posture and posterior chain",
            "aerobic base",
            "mobility",
            "stress management",
        ],
        posture_risk_baseline=8,
        movement_risk_baseline=9,
        occupational_strain_baseline=6,
        risk_profile_notes="Similar profile to software engineers; sedentary risk and postural decline are primary concerns.",
    ),
    "freelancer": OccupationProfile(
        profession="freelancer",
        profession_display="Freelancer",
        work_demands=[
            "irregular working hours and self-management demands",
            "prolonged sitting at home setup",
            "isolation and social stress",
            "high variability in workload and pressure",
            "often poor ergonomic environment",
        ],
        posture_patterns=[
            "forward head from laptop use at home",
            "rounded shoulders",
            "often suboptimal desk and chair setup",
        ],
        movement_patterns=[
            "very low structured movement",
            "tendency to skip movement breaks",
            "irregular exercise patterns disrupted by project cycles",
        ],
        health_risks=[
            "postural deconditioning from poor home ergonomics",
            "social and isolation-driven stress",
            "irregular routine disrupting sleep quality",
            "weak posterior chain",
        ],
        common_pain_patterns=["neck", "upper_back", "lower_back"],
        health_priorities=[
            "Stress Resilience",
            "Posture Restoration",
            "Metabolic Health",
            "Work Capacity",
        ],
        work_performance_benefits=[
            "better focus and creative output during deep work sessions",
            "less physical tension reducing distraction",
            "improved mental energy through structured daily movement",
        ],
        recommended_training_focuses=[
            "stress management",
            "posture correction",
            "aerobic base",
            "routine-building through consistent movement",
        ],
        posture_risk_baseline=8,
        movement_risk_baseline=9,
        occupational_strain_baseline=6,
        risk_profile_notes="High sedentary and stress risk compounded by irregular routine and isolation.",
    ),
    "student": OccupationProfile(
        profession="student",
        profession_display="Student",
        work_demands=[
            "prolonged sitting during study sessions",
            "high cognitive and exam-period stress",
            "screen-intensive work",
            "irregular sleep patterns",
            "often poor ergonomic setup",
        ],
        posture_patterns=[
            "forward head from laptop use",
            "rounded shoulders",
            "prolonged lumbar flexion during study",
        ],
        movement_patterns=[
            "low structured movement",
            "sedentary study blocks",
            "some campus or commuting walking",
        ],
        health_risks=[
            "forward head posture",
            "chronic study-related stress affecting recovery",
            "sleep disruption affecting health and performance",
            "weak posterior chain",
        ],
        common_pain_patterns=["neck", "upper_back", "lower_back"],
        health_priorities=[
            "Stress Resilience",
            "Posture Restoration",
            "Metabolic Health",
            "Sleep Quality",
        ],
        work_performance_benefits=[
            "better concentration and retention during study sessions",
            "reduced physical tension that distracts from learning",
            "improved sleep quality supporting memory consolidation",
        ],
        recommended_training_focuses=[
            "stress management",
            "posture correction",
            "aerobic base",
            "sleep optimization",
        ],
        posture_risk_baseline=7,
        movement_risk_baseline=8,
        occupational_strain_baseline=5,
        risk_profile_notes="Moderate risk driven by stress and sedentary study patterns; often underestimated.",
    ),
    "physiotherapist": OccupationProfile(
        profession="physiotherapist",
        profession_display="Physiotherapist",
        work_demands=[
            "manual patient handling and treatment",
            "prolonged bending and forward leaning",
            "standing throughout patient sessions",
            "repetitive upper-limb manual therapy work",
            "moderate cognitive and emotional load",
        ],
        posture_patterns=[
            "forward trunk lean during treatment",
            "asymmetric arm and shoulder loading",
            "repetitive wrist and hand use",
        ],
        movement_patterns=[
            "moderate daily movement",
            "repetitive manual therapy patterns",
            "variable posture throughout the treatment day",
        ],
        health_risks=[
            "lower back strain from sustained bending postures",
            "wrist and hand overuse from manual therapy",
            "shoulder overuse from repetitive techniques",
            "compassion fatigue contributing to stress load",
        ],
        common_pain_patterns=["lower_back", "wrist", "shoulder"],
        health_priorities=[
            "Lumbar Stability",
            "Wrist and Forearm Health",
            "Shoulder Stability",
            "Stress Resilience",
        ],
        work_performance_benefits=[
            "safer body mechanics during patient treatment",
            "reduced wrist fatigue during manual therapy sessions",
            "more energy and precision in afternoon patient sessions",
        ],
        recommended_training_focuses=[
            "glute and core stability",
            "wrist strength and mobility",
            "shoulder health and balance",
            "aerobic recovery",
        ],
        posture_risk_baseline=6,
        movement_risk_baseline=4,
        occupational_strain_baseline=7,
        risk_profile_notes="Occupational irony — therapists frequently neglect their own structural health while treating others.",
    ),
}


def get_occupation_profile(profession: str) -> Optional[OccupationProfile]:
    return OCCUPATION_DATABASE.get(profession)


def list_professions() -> List[dict]:
    return sorted(
        [{"id": k, "display": v.profession_display} for k, v in OCCUPATION_DATABASE.items()],
        key=lambda x: x["display"],
    )
