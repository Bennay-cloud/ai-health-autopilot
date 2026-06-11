from openai import OpenAI
import os
from math import isfinite
from dotenv import load_dotenv

from meal_catalog_service import select_weekly_meals, format_for_prompt, MealItem

load_dotenv()
client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)
MODEL = "llama-3.3-70b-versatile"

# ── Nutrition helpers ────────────────────────────────────────────

def _to_float(x, default=0.0):
    try:
        v = float(str(x).replace(",", "."))
        return v if isfinite(v) else default
    except Exception:
        return default

def _g(data: dict, *keys, default=""):
    """Get value from the first matching key."""
    for k in keys:
        if k in data and data[k] not in (None, ""):
            return data[k]
    return default

def estimate_targets(data: dict) -> dict:
    """Mifflin-St Jeor BMR → TDEE → goal-adjusted calorie & macro targets."""
    geschlecht = str(_g(data, "geschlecht", "gender", default="")).lower().strip()
    male = geschlecht.startswith(("m", "mann", "male"))
    alter = int(_to_float(_g(data, "alter", "age", default=30)))
    gewicht = _to_float(_g(data, "gewicht", "weight_kg", default=75))
    groesse = _to_float(_g(data, "groesse", "height_cm", default=175), 175)

    # Mifflin-St Jeor
    if male:
        bmr = 10 * gewicht + 6.25 * groesse - 5 * alter + 5
    else:
        bmr = 10 * gewicht + 6.25 * groesse - 5 * alter - 161

    days = int(_to_float(_g(data, "training_days", default=3)))
    level = str(_g(data, "level", default="")).lower()
    base_factor = 1.2 + min(max(days, 0), 7) * 0.07  # 1.2 .. 1.69
    if "fortgesch" in level or "advanced" in level:
        base_factor += 0.05

    tdee = bmr * base_factor

    ziel = str(_g(data, "ziel", "goal", default="gesund bleiben")).lower()
    if "fett" in ziel:
        target_cal = tdee - 400
    elif "muskel" in ziel:
        target_cal = tdee + 300
    else:
        target_cal = tdee

    if "muskel" in ziel:
        protein_g = 2.0 * gewicht
    elif "fett" in ziel:
        protein_g = 1.8 * gewicht
    else:
        protein_g = 1.6 * gewicht

    fat_g = 0.8 * gewicht
    carbs_g = max((target_cal - (protein_g * 4 + fat_g * 9)) / 4, 0)

    return {
        "calories": round(target_cal),
        "protein_g": round(protein_g),
        "fat_g": round(fat_g),
        "carbs_g": round(carbs_g),
        "bmr": round(bmr),
        "tdee": round(tdee),
    }

def _meal_split(goal: str, snack_pref: str = "beide") -> dict:
    """Goal-aware calorie % split across 5 meals per day."""
    g = (goal or "").lower()
    if "muskel" in g:
        base = dict(breakfast=22, snack_am=12, lunch=28, snack_pm=12, dinner=26)
    elif "fett" in g:
        base = dict(breakfast=23, snack_am=10, lunch=34, snack_pm=13, dinner=20)
    else:
        base = dict(breakfast=22, snack_am=10, lunch=28, snack_pm=10, dinner=30)

    s = (snack_pref or "").lower().strip()
    if s in {"keine", "null", "0", "none"}:
        shift = base["snack_am"] + base["snack_pm"]
        base["snack_am"] = 0
        base["snack_pm"] = 0
        base["breakfast"] += shift * 0.3
        base["lunch"]     += shift * 0.4
        base["dinner"]    += shift * 0.3

    total = sum(base.values()) or 100.0
    return {k: round(v * 100 / total, 2) for k, v in base.items()}

def _macro_split_by_calories(targets: dict, split_pct: dict) -> dict:
    """Distribute calories & macros to each meal proportional to its calorie share."""
    per_meal = {}
    for meal, pct in split_pct.items():
        cals = targets["calories"] * pct / 100.0
        per_meal[meal] = dict(
            calories=round(cals),
            protein_g=round(targets["protein_g"] * pct / 100.0),
            fat_g=round(targets["fat_g"] * pct / 100.0),
            carbs_g=round(targets["carbs_g"] * pct / 100.0),
        )
    return per_meal

def _supplement_reco(goal: str, user_suppl) -> list:
    g = (goal or "").lower()
    have = str(user_suppl).strip().lower() if isinstance(user_suppl, str) else ""
    wants = (user_suppl is True) or have in {"ja", "yes", "y", "1", "true"}

    recos = []
    def add_once(x):
        if x not in recos:
            recos.append(x)

    if wants:
        add_once("Vitamin D3 (1000–2000 IU/Tag)")
        add_once("Omega-3 (1–2 g/Tag)")
        if "muskel" in g:
            add_once("Whey/Protein-Shake (20–30 g Post-Workout)")
            add_once("Kreatin Monohydrat (3–5 g/Tag)")
        elif "fett" in g:
            add_once("Protein-Shake optional (20–25 g)")
    return recos

def _fiber_target(calories: float) -> int:
    """Ballaststoff-Ziel in g/Tag (~14 g je 1000 kcal; Korridor 25–40 g)."""
    if not calories or calories <= 0:
        return 30
    return max(25, min(round(14 * (calories / 1000.0)), 40))

def _progression_plan(goal: str, tdee: float, target_cal: float, weeks: int = 8) -> list:
    """Sanfter wöchentlicher Kalorien-Fahrplan über 8 Wochen."""
    g = (goal or "").lower()
    plan = []
    if "fett" in g:
        for w in range(1, weeks + 1):
            plan.append({"week": w, "calories": max(round(target_cal), round(tdee - 100 * w))})
    elif "muskel" in g:
        for w in range(1, weeks + 1):
            plan.append({"week": w, "calories": min(round(target_cal), round(tdee + 100 * w))})
    else:
        for w in range(1, weeks + 1):
            plan.append({"week": w, "calories": round(tdee)})
    return plan

# ── Server-side rendered intro HTML ─────────────────────────────

def _render_intro(targets: dict, fiber_g: int, week_plan: list, goal: str) -> str:
    """BMR, TDEE, per-meal targets, and 8-week ramp — rendered before the LLM output."""
    g = (goal or "").lower()
    if "fett" in g:
        ramp_note = "Für Fettabbau reduzieren wir behutsam um ~100 kcal pro Woche, damit sich dein Körper ohne Stress anpasst."
    elif "muskel" in g:
        ramp_note = "Für Aufbau steigern wir behutsam um ~100 kcal pro Woche, um sauberen Progress ohne unnötiges Fett zu erzielen."
    else:
        ramp_note = "Für Erhaltung bleiben wir stabil um deinen Gesamtumsatz (TDEE)."

    weeks_html = "".join(
        f"<li><strong>Woche {w['week']}:</strong> {w['calories']} kcal</li>"
        for w in week_plan
    )

    meal_labels = {
        "breakfast": "Frühstück",
        "snack_am":  "Snack (Vormittag)",
        "lunch":     "Mittagessen",
        "snack_pm":  "Snack (Nachmittag)",
        "dinner":    "Abendessen",
    }
    split_pct = _meal_split(goal)
    per_meal = _macro_split_by_calories(targets, split_pct)
    meal_rows = "".join(
        f"<li><strong>{meal_labels[k]}:</strong> "
        f"{v['calories']} kcal | P {v['protein_g']} g | F {v['fat_g']} g | KH {v['carbs_g']} g</li>"
        for k, v in per_meal.items()
    )

    return f"""
<h2>Dein Grundumsatz &amp; tägliche Ziele</h2>
<ul>
  <li><strong>Grundumsatz (BMR):</strong> {targets['bmr']} kcal</li>
  <li><strong>Gesamtumsatz (TDEE):</strong> {targets['tdee']} kcal</li>
</ul>

<h3>Tägliche Zielwerte</h3>
<ul>
  <li><strong>Kalorien:</strong> {targets['calories']} kcal</li>
  <li><strong>Protein:</strong> {targets['protein_g']} g</li>
  <li><strong>Fett:</strong> {targets['fat_g']} g</li>
  <li><strong>Kohlenhydrate:</strong> {targets['carbs_g']} g</li>
  <li><strong>Ballaststoffe:</strong> {fiber_g} g</li>
</ul>

<h3>Mahlzeiten-Zielwerte (pro Tag)</h3>
<ul>
  {meal_rows}
</ul>

<h3>Sanfter Kalorien-Fahrplan (Woche 1–8)</h3>
<p>{ramp_note}</p>
<ul>
  {weeks_html}
</ul>
""".strip()

# ── Main plan generator ──────────────────────────────────────────

def generate_plan(data: dict) -> str:
    # Catalog RAG matching via shared service
    matched_meals = select_weekly_meals(data["ernaehrung"], data["ziel"], limit=6)
    catalog_context = format_for_prompt(matched_meals)

    # Nutrition targets
    targets = estimate_targets(data)
    fiber_g = _fiber_target(targets["calories"])
    week_plan = _progression_plan(data["ziel"], targets["tdee"], targets["calories"], weeks=8)

    # Per-meal breakdown for prompt context
    split_pct = _meal_split(data["ziel"])
    per_meal_targets = _macro_split_by_calories(targets, split_pct)
    meal_labels = {
        "breakfast": "Frühstück",
        "snack_am":  "Snack (Vormittag)",
        "lunch":     "Mittagessen",
        "snack_pm":  "Snack (Nachmittag)",
        "dinner":    "Abendessen",
    }
    per_meal_lines = "\n".join(
        f"  - {meal_labels[k]}: {v['calories']} kcal | P {v['protein_g']}g | F {v['fat_g']}g | KH {v['carbs_g']}g"
        for k, v in per_meal_targets.items()
    )

    # Supplements
    supp_val = data.get("supplements", False)
    supp_list = _supplement_reco(data["ziel"], supp_val)
    if supp_list:
        supp_html = "<ul>" + "".join(f"<li>{s}</li>" for s in supp_list) + "</ul>"
    else:
        supp_html = "<p><em>Keine Supplements gewünscht.</em></p>"

    prompt = f"""
Du bist ein persönlicher AI-Fitness-Coach & Ernährungsberater. Erstelle einen strukturierten HTML-Trainings- und Ernährungsplan.
Gib die Antwort ausschließlich in HTML aus (keine Markdown, kein Plain Text).
Nutze HTML-Elemente: <h2>, <h3>, <ul>, <li>, <strong>, <p>, <em>

🧍 Nutzerprofil:
- Name: {data['name']}
- Geschlecht: {data['geschlecht']}
- Alter: {data['alter']}
- Gewicht: {data['gewicht']} kg
- Ziel: {data['ziel']}
- Ernährungsstil: {data['ernaehrung']}
- Trainingslevel: {data['level']}
- Trainingstage pro Woche: {data['training_days']}x
- Verfügbares Equipment: {data.get('equipment', 'nicht angegeben')}

📊 Berechnete Zielwerte (bereits ermittelt – nutze diese exakt):
- Tägliche Kalorien: {targets['calories']} kcal
- Protein: {targets['protein_g']} g | Fett: {targets['fat_g']} g | Kohlenhydrate: {targets['carbs_g']} g
- Ballaststoffe: {fiber_g} g

Per-Mahlzeit-Zielvorgaben (verteile Makros entsprechend):
{per_meal_lines}

🛒 Verfügbare Partner-Mahlzeiten (bereits auf Diät & Ziel gefiltert):
Baue diese gezielt für Mittagessen und Abendessen ein – nenne Produktname und SKU:
{catalog_context}

---

🎯 Deine Aufgaben:

1. 📆 Wochenübersicht Training
   - Verteile {data['training_days']} Trainingstage sinnvoll auf die Woche
   - Berücksichtige Niveau ({data['level']}) und Ziel ({data['ziel']})
     - Einsteiger: Ganzkörper
     - Fortgeschrittene/Advanced: Split (Push/Pull/Beine oder Oberkörper/Unterkörper)

2. 🏋️ Täglicher Trainingsplan (je Trainingstag)
   - 5–8 Übungen mit Sätzen & Wiederholungen
   - Muskelaufbau: 1. Übung 4 Sätze (15/12/10/8), restliche 3–4 Sätze
   - Fettabbau: mehr Wdh., kürzere Pausen, Cardio integrieren
   - Pre-/Post-Workout Timing angeben

3. 🍽️ Sieben-Tage-Ernährungsplan (WICHTIG — nutze die per-Mahlzeit-Ziele exakt)
   - 5 Mahlzeiten pro Tag: Frühstück, Snack Vormittag, Mittagessen, Snack Nachmittag, Abendessen
   - Zeige je Mahlzeit: Lebensmittel, Portionsgröße, kcal | P | F | KH
   - Mittagessen & Abendessen: empfehle konkret eine Partner-Mahlzeit (Produktname + SKU)
   - Rotiere Proteinquellen, Gemüse, Kohlenhydrate über die Woche (keine identischen Hauptmahlzeiten an zwei aufeinanderfolgenden Tagen)
   - Halte Tageskalorien im Zielbereich ±10 %
   - Achte auf den Ernährungsstil: {data['ernaehrung']}
   - Füge pro Tag eine kurze Rationale hinzu (1–2 Sätze, warum die Auswahl passt)

4. 💊 Supplements
   Nutze folgenden vorbereiteten Block direkt:
   {supp_html}

5. 🛒 Einkaufsliste
   - Kompakte Wocheneinkaufsliste für die selbst gekochten Mahlzeiten (Frühstück, Snacks)

6. 💬 Motivationssatz am Ende

---

Format: Beginne mit <h2>Wochenübersicht</h2>, dann <h2>Trainingsplan</h2>, dann <h2>Ernährungsplan</h2> (7 Tage), dann <h2>Supplemente</h2>, dann <h2>Einkaufsliste</h2>, dann <h2>Motivation</h2>.
Sprich motivierend, direkt und sympathisch – wie ein echter Coach.
""".strip()

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.45,
    )

    llm_html = response.choices[0].message.content or ""

    # Prepend the server-side calculated intro (BMR, TDEE, targets, ramp)
    intro_html = _render_intro(targets, fiber_g, week_plan, data["ziel"])
    return intro_html + "\n" + llm_html
