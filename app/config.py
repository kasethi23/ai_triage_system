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

# --- API auth ---------------------------------------------------------------
# Bearer token required on /calls*, /devices*, and the SSE stream. If unset we
# allow unauthenticated access for local dev (with a loud warning), but never
# in production (see app/auth.py).
API_BEARER_TOKEN = os.getenv("API_BEARER_TOKEN", "")

# --- Storage (env-driven, defaults to the Railway /data volume in prod) ------
DATABASE_URL = os.getenv("DATABASE_URL") or (
    "sqlite:////data/app.db" if IS_PRODUCTION else "sqlite:///./app.db"
)

AUDIO_STORAGE_DIR = Path(
    os.getenv("AUDIO_STORAGE_DIR")
    or ("/data/audio_recordings" if IS_PRODUCTION else "./audio_recordings")
).resolve()
AUDIO_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# --- APNs (Apple Push Notification service) ---------------------------------
# Token-based auth with a .p8 key. The key is passed base64-encoded so it can
# live in a single Railway env var. Sandbox is used for dev builds.
APNS_KEY_BASE64 = os.getenv("APNS_KEY_BASE64", "")
APNS_KEY_ID = os.getenv("APNS_KEY_ID", "")
APNS_TEAM_ID = os.getenv("APNS_TEAM_ID", "")
APNS_BUNDLE_ID = os.getenv("APNS_BUNDLE_ID", "com.clinroute.console")
APNS_USE_SANDBOX = os.getenv("APNS_USE_SANDBOX", "true").lower() in {"1", "true", "yes"}
