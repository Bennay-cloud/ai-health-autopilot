from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = "gpt-4o"

def generate_plan(data):
    prompt = f"""
    Du bist ein persönlicher AI-Fitness-Coach & Ernährungsberater. Erstelle einen **individuellen, motivierenden Wochen- & Tagesplan**, abgestimmt auf das Ziel der Person (Muskelaufbau, Fettabbau oder Gesundheit). strukturierten HTML-Trainings- und Ernährungsplan mit folgenden Anforderungen:


    👉 Nutze HTML-Elemente wie: <h2>, <ul>, <li>, <strong>, <p>, <em>, Emojis

    🧍 Nutzerprofil:
    - Geschlecht: {data['geschlecht']}
    - Name: {data['name']}
    - Alter: {data['alter']}
    - Gewicht: {data['gewicht']} kg
    - Ziel: {data['ziel']} (z. B. Muskelaufbau, Fettabbau, gesund bleiben)
    - Ernährungsstil: {data['ernaehrung']}
    - Trainingslevel: {data['level']} (Einsteiger, Fortgeschrittene, Advanced)
    - Trainingstage pro Woche: {data['training_days']}x
    - Verfügbares Equipment: {data['equipment']}
    - Supplement-Wunsch: {data['supplements']}

    ---

    🎯 **Deine Aufgaben**:

    1. 📆 **Wochenübersicht**
    - Verteile die Trainingstage sinnvoll (z. B. Mo, Mi, Fr bei 3x Training)
    - Berücksichtige Niveau & Ziel:  
        - Anfänger: Ganzkörper / Oberkörper-Unterkörper
        - Fortgeschrittene: Push/Pull/Beine oder muskelorientierter Split
        - Muskelaufbau: möglichst gezielt nach Muskelgruppen splitten

    2. 🏋️‍♂️ **Täglicher Trainingsplan (pro Trainingstag)**
    - Wähle 5–8 passende Übungen je Einheit (nach Ziel & Niveau)
    - Für **Muskelaufbau gilt folgende Logik je Muskelgruppe**:
        - 1. Übung = 4 Sätze → 15 (Aufwärmen), 12 (mittel), 10 (schwer), 8 (max)
        - Restliche Übungen: 3–4 Sätze mit variierender Intensität
    - Für Fettabbau: mehr Wiederholungen, kürzere Pausen, Cardio integrieren

    3. 🍽️ **Täglicher Ernährungsplan**
    - Rechne individuellen Kalorienbedarf (mit Aktivitätsfaktor)
    - Verteile Makros (Protein, Fett, Kohlenhydrate) passend zum Ziel
    - Gib 3 Hauptmahlzeiten & 2 Snacks mit Lebensmitteln und Makros an
    - Achte auf Tagesstruktur (z. B. Frühstückszeit, Pre-/Post-Workout Meals)

    4. 💊 **Supplement-Empfehlung** (nur wenn `supplements == True`)
    - Gib gezielte Empfehlungen je nach Ziel:  
        - Muskelaufbau: Whey, Kreatin, Omega-3, etc.  
        - Gesundheit: Magnesium, Vitamin D, etc.

    5. 💬 **Motivationssatz am Ende**
    - Mach Mut & gib Zuversicht
    - Gerne mit Emojis & direkter Sprache

    ---
    6. HTML-Ausgabe soll enthalten:
    1. 📅 <h2>Wochenübersicht</h2>: Trainingsfrequenz und Aufteilung (z. B. Push/Pull/Beine)
    2. 🏋️‍♂️ <h2>Trainingsplan</h2>: 5–8 Übungen je Trainingseinheit mit Sätzen und Wiederholungen
    3. 🥗 <h2>Ernährungsplan</h2>: 3–5 Mahlzeiten inkl. Kalorien, Makronährstoffen
    4. 💊 <h2>Supplemente</h2>: Wenn Supplements gewünscht, gib Empfehlungen mit Mengen
    5. ✅ <h2>Motivationssatz</h2>: Kurzer, positiver Abschlusssatz

    Gib die komplette Antwort ausschließlich in HTML aus.

    ✍️ **Sprich motivierend, direkt & sympathisch – wie ein echter Coach. Verwende Emojis, Zwischenüberschriften & klare Struktur.**
    """

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )

    return response.choices[0].message.content