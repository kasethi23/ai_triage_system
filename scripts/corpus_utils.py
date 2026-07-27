"""Shared helpers for the synthetic-corpus scripts (Tasks 5-11).

Kept dependency-light (stdlib + PyYAML) so the non-LLM scripts — leakage
checks, splits, agreement — do not pull in the OpenAI client. The canonical
severity enum lives in app/services/classification.py; it is re-stated here so
these scripts can run without importing the classifier. If the enum changes
there, change it here too.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# Canonical severity enum (mirror of classification.py SEVERITY_TO_URGENCY keys).
SEVERITY_TIERS = ["critical", "urgent", "routine", "fyi"]

REQUEST_TYPES = [
    "medication",
    "lab_result",
    "patient_status",
    "consult",
    "scheduling",
    "operational",
    "other",
]

CHANNELS = ["text", "voicemail", "phone"]

# Placeholder used in every generation prompt so the partner's real attending
# name (which appears throughout the source scenarios) never lands in the repo.
PHYSICIAN_PLACEHOLDER = "Dr. Attending"

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
RUBRIC_PATH = DATA_DIR / "rubric.md"
GRID_PATH = DATA_DIR / "grid.yaml"
COSTS_PATH = DATA_DIR / "costs.yaml"
RAW_PATH = DATA_DIR / "generated" / "raw.jsonl"
SPLITS_DIR = DATA_DIR / "splits"
RATINGS_DIR = DATA_DIR / "ratings"
RESULTS_DIR = DATA_DIR / "results"


# --- JSONL I/O ---------------------------------------------------------------

def read_jsonl(path: str | Path) -> list[dict]:
    path = Path(path)
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def write_jsonl(path: str | Path, records: list[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# --- Text helpers ------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Lowercase word/number tokens. Used by leakage checks and length stats."""
    return _TOKEN_RE.findall((text or "").lower())


# --- Rubric parsing ----------------------------------------------------------

def load_rubric_tier_definitions(path: str | Path = RUBRIC_PATH) -> dict[str, str]:
    """Extract the §1 per-tier definition text from rubric.md.

    Returns {tier: definition_text}. The rubric is the authority for these
    strings; the generator asserts the label in the prompt using them. While
    the rubric still has TODOs, the TODO text is returned verbatim so a run on
    an unfinished rubric is obviously unfinished rather than silently wrong.
    """
    text = Path(path).read_text(encoding="utf-8")
    # Grab the "## 1. Severity tier definitions" section.
    m = re.search(r"^##\s*1\..*?$(.*?)(?=^##\s|\Z)", text, re.MULTILINE | re.DOTALL)
    section = m.group(1) if m else text
    defs: dict[str, str] = {}
    for tier in SEVERITY_TIERS:
        tm = re.search(
            rf"^###\s+{re.escape(tier)}\s*$(.*?)(?=^###\s|\Z)",
            section,
            re.MULTILINE | re.DOTALL,
        )
        defs[tier] = tm.group(1).strip() if tm else ""
    return defs


def load_split(name: str, allow_test: bool = False) -> list[dict]:
    """Load a split by name with a load-time guard (Task 9).

    The `test` split must never be read by generation or prompt-construction
    code. Only evaluation passes allow_test=True. This is the load-time guard the
    spec asks for — a hard failure, not a comment.
    """
    if name == "test" and not allow_test:
        raise RuntimeError(
            "The 'test' split must not be read by generation/prompt code (Task 9). "
            "If this is the evaluator, call load_split('test', allow_test=True)."
        )
    return read_jsonl(SPLITS_DIR / f"{name}.jsonl")


def transcript_hash(transcript: str) -> str:
    """Stable hash of a transcript, for leakage/overlap guards."""
    import hashlib

    norm = " ".join(tokenize(transcript))
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()
