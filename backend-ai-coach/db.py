# db.py
from pymongo import MongoClient
import os
from dotenv import load_dotenv

# .env-Datei laden
load_dotenv()

# MongoDB-Verbindungs-URI aus Umgebungsvariable lesen
MONGO_URI = os.getenv("MONGO_URI")

# --- Add this debug line ---
print(f"DEBUG: Attempting to connect with MONGO_URI = '{MONGO_URI}'")
# --------------------------

# Check if MONGO_URI was loaded correctly
if not MONGO_URI:
    raise ValueError("MONGO_URI environment variable not found or is empty. Please check your .env file.")

try:
    # MongoClient initialisieren
    client = MongoClient(MONGO_URI)
    # Optionally: Test connection
    # client.admin.command('ping') # You can uncomment this later to test connection
    print("✅ MongoDB connection successful! (Client initialized)")
except Exception as e:
    print(f"❌ MongoDB connection failed during client initialization: {e}")
    raise # Re-raise the exception to see the error

# Datenbank & Collection auswählen
db = client["ai_fitness_app"]
users_collection = db["users"]
orders_collection = db["orders"]
auth_users_collection = db["auth_users"]
decision_records_collection = db["decision_records"]
outcome_records_collection  = db["outcome_records"]