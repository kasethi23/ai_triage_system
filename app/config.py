import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# True when running on Railway (any of its environment markers is present).
# Used to harden defaults: unauthenticated access is never allowed in prod,
# and storage defaults to the mounted /data volume.
RAILWAY_ENVIRONMENT = os.getenv("RAILWAY_ENVIRONMENT", "")
IS_PRODUCTION = bool(RAILWAY_ENVIRONMENT)

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_TRANSCRIPTION_MODEL = os.getenv("OPENAI_TRANSCRIPTION_MODEL", "whisper-1")
OPENAI_CLASSIFICATION_MODEL = os.getenv("OPENAI_CLASSIFICATION_MODEL", "gpt-5-mini")

# --- De-identification (privacy spec P6) ------------------------------------
# When true, transcripts are redacted (app/services/deident.py) BEFORE they are
# sent to the classifier, so identifiers never cross the boundary to OpenAI.
# Default false while the prototype runs on synthetic data; the flag exists so
# the behaviour is demonstrable and testable. Requires presidio-analyzer,
# presidio-anonymizer and a local spaCy model.
DEIDENTIFY_TRANSCRIPTS = os.getenv("DEIDENTIFY_TRANSCRIPTS", "false").strip().lower() in (
    "1",
    "true",
    "yes",
)

# --- Audio retention (privacy spec P8) --------------------------------------
# Voice is biometric and cannot be tokenised, so stored audio is the highest-risk
# artifact. When false (default), the local recording is deleted after a
# successful transcription and Twilio's retained copy is deleted via the REST API.
RETAIN_AUDIO = os.getenv("RETAIN_AUDIO", "false").strip().lower() in ("1", "true", "yes")

# --- API auth ---------------------------------------------------------------
# Bearer token required on /calls*, /devices*, and the SSE stream. If unset we
# allow unauthenticated access for local dev (with a loud warning), but never
# in production (see app/auth.py).
API_BEARER_TOKEN = os.getenv("API_BEARER_TOKEN", "")

# --- CORS (privacy spec P3) -------------------------------------------------
# Allowed browser origins for the console. Comma-separated; defaults to the
# local Vite dev server. Never wildcard — the API serves PHI once real data
# flows, and a wildcard origin with credentials is disallowed by browsers anyway.
FRONTEND_ORIGINS = [
    o.strip()
    for o in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if o.strip()
]

# --- Storage (env-driven, defaults to the Railway /data volume in prod) ------
DATABASE_URL = os.getenv("DATABASE_URL") or (
    "sqlite:////data/app.db" if IS_PRODUCTION else "sqlite:///./app.db"
)

AUDIO_STORAGE_DIR = Path(
    os.getenv("AUDIO_STORAGE_DIR")
    or ("/data/audio_recordings" if IS_PRODUCTION else "./audio_recordings")
).resolve()
AUDIO_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# Correction feedback loop (Task 12). The runtime few-shot pool holds physician-
# corrected worked examples that classify_transcript prepends to the prompt.
# RUNTIME_FEWSHOT_ENABLED is read live (per call) so evaluate.py can measure the
# classifier with and without it.
RUNTIME_FEWSHOT_PATH = Path(
    os.getenv("RUNTIME_FEWSHOT_PATH", str(BASE_DIR / "data" / "runtime_fewshot.jsonl"))
)
FEWSHOT_MAX_EXAMPLES = int(os.getenv("FEWSHOT_MAX_EXAMPLES", "8"))


def runtime_fewshot_enabled() -> bool:
    """Read the toggle live so a run can flip it via env without re-import."""
    return os.getenv("RUNTIME_FEWSHOT_ENABLED", "true").strip().lower() not in (
        "0",
        "false",
        "no",
    )
# --- APNs (Apple Push Notification service) ---------------------------------
# Token-based auth with a .p8 key. The key is passed base64-encoded so it can
# live in a single Railway env var. Sandbox is used for dev builds.
APNS_KEY_BASE64 = os.getenv("APNS_KEY_BASE64", "")
APNS_KEY_ID = os.getenv("APNS_KEY_ID", "")
APNS_TEAM_ID = os.getenv("APNS_TEAM_ID", "")
APNS_BUNDLE_ID = os.getenv("APNS_BUNDLE_ID", "com.clinroute.console")
APNS_USE_SANDBOX = os.getenv("APNS_USE_SANDBOX", "true").lower() in {"1", "true", "yes"}
