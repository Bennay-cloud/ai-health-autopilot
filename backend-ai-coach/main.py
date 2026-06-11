from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Optional, List
from gpt_service import generate_plan
from db import users_collection, orders_collection, auth_users_collection
from pdf_generator import generate_pdf
from auth import hash_password, verify_password, create_access_token, get_current_user
from daily_decision_engine import DailyDecisionRequest, generate_daily_decision
from meal_catalog_service import select_weekly_meals, get_meal_by_id
from order_service import confirm_daily_delivery, confirm_weekly_order
import workout_session_service as wss
import decision_record_service as drs
import anti_ghosting_service as ags
import outcome_tracking_service as ots
import personal_learning_engine as ple
import preference_engine as prefe
from db import (
    decision_records_collection, outcome_records_collection,
    user_feedback_collection, user_preferences_collection,
)
from occupation_engine import list_professions
from pain_engine import list_pain_areas
import os
import re
import uuid
from datetime import datetime, timezone


class UserProfile(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    geschlecht: str
    alter: int = Field(..., ge=10, le=100)
    gewicht: float = Field(..., ge=20, le=300)
    ziel: str
    ernaehrung: str
    equipment: Optional[str] = ""
    supplements: bool = False
    level: str
    training_days: int = Field(..., ge=1, le=6)


class OrderRequest(BaseModel):
    user_name: str = Field(..., min_length=1, max_length=50)
    meal_ids: List[str] = Field(..., min_length=1)


class DailyDeliveryRequest(BaseModel):
    meal_id: str
    meal_slot: str               # "lunch" | "dinner"
    delivery_location: str       # "home" | "office" | "travel"
    scheduled_time: Optional[str] = None


class WorkoutStartRequest(BaseModel):
    workout_id: str
    workout_name: str
    total_sets: int = Field(..., ge=1)


class WorkoutProgressRequest(BaseModel):
    session_id: str
    exercise_name: str
    sets_completed: int = Field(1, ge=1)


class WorkoutCompleteRequest(BaseModel):
    session_id: str
    duration_seconds: int = Field(..., ge=0)
    intensity: str = "moderate"
    completed_exercises: Optional[List[str]] = None
    completed_sets: Optional[int] = None


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    email: str = Field(..., min_length=5, max_length=100)
    password: str = Field(..., min_length=8)


class LoginRequest(BaseModel):
    email: str
    password: str


class DailyOutcomeInput(BaseModel):
    user_id: str
    mood: float = Field(..., ge=1, le=10)
    energy: float = Field(..., ge=1, le=10)
    stress: float = Field(..., ge=1, le=10)
    sleep_hours: float = Field(..., ge=0, le=24)
    notes: Optional[str] = None
    date: Optional[str] = None


class WeeklyOutcomeInput(BaseModel):
    user_id: str
    weight_kg: Optional[float] = None
    waist_cm: Optional[float] = None
    body_fat_percentage: Optional[float] = None
    date: Optional[str] = None


app = FastAPI()

# CORS aktivieren – wichtig für Verbindung Frontend <-> Backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # später evtl. auf dein Frontend beschränken
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# PDF-Verzeichnis (optional erzeugen)
PDF_DIR = "generated_pdfs"
os.makedirs(PDF_DIR, exist_ok=True)

# Erlaube statische Auslieferung der PDFs über /pdfs/...
app.mount("/pdfs", StaticFiles(directory=PDF_DIR), name="pdfs")

# Root Endpoint für Test
@app.get("/")
def root():
    return {"message": "Backend läuft 🎯"}


# ── Auth Endpoints ────────────────────────────────────────────────

@app.post("/auth/register")
def register(req: RegisterRequest):
    if auth_users_collection.find_one({"email": req.email}):
        raise HTTPException(status_code=400, detail="E-Mail bereits registriert.")
    auth_users_collection.insert_one({
        "name": req.name,
        "email": req.email,
        "password": hash_password(req.password),
        "created_at": datetime.utcnow().isoformat(),
    })
    token = create_access_token(req.email)
    return {"access_token": token, "token_type": "bearer", "user": {"name": req.name, "email": req.email}}


@app.post("/auth/login")
def login(req: LoginRequest):
    user = auth_users_collection.find_one({"email": req.email})
    if not user or not verify_password(req.password, user["password"]):
        raise HTTPException(status_code=401, detail="Ungültige E-Mail oder Passwort.")
    token = create_access_token(req.email)
    return {"access_token": token, "token_type": "bearer", "user": {"name": user["name"], "email": user["email"]}}


@app.get("/auth/me")
def me(current_user: dict = Depends(get_current_user)):
    return current_user

# ── Occupational Health Reference Endpoints ───────────────────────

@app.get("/api/health/occupations")
def get_occupations():
    return {"professions": list_professions()}


@app.get("/api/health/pain-areas")
def get_pain_areas():
    return {"pain_areas": list_pain_areas()}


@app.post("/api/health/profile")
def save_health_profile(body: dict):
    """
    Stores a user's occupational health profile for future learning.
    Part 9 — enables future adherence-explanation correlation analysis.
    """
    from db import db
    health_profiles = db["health_profiles"]
    body["created_at"] = datetime.now(timezone.utc).isoformat()
    result = health_profiles.insert_one(body)
    return {"profile_id": str(result.inserted_id)}


# POST Endpoint für das Formular
@app.post("/formdata")
async def formdata(profile: UserProfile, current_user: dict = Depends(get_current_user)):
    data = profile.model_dump()
    print("Erhalten vom Frontend:", data)

    # Passende Mahlzeiten aus dem Katalog holen (shared catalog service)
    matched_meals = select_weekly_meals(profile.ernaehrung, profile.ziel, limit=6)

    # GPT-Antwort generieren
    try:
        gpt_response = generate_plan(data)
    except Exception as e:
        print(f"AI-Fehler: {e}")
        raise HTTPException(status_code=502, detail=f"AI-Service nicht erreichbar: {str(e)}")
    print("GPT-Antwort erhalten")

    # PDF erzeugen (Dateiname bereinigen um Path-Traversal zu verhindern)
    safe_name = re.sub(r"[^\w\-]", "_", profile.name)[:30]
    pdf_filename = f"{safe_name}_plan.pdf"
    pdf_path = os.path.join(PDF_DIR, pdf_filename)
    generate_pdf(gpt_response, pdf_path)

    # Daten in MongoDB speichern (nicht-blockierend für den User)
    try:
        users_collection.insert_one({**data, "gpt_plan": gpt_response, "pdf_filename": pdf_filename, "user_email": current_user["email"]})
    except Exception as e:
        print(f"MongoDB Fehler (nicht kritisch): {e}")

    return {
        "status": "ok",
        "plan": gpt_response,
        "pdf_url": f"/pdfs/{pdf_filename}",
        "matched_meals": [m.model_dump() for m in matched_meals],
    }


@app.post("/api/health-autopilot/daily-decision")
def daily_decision(request: DailyDecisionRequest):
    # Pre-fetch preference profile for preference-aware workout selection
    effective_user_id_pre = request.user_id or request.user_profile.name
    pref_preferred: Optional[list] = None
    pref_disliked:  Optional[list] = None
    try:
        pre_records  = drs.get_user_history(decision_records_collection, effective_user_id_pre)
        pre_wo_fb    = prefe.get_workout_feedbacks(user_feedback_collection, effective_user_id_pre)
        pre_meal_fb  = prefe.get_meal_feedbacks(user_feedback_collection, effective_user_id_pre)
        pre_profile  = prefe.compute_preference_profile(
            effective_user_id_pre, pre_records, pre_wo_fb, pre_meal_fb
        )
        pref_preferred = pre_profile.preferred_workout_types or None
        pref_disliked  = pre_profile.disliked_workout_types  or None
    except Exception as e:
        print(f"Preference pre-fetch failed (non-critical): {e}")

    response = generate_daily_decision(
        request,
        user_preferred_workout_types=pref_preferred,
        user_disliked_workout_types=pref_disliked,
    )

    # Auto-create a DecisionRecord capturing context + decision
    record_id: Optional[str] = None
    effective_user_id = request.user_id or request.user_profile.name
    try:
        context = drs.RecordContext(
            sleep_hours=request.daily_context.sleep_hours,
            stress_level=request.daily_context.stress_level,
            mood=request.daily_context.mood_level,
            meetings=request.daily_context.meetings_count,
            travel=request.daily_context.travel_today,
            cycle_phase=response.cycle_phase.phase,
            previous_workout=(
                str(request.daily_context.previous_day_workout_intensity)
                if request.daily_context.previous_day_workout_intensity is not None
                else None
            ),
            goal=request.user_profile.ziel,
            recovery_score=response.recovery_score,
            energy_score=response.energy_score,
            stress_score=response.stress_score,
            context_flags=response.context_flags,
        )
        decision = drs.RecordDecision(
            day_type=response.day_type,
            workout_type=response.selected_workout.workout_type,
            workout_duration_recommended=response.workout_duration_breakdown.total_minutes,
            workout_intensity=response.selected_workout.intensity,
            selected_lunch=response.selected_lunch.name,
            selected_dinner=response.selected_dinner.name,
            meal_calories=response.selected_lunch.calories + response.selected_dinner.calories,
            delivery_location=request.daily_context.location_today,
            workout_time=response.workout_time,
            sleep_target=request.daily_context.sleep_target_time,
        )
        record = drs.DecisionRecord(
            user_id=effective_user_id,
            date=(request.daily_context.date or datetime.now(timezone.utc).date().isoformat()),
            context=context,
            decision=decision,
        )
        record_id = drs.create_record(decision_records_collection, record)
    except Exception as e:
        print(f"DecisionRecord creation failed (non-critical): {e}")

    # Anti-ghosting: adapt recommendation based on user history
    adaptive: Optional[dict] = None
    try:
        history = drs.get_user_history(decision_records_collection, effective_user_id)
        adherence = drs.get_user_adherence(decision_records_collection, effective_user_id)
        rec = ags.generate_adaptive_recommendation(
            records=history,
            adherence=adherence,
            current_duration=response.workout_duration_breakdown.total_minutes,
            current_intensity=response.selected_workout.intensity,
        )
        adaptive = rec.model_dump()
    except Exception as e:
        print(f"Anti-ghosting adaptation failed (non-critical): {e}")

    # Personal learning: attach personalization note when applicable
    try:
        history = drs.get_user_history(decision_records_collection, effective_user_id)
        outcomes = ots.get_user_outcomes(outcome_records_collection, effective_user_id)
        if history:
            learning_profile = ple.analyze_learning_profile(history, outcomes, effective_user_id)
            note = ple.build_personalization_note(
                learning_profile,
                response.workout_duration_breakdown.total_minutes,
            )
            response.personalization_note = note
    except Exception as e:
        print(f"Personal learning note failed (non-critical): {e}")

    # Preference engine: attach preference note
    try:
        wo_feedbacks   = prefe.get_workout_feedbacks(user_feedback_collection, effective_user_id)
        meal_feedbacks = prefe.get_meal_feedbacks(user_feedback_collection, effective_user_id)
        pref_profile   = prefe.compute_preference_profile(
            effective_user_id,
            drs.get_user_history(decision_records_collection, effective_user_id),
            wo_feedbacks,
            meal_feedbacks,
        )
        response.preference_note = prefe.build_preference_note(
            pref_profile,
            response.selected_workout.workout_type,
            response.workout_duration_breakdown.total_minutes,
        )
    except Exception as e:
        print(f"Preference note failed (non-critical): {e}")

    result = response.model_dump()
    result["record_id"] = record_id
    result["adaptive_recommendation"] = adaptive
    return result


@app.post("/api/decision-records/{record_id}/outcome")
def record_outcome(record_id: str, inp: drs.OutcomeInput):
    existing = drs.get_record(decision_records_collection, record_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Decision record not found.")
    outcome = drs.build_outcome(inp, existing.decision.workout_duration_recommended)
    updated = drs.update_record_outcome(decision_records_collection, record_id, outcome)
    return updated.model_dump()


@app.get("/api/users/{user_id}/history")
def user_history(user_id: str, period: str = "all"):
    if period not in ("7d", "30d", "all"):
        raise HTTPException(status_code=400, detail="period must be '7d', '30d', or 'all'.")
    records = drs.get_user_history(decision_records_collection, user_id, period)
    return {"decision_records": [r.model_dump() for r in records]}


@app.get("/api/users/{user_id}/adherence")
def user_adherence(user_id: str):
    return drs.get_user_adherence(decision_records_collection, user_id).model_dump()


@app.get("/api/ml/training-dataset")
def training_dataset():
    return {"dataset": drs.export_training_dataset(decision_records_collection, outcome_records_collection)}


# ── Anti-Ghosting / Adherence Intelligence Endpoints ─────────────

@app.get("/api/users/{user_id}/streaks")
def user_streaks(user_id: str):
    try:
        records = drs.get_user_history(decision_records_collection, user_id)
        return ags.calculate_streak(records).model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/users/{user_id}/trends")
def user_trends(user_id: str):
    try:
        records = drs.get_user_history(decision_records_collection, user_id)
        return ags.generate_weekly_trends(records).model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/users/{user_id}/insights")
def user_insights(user_id: str):
    try:
        records  = drs.get_user_history(decision_records_collection, user_id)
        adherence = drs.get_user_adherence(decision_records_collection, user_id)
        return ags.generate_adherence_insights(records, adherence).model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/users/{user_id}/dashboard")
def user_dashboard(user_id: str):
    try:
        records  = drs.get_user_history(decision_records_collection, user_id)
        adherence = drs.get_user_adherence(decision_records_collection, user_id)
        return ags.generate_dashboard(records, adherence).model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/users/{user_id}/adaptive-recommendation")
def user_adaptive_recommendation(
    user_id: str,
    current_duration: int = 45,
    current_intensity: str = "moderate",
):
    try:
        records  = drs.get_user_history(decision_records_collection, user_id)
        adherence = drs.get_user_adherence(decision_records_collection, user_id)
        return ags.generate_adaptive_recommendation(
            records, adherence, current_duration, current_intensity
        ).model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Preference Engine Request Models ──────────────────────────────

class WorkoutFeedbackInput(BaseModel):
    user_id: str
    workout_type: str
    score: int = Field(..., ge=-1, le=1)
    reason: Optional[str] = None
    coaching_style: Optional[str] = None
    date: Optional[str] = None


class MealFeedbackInput(BaseModel):
    user_id: str
    meal_id: str
    meal_name: Optional[str] = None
    provider: Optional[str] = None
    category: Optional[str] = None
    score: int = Field(..., ge=-1, le=1)
    reason: Optional[str] = None
    date: Optional[str] = None


# ── Preference Engine Endpoints ────────────────────────────────────

@app.get("/api/users/{user_id}/preferences")
def user_preferences(user_id: str):
    try:
        records       = drs.get_user_history(decision_records_collection, user_id)
        wo_feedbacks  = prefe.get_workout_feedbacks(user_feedback_collection, user_id)
        meal_feedbacks = prefe.get_meal_feedbacks(user_feedback_collection, user_id)
        profile       = prefe.compute_preference_profile(user_id, records, wo_feedbacks, meal_feedbacks)
        return profile.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/users/{user_id}/preference-insights")
def user_preference_insights(user_id: str):
    try:
        records        = drs.get_user_history(decision_records_collection, user_id)
        wo_feedbacks   = prefe.get_workout_feedbacks(user_feedback_collection, user_id)
        meal_feedbacks = prefe.get_meal_feedbacks(user_feedback_collection, user_id)
        profile        = prefe.compute_preference_profile(user_id, records, wo_feedbacks, meal_feedbacks)
        return {
            "confidence_level": profile.confidence_level,
            "total_decisions_analyzed": profile.total_decisions_analyzed,
            "preferred_workout_types": profile.preferred_workout_types,
            "disliked_workout_types": profile.disliked_workout_types,
            "preferred_workout_time": profile.preferred_workout_time,
            "preferred_duration_bucket": profile.preferred_duration_bucket,
            "preferred_delivery_location": profile.preferred_delivery_location,
            "preferred_meal_categories": profile.preferred_meal_categories,
            "preferred_coaching_style": profile.preferred_coaching_style,
            "preference_insights": profile.preference_insights,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/users/{user_id}/feedback/workout")
def workout_feedback(user_id: str, inp: WorkoutFeedbackInput):
    if inp.score not in (-1, 1):
        raise HTTPException(status_code=400, detail="score must be 1 (positive) or -1 (negative).")
    feedback = prefe.WorkoutFeedback(
        user_id=user_id,
        workout_type=inp.workout_type,
        score=inp.score,
        reason=inp.reason,
        coaching_style=inp.coaching_style,
        date=inp.date or datetime.now(timezone.utc).date().isoformat(),
    )
    fid = prefe.save_workout_feedback(user_feedback_collection, feedback)
    return {"feedback_id": fid, "status": "recorded"}


@app.post("/api/users/{user_id}/feedback/meal")
def meal_feedback(user_id: str, inp: MealFeedbackInput):
    if inp.score not in (-1, 1):
        raise HTTPException(status_code=400, detail="score must be 1 (positive) or -1 (negative).")
    feedback = prefe.MealFeedback(
        user_id=user_id,
        meal_id=inp.meal_id,
        meal_name=inp.meal_name,
        provider=inp.provider,
        category=inp.category,
        score=inp.score,
        reason=inp.reason,
        date=inp.date or datetime.now(timezone.utc).date().isoformat(),
    )
    fid = prefe.save_meal_feedback(user_feedback_collection, feedback)
    return {"feedback_id": fid, "status": "recorded"}


@app.post("/api/users/{user_id}/preferences/recompute")
def preferences_recompute(user_id: str):
    """Forces a fresh recomputation of the preference profile for this user."""
    try:
        records        = drs.get_user_history(decision_records_collection, user_id)
        wo_feedbacks   = prefe.get_workout_feedbacks(user_feedback_collection, user_id)
        meal_feedbacks = prefe.get_meal_feedbacks(user_feedback_collection, user_id)
        profile        = prefe.compute_preference_profile(user_id, records, wo_feedbacks, meal_feedbacks)
        return {
            "status": "recomputed",
            "user_id": user_id,
            "confidence_level": profile.confidence_level,
            "preferred_workout_types": profile.preferred_workout_types,
            "disliked_workout_types": profile.disliked_workout_types,
            "generated_at": profile.generated_at,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Personal Learning Endpoints ───────────────────────────────────

@app.get("/api/users/{user_id}/learning-profile")
def learning_profile(user_id: str):
    try:
        records  = drs.get_user_history(decision_records_collection, user_id)
        outcomes = ots.get_user_outcomes(outcome_records_collection, user_id)
        profile  = ple.analyze_learning_profile(records, outcomes, user_id)
        return profile.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/users/{user_id}/learning-insights")
def learning_insights(user_id: str):
    try:
        records  = drs.get_user_history(decision_records_collection, user_id)
        outcomes = ots.get_user_outcomes(outcome_records_collection, user_id)
        profile  = ple.analyze_learning_profile(records, outcomes, user_id)
        return ple.get_learning_insights_view(profile).model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/users/{user_id}/learning/recompute")
def learning_recompute(user_id: str):
    """Forces a fresh recomputation of the learning profile for this user."""
    try:
        records  = drs.get_user_history(decision_records_collection, user_id)
        outcomes = ots.get_user_outcomes(outcome_records_collection, user_id)
        profile  = ple.analyze_learning_profile(records, outcomes, user_id)
        return {
            "status": "recomputed",
            "user_id": user_id,
            "total_days_analyzed": profile.total_days_analyzed,
            "confidence_level": profile.confidence_level,
            "patterns_found": len(profile.learned_patterns),
            "generated_at": profile.generated_at,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Outcome Tracking Endpoints ────────────────────────────────────

@app.post("/api/outcomes/daily")
def daily_outcome(inp: DailyOutcomeInput):
    daily = ots.DailyOutcomes(
        mood=inp.mood,
        energy=inp.energy,
        stress=inp.stress,
        sleep_hours=inp.sleep_hours,
        notes=inp.notes,
    )
    record = ots.save_daily_outcome(outcome_records_collection, inp.user_id, daily, inp.date)
    return record.model_dump()


@app.post("/api/outcomes/weekly")
def weekly_outcome(inp: WeeklyOutcomeInput):
    weekly = ots.WeeklyOutcomes(
        weight_kg=inp.weight_kg,
        waist_cm=inp.waist_cm,
        body_fat_percentage=inp.body_fat_percentage,
    )
    record = ots.save_weekly_outcome(outcome_records_collection, inp.user_id, weekly, inp.date)
    return record.model_dump()


@app.get("/api/users/{user_id}/outcome-trends")
def outcome_trends(user_id: str):
    try:
        return ots.calculate_outcome_trends(outcome_records_collection, user_id).model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/users/{user_id}/outcome-insights")
def outcome_insights(user_id: str):
    try:
        return ots.generate_outcome_insights(outcome_records_collection, user_id).model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/users/{user_id}/decision-effectiveness")
def decision_effectiveness(user_id: str):
    try:
        return ots.evaluate_decision_effectiveness(
            outcome_records_collection, decision_records_collection, user_id
        ).model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/order")
async def place_order(order: OrderRequest, current_user: dict = Depends(get_current_user)):
    try:
        result = confirm_weekly_order(order.meal_ids)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    order_doc = {
        "order_id": result.order_id,
        "user_name": order.user_name,
        "order_type": result.order_type,
        "items": [i.model_dump() for i in result.items],
        "total_price_eur": result.total_price_eur,
        "status": result.status,
        "created_at": datetime.utcnow().isoformat(),
        "user_email": current_user["email"],
    }
    try:
        orders_collection.insert_one(order_doc)
    except Exception as e:
        print(f"MongoDB Fehler beim Speichern der Bestellung: {e}")

    return {
        "status": "ok",
        "order_id": result.order_id,
        "ordered_meals": [i.model_dump() for i in result.items],
        "total_price_eur": result.total_price_eur,
    }


@app.post("/api/orders/daily-delivery")
async def place_daily_delivery(
    req: DailyDeliveryRequest,
    current_user: dict = Depends(get_current_user),
):
    meal = get_meal_by_id(req.meal_id)
    if meal is None:
        raise HTTPException(status_code=400, detail=f"Unbekannte Mahlzeit: {req.meal_id}")

    result = confirm_daily_delivery(
        meal_id=req.meal_id,
        meal_slot=req.meal_slot,
        delivery_location=req.delivery_location,
        scheduled_time=req.scheduled_time,
    )

    order_doc = {
        "order_id": result.order_id,
        "order_type": result.order_type,
        "meal_slot": req.meal_slot,
        "items": [i.model_dump() for i in result.items],
        "delivery_location": result.delivery_location,
        "scheduled_time": result.scheduled_time,
        "total_price_eur": result.total_price_eur,
        "status": result.status,
        "created_at": datetime.utcnow().isoformat(),
        "user_email": current_user["email"],
    }
    try:
        orders_collection.insert_one(order_doc)
    except Exception as e:
        print(f"MongoDB Fehler beim Speichern der Tageslieferung: {e}")

    return result.model_dump()


# ── Workout Session Endpoints ─────────────────────────────────────

@app.post("/api/workouts/start")
def workout_start(req: WorkoutStartRequest):
    session = wss.start_session(req.workout_id, req.workout_name, req.total_sets)
    return session.model_dump()


@app.post("/api/workouts/progress")
def workout_progress(req: WorkoutProgressRequest):
    try:
        session = wss.record_progress(req.session_id, req.exercise_name, req.sets_completed)
        return session.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/workouts/complete")
def workout_complete(req: WorkoutCompleteRequest):
    # Handle 'local' or unknown session_id (frontend fallback when start failed)
    existing = wss.get_session(req.session_id)
    if req.session_id == "local" or existing is None:
        return {
            "session_id": req.session_id,
            "status": "completed",
            "duration_seconds": req.duration_seconds,
            "calories_estimate": wss.estimate_calories(req.intensity, req.duration_seconds),
            "completed_exercises": req.completed_exercises or [],
            "completed_sets": req.completed_sets or 0,
        }
    try:
        session = wss.complete_session(
            req.session_id,
            req.duration_seconds,
            req.intensity,
            req.completed_exercises,
            req.completed_sets,
        )
        return session.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))