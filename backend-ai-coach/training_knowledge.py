"""
Training Knowledge Database.

Maps training types to structured knowledge:
  - physiological_adaptations
  - work_performance_benefits  (new layer)
  - long_term_health_benefits
  - best_for_occupations        (used by explanation engine for context)
  - addresses_pain_areas        (used by explanation engine for context)
"""
from __future__ import annotations

from pydantic import BaseModel
from typing import Dict, List, Optional


class TrainingTypeProfile(BaseModel):
    training_type: str
    display_name: str
    physiological_adaptations: List[str]
    work_performance_benefits: List[str]
    long_term_health_benefits: List[str]
    best_for_occupations: List[str]
    addresses_pain_areas: List[str]


TRAINING_DATABASE: Dict[str, TrainingTypeProfile] = {
    "strength": TrainingTypeProfile(
        training_type="strength",
        display_name="Strength Training",
        physiological_adaptations=[
            "enhanced neural drive and motor unit recruitment",
            "muscle fibre hypertrophy and cross-sectional area increase",
            "connective tissue and tendon strengthening",
            "bone density improvement",
        ],
        work_performance_benefits=[
            "reduced fatigue during physically demanding occupational tasks",
            "improved postural endurance during long work sessions",
            "greater physical confidence and capacity for occupational movements",
        ],
        long_term_health_benefits=[
            "preserved muscle mass and function with age",
            "reduced injury and strain risk",
            "improved bone density reducing fracture risk",
            "metabolic health support",
        ],
        best_for_occupations=["construction_worker", "nurse", "physiotherapist"],
        addresses_pain_areas=["lower_back", "knee", "shoulder"],
    ),
    "strength_endurance": TrainingTypeProfile(
        training_type="strength_endurance",
        display_name="Strength Endurance",
        physiological_adaptations=[
            "increased capillarisation in working muscles",
            "improved aerobic energy production within muscle tissue",
            "enhanced muscular fatigue resistance",
            "improved lactate clearance",
        ],
        work_performance_benefits=[
            "sustained concentration and output throughout the workday",
            "reduced physical fatigue during long sessions",
            "more stable energy levels without afternoon crashes",
        ],
        long_term_health_benefits=[
            "improved cardiovascular health",
            "metabolic flexibility and efficiency",
            "healthy ageing through maintained work capacity",
        ],
        best_for_occupations=["nurse", "teacher", "chef"],
        addresses_pain_areas=["lower_back", "knee"],
    ),
    "mobility": TrainingTypeProfile(
        training_type="mobility",
        display_name="Mobility & Corrective",
        physiological_adaptations=[
            "increased joint range of motion",
            "reduced myofascial tension and tissue stiffness",
            "improved neuromuscular control and body awareness",
            "normalisation of movement patterns",
        ],
        work_performance_benefits=[
            "easier movement after prolonged sitting or standing",
            "reduced stiffness during and after work",
            "better body mechanics during occupational tasks",
        ],
        long_term_health_benefits=[
            "joint health preservation",
            "injury and strain prevention",
            "healthy ageing through maintained mobility",
            "reduced degenerative joint risk",
        ],
        best_for_occupations=["software_engineer", "office_worker", "driver", "freelancer"],
        addresses_pain_areas=["neck", "upper_back", "lower_back", "hip", "ankle"],
    ),
    "yoga": TrainingTypeProfile(
        training_type="yoga",
        display_name="Yoga",
        physiological_adaptations=[
            "improved tissue extensibility and flexibility",
            "enhanced parasympathetic nervous system activity",
            "improved breathing mechanics and respiratory capacity",
            "neuromuscular relaxation and body awareness",
        ],
        work_performance_benefits=[
            "reduced work-related stress and physical tension",
            "improved mental clarity for cognitive and creative tasks",
            "better sleep quality supporting work performance",
        ],
        long_term_health_benefits=[
            "stress resilience and mental health",
            "joint mobility preservation",
            "improved sleep quality",
            "sustainable nervous system health",
        ],
        best_for_occupations=["manager", "teacher", "freelancer", "student"],
        addresses_pain_areas=["neck", "upper_back", "lower_back", "hip"],
    ),
    "zone2_cardio": TrainingTypeProfile(
        training_type="zone2_cardio",
        display_name="Zone 2 Cardio",
        physiological_adaptations=[
            "mitochondrial density increase in muscle cells",
            "improved fat oxidation at moderate intensities",
            "increased cardiac stroke volume",
            "enhanced aerobic base capacity",
        ],
        work_performance_benefits=[
            "sustained mental energy and focus throughout the workday",
            "improved tolerance for work-related stress",
            "better afternoon concentration without energy dips",
        ],
        long_term_health_benefits=[
            "cardiovascular health and longevity",
            "metabolic flexibility",
            "healthy ageing through sustained aerobic capacity",
            "reduced all-cause mortality risk",
        ],
        best_for_occupations=["manager", "software_engineer", "driver", "office_worker"],
        addresses_pain_areas=[],
    ),
    "interval_training": TrainingTypeProfile(
        training_type="interval_training",
        display_name="Interval Training",
        physiological_adaptations=[
            "VO2max improvement",
            "improved anaerobic threshold",
            "enhanced cardiac output",
            "elevated metabolic rate post-exercise",
        ],
        work_performance_benefits=[
            "efficient training output within limited time windows",
            "elevated energy levels in the hours following training",
            "improved stress response and resilience",
        ],
        long_term_health_benefits=[
            "cardiovascular fitness and longevity",
            "metabolic health and body composition",
            "improved insulin sensitivity",
        ],
        best_for_occupations=["manager", "sales_representative", "freelancer"],
        addresses_pain_areas=[],
    ),
    "active_recovery": TrainingTypeProfile(
        training_type="active_recovery",
        display_name="Active Recovery",
        physiological_adaptations=[
            "increased blood flow without additional muscular stress",
            "metabolic waste product clearance",
            "nervous system downregulation",
            "reduced delayed onset muscle soreness",
        ],
        work_performance_benefits=[
            "reduced fatigue entering the next workday or shift",
            "improved mental recovery and readiness",
            "better physical preparedness for demanding upcoming days",
        ],
        long_term_health_benefits=[
            "improved training consistency through injury prevention",
            "sustainable long-term performance",
            "nervous system health and recovery capacity",
        ],
        best_for_occupations=["construction_worker", "nurse", "chef", "physiotherapist"],
        addresses_pain_areas=["lower_back", "knee", "shoulder"],
    ),
    "pilates": TrainingTypeProfile(
        training_type="pilates",
        display_name="Pilates",
        physiological_adaptations=[
            "deep core stabiliser activation",
            "improved spinal segmental control",
            "neuromuscular coordination",
            "postural muscle endurance",
        ],
        work_performance_benefits=[
            "improved sitting and standing posture during work",
            "reduced lower back tension from desk or standing work",
            "better body mechanics during occupational tasks",
        ],
        long_term_health_benefits=[
            "spinal health and structural resilience",
            "core stability maintained through ageing",
            "reduced chronic back pain risk",
        ],
        best_for_occupations=["software_engineer", "office_worker", "driver", "teacher"],
        addresses_pain_areas=["lower_back", "upper_back", "hip"],
    ),
    "hypertrophy": TrainingTypeProfile(
        training_type="hypertrophy",
        display_name="Hypertrophy Training",
        physiological_adaptations=[
            "muscle fibre cross-sectional area increase",
            "increased resting metabolic rate",
            "improved hormonal environment supporting recovery",
            "connective tissue and structural adaptation",
        ],
        work_performance_benefits=[
            "greater physical work capacity for demanding occupational tasks",
            "improved physical confidence",
            "reduced fatigue from occupational physical demands",
        ],
        long_term_health_benefits=[
            "preserved muscle mass and function with age",
            "improved metabolic health and insulin sensitivity",
            "bone density support",
            "healthier long-term body composition",
        ],
        best_for_occupations=["construction_worker", "nurse", "sales_representative"],
        addresses_pain_areas=["lower_back", "knee", "shoulder"],
    ),
    "light_strength": TrainingTypeProfile(
        training_type="light_strength",
        display_name="Light Strength",
        physiological_adaptations=[
            "neuromuscular activation without excessive load",
            "joint stability improvement",
            "movement quality enhancement",
            "mild muscular endurance gain",
        ],
        work_performance_benefits=[
            "maintained physical function on high-demand or recovery days",
            "joint stability supporting occupational movements",
            "improved movement quality during work tasks",
        ],
        long_term_health_benefits=[
            "movement pattern maintenance and injury prevention",
            "consistent physical function",
            "structural resilience built gradually",
        ],
        best_for_occupations=["nurse", "physiotherapist", "construction_worker"],
        addresses_pain_areas=["lower_back", "knee", "shoulder", "hip"],
    ),
    "circuit": TrainingTypeProfile(
        training_type="circuit",
        display_name="Circuit Training",
        physiological_adaptations=[
            "combined aerobic and muscular adaptations",
            "elevated metabolic rate",
            "improved work capacity",
            "efficient caloric expenditure",
        ],
        work_performance_benefits=[
            "efficient training within time-limited schedules",
            "maintained energy and physical capacity",
            "improved stress response",
        ],
        long_term_health_benefits=[
            "cardiovascular health",
            "maintained muscle mass and function",
            "metabolic health",
        ],
        best_for_occupations=["manager", "sales_representative", "teacher"],
        addresses_pain_areas=[],
    ),
    "walking": TrainingTypeProfile(
        training_type="walking",
        display_name="Walking",
        physiological_adaptations=[
            "gentle aerobic system activation",
            "improved peripheral circulation",
            "mild metabolic rate elevation",
        ],
        work_performance_benefits=[
            "mental clarity and stress reduction during or after work",
            "improved circulation reducing the effects of sedentary patterns",
            "gentle recovery from physical occupational demands",
        ],
        long_term_health_benefits=[
            "cardiovascular baseline maintenance",
            "mental health and wellbeing",
            "longevity and healthy ageing",
        ],
        best_for_occupations=["software_engineer", "office_worker", "freelancer", "student"],
        addresses_pain_areas=["lower_back", "hip"],
    ),
    "plyometric": TrainingTypeProfile(
        training_type="plyometric",
        display_name="Plyometric Training",
        physiological_adaptations=[
            "improved reactive strength and power",
            "tendon stiffness and energy return",
            "neuromuscular power output",
        ],
        work_performance_benefits=[
            "improved explosive physical capacity for demanding tasks",
            "better neuromuscular control in dynamic occupational movements",
        ],
        long_term_health_benefits=[
            "bone density",
            "tendon health and resilience",
            "preserved power output with ageing",
        ],
        best_for_occupations=["construction_worker"],
        addresses_pain_areas=[],
    ),
}


def get_training_profile(training_type: str) -> Optional[TrainingTypeProfile]:
    return TRAINING_DATABASE.get(training_type)
