import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_TRANSCRIPTION_MODEL = os.getenv("OPENAI_TRANSCRIPTION_MODEL", "whisper-1")
OPENAI_CLASSIFICATION_MODEL = os.getenv("OPENAI_CLASSIFICATION_MODEL", "gpt-5-mini")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

AUDIO_STORAGE_DIR = Path(os.getenv("AUDIO_STORAGE_DIR", "./audio_recordings")).resolve()
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
