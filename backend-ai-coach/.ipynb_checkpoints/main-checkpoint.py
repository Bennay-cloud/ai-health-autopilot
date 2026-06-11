from fastapi import FastAPI, Request # importiert FasAPI zum Erstellung der API, und Request um ankommende Daten von Client zu lesen
from fastapi.middleware.cors import CORSMiddleware # Frontend greift auf Backend zu
from fastapi.staticfiles import StaticFiles
from gpt_service import generate_plan
from db import users_collection
from pdf_generator import generate_pdf
import os

# FastAPI App erstellen
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

# POST Endpoint für das Formular
@app.post("/formdata")
async def formdata(request: Request):
    data = await request.json()
    print("✅ Erhalten vom Frontend:", data)

    # GPT-Antwort generieren
    gpt_response = generate_plan(data)
    print("✅ GPT-Antwort:", gpt_response)

    # PDF erzeugen
    pdf_filename = f"{data.get('name', 'user')}_plan.pdf"
    pdf_path = os.path.join(PDF_DIR, pdf_filename)
    generate_pdf(gpt_response, pdf_path)

    # Daten in MongoDB speichern
    users_collection.insert_one({
        **data,
        "gpt_plan": gpt_response,
        "pdf_filename": pdf_filename
    })

    # Antwort an das Frontend zurückgeben
    return {
        "status": "ok",
        "plan": gpt_response,
        "pdf_url": f"/pdfs/{pdf_filename}"
    }  