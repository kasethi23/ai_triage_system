import copy
import json
from collections import defaultdict
from pathlib import Path

from openai import OpenAI

from app.config import (
    FEWSHOT_MAX_EXAMPLES,
    OPENAI_API_KEY,
    OPENAI_CLASSIFICATION_MODEL,
    RUNTIME_FEWSHOT_PATH,
    runtime_fewshot_enabled,
)
from app.services import rubric as _rubric

_client = OpenAI(api_key=OPENAI_API_KEY)

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_COSTS_PATH = _DATA_DIR / "costs.yaml"
# The generated fewshot split is built specifically for prompt injection
# (make_splits.py) and is disjoint from the test split by construction.
_SPLIT_FEWSHOT_PATH = _DATA_DIR / "splits" / "fewshot.jsonl"
_SPLIT_FEWSHOT_PER_TIER = 3

# Maps the single LLM-produced severity label onto the legacy `urgency` enum,
# which is kept only for requirements traceability (FR2). The model is no longer
# asked for `urgency` directly; it is derived here so there is exactly one source
# of truth and `severity`/`urgency` can never disagree. Keep this the only place
# the mapping lives.
SEVERITY_TO_URGENCY = {
    "critical": "urgent",
    "urgent": "urgent",
    "routine": "routine",
    "fyi": "informational",
}

_SYSTEM_PROMPT_BASE = (
    "You are a clinical call triage assistant for an on-call electrophysiology "
    "(EP) attending. You receive a transcript of a message left by clinical "
    "staff, ideally in SBAR format (Situation, Background, Assessment, "
    "Recommendation), though many real messages lack that structure. Classify "
    "the call so it can be triaged correctly. Judge severity on required "
    "response time and action, not on vocabulary or emotional register."
)

# Fallback severity description, used ONLY when data/rubric.md is missing or its
# §1 is unfilled. Normally the description is built live from the rubric (see
# _severity_description) so the rubric is the single source of truth.
_SEVERITY_DESCRIPTION_FALLBACK = (
    "Triage severity for the on-call EP physician, judged on required response "
    "time and action, not on the caller's tone or word choice. "
    "'critical' = life- or limb-threatening; the attending must be interrupted "
    "and respond within minutes (e.g. electrical storm, VT/VF, cardiac "
    "tamponade). "
    "'urgent' = serious and time-sensitive; needs the attending's attention "
    "soon (within the hour) but is not an immediate interrupt. "
    "'routine' = a genuine request that can wait hours and be handled in the "
    "normal workflow; no interruption needed. "
    "'fyi' = informational only; no action required from the attending, logged "
    "for awareness."
)

_RESPONSE_SCHEMA_TEMPLATE = {
    "type": "json_schema",
    "json_schema": {
        "name": "call_classification",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "severity": {
                    "type": "string",
                    "description": _SEVERITY_DESCRIPTION_FALLBACK,
                    "enum": ["critical", "urgent", "routine", "fyi"],
                },
                "request_type": {
                    "type": "string",
                    "description": (
                        "The kind of request. 'operational' = time-sensitive but "
                        "non-clinical logistics (e.g. OR room turnover, missing "
                        "consumables, staffing), distinct from 'other'."
                    ),
                    "enum": [
                        "medication",
                        "lab_result",
                        "patient_status",
                        "consult",
                        "scheduling",
                        "operational",
                        "other",
                    ],
                },
                "no_callback": {
                    "type": "boolean",
                    "description": (
                        "True only when the caller explicitly states no response "
                        "or callback is needed (a loop-closing FYI). Distinct from "
                        "low severity: a 'routine' or 'fyi' call may still need a "
                        "reply."
                    ),
                },
                "insufficient_detail": {
                    "type": "boolean",
                    "description": (
                        "True when the transcript lacks the information needed to "
                        "triage at all (e.g. 'call me back about bed 7'). When "
                        "true, still emit a best-guess severity, but this flag "
                        "signals the call must be flagged for review, not acted "
                        "on blindly."
                    ),
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence in this classification, 0 to 1.",
                },
                "summary": {
                    "type": "string",
                    "description": "One-line summary for the physician, max 200 characters.",
                },
                "suggested_action": {
                    "type": "string",
                    "description": "One-line suggested next action for the physician.",
                },
                "patient_name": {
                    "type": "string",
                    "description": "Patient's name as stated in the call, or 'Unknown' if not stated.",
                },
                "room": {
                    "type": "string",
                    "description": "Patient's room/unit as stated in the call, or '' if not stated.",
                },
                "caller_name": {
                    "type": "string",
                    "description": "Caller's name as stated in the call, or 'Unknown' if not stated.",
                },
                "caller_role": {
                    "type": "string",
                    "description": "Caller's role/title (e.g. charge nurse), or '' if not stated.",
                },
            },
            "required": [
                "severity",
                "request_type",
                "no_callback",
                "insufficient_detail",
                "confidence",
                "summary",
                "suggested_action",
                "patient_name",
                "room",
                "caller_name",
                "caller_role",
            ],
            "additionalProperties": False,
        },
    },
}


# --- Rubric-driven prompt assembly ------------------------------------------
# The rubric (data/rubric.md) is the single source of truth. These builders read
# it at call time, so editing the rubric changes what the classifier is told:
# tier definitions (§1), boundary rules (§2.1), signals-not-to-use (§6), and
# anchor examples (§2) all flow into the request.


def _system_prompt() -> str:
    prompt = _SYSTEM_PROMPT_BASE
    signals = _rubric.signals_not_to_use()
    if signals:
        prompt += " Signals that must NOT influence the severity decision: " + signals
    cost = _cost_bias()
    if cost:
        prompt += " " + cost
    return prompt


def _cost_bias() -> str:
    """Communicate the asymmetric cost matrix (data/costs.yaml) to the model, so
    it errs toward higher acuity when genuinely uncertain — the same cost-sensitive
    framing the offline evaluator uses. Empty string if costs are unavailable."""
    try:
        import yaml

        costs = yaml.safe_load(_COSTS_PATH.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001 — best effort; classifier still works without it
        return ""
    missed = costs.get("missed_critical")
    interrupt = costs.get("unnecessary_interrupt")
    if not missed or not interrupt:
        return ""
    ratio = int(round(missed / interrupt))
    return (
        f"Errors are not equally costly: missing a critical call is roughly {ratio}x "
        "as costly as an unnecessary interruption. When you are genuinely uncertain "
        "between two adjacent severity tiers, prefer the higher-acuity tier."
    )


def _severity_description() -> str:
    """Built from rubric §1 tier definitions + §2.1 boundary rules. Falls back to
    the embedded constant only if the rubric is missing/unfilled."""
    if not _rubric.is_usable():
        return _SEVERITY_DESCRIPTION_FALLBACK
    defs = _rubric.tier_definitions()
    parts = [
        "Triage severity for the on-call EP physician, judged on required response "
        "time and action, not on the caller's tone or word choice."
    ]
    for tier in ("critical", "urgent", "routine", "fyi"):
        parts.append(f"'{tier}' = {defs[tier]}")
    boundary = _rubric.boundary_rules()
    if boundary:
        parts.append("Boundary rules — " + boundary)
    return " ".join(parts)


def _response_schema() -> dict:
    schema = copy.deepcopy(_RESPONSE_SCHEMA_TEMPLATE)
    props = schema["json_schema"]["schema"]["properties"]
    props["severity"]["description"] = _severity_description()
    # §3/§4/§5 drive the flag + request_type field descriptions live too, so the
    # whole classification is rubric-controlled (fall back to the template text
    # when a section is empty).
    if _rubric.no_callback_rule():
        props["no_callback"]["description"] = _rubric.no_callback_rule()
    if _rubric.insufficient_detail_rule():
        props["insufficient_detail"]["description"] = _rubric.insufficient_detail_rule()
    if _rubric.request_type_defs():
        props["request_type"]["description"] = _rubric.request_type_defs()
    return schema


def _split_fewshot() -> list[dict]:
    """Inject the generated fewshot split as labelled worked examples. Unlike the
    rubric anchors (all clean), these include degraded/realistic messages — the
    slice the classifier is weakest on. Leakage-safe: disjoint from test by
    construction (make_splits.py)."""
    if not _SPLIT_FEWSHOT_PATH.exists():
        return []
    by_tier: dict[str, list[dict]] = defaultdict(list)
    with open(_SPLIT_FEWSHOT_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rec = json.loads(line)
                by_tier[rec.get("assigned_severity")].append(rec)
    pairs: list[dict] = []
    for tier in ("critical", "urgent", "routine", "fyi"):
        for rec in by_tier.get(tier, [])[:_SPLIT_FEWSHOT_PER_TIER]:
            label = {
                "severity": rec.get("assigned_severity"),
                "request_type": rec.get("assigned_request_type"),
                "no_callback": bool(rec.get("assigned_no_callback", False)),
                "insufficient_detail": bool(rec.get("assigned_insufficient_detail", False)),
            }
            pairs.append({"role": "user", "content": f"Transcript:\n\n{rec.get('transcript', '')}"})
            pairs.append({"role": "assistant", "content": json.dumps(label)})
    if not pairs:
        return []
    return [
        {
            "role": "system",
            "content": "Additional labelled examples, including degraded/realistic messages:",
        }
    ] + pairs


def _rubric_fewshot() -> list[dict]:
    """The rubric's §2 anchor examples as worked examples with their correct
    severity. These are the partner's source scenarios — held separate from the
    test set — so they are leakage-safe."""
    anchors = _rubric.anchor_examples()
    pairs: list[dict] = []
    for tier in ("critical", "urgent", "routine", "fyi"):
        for quote in anchors.get(tier, []):
            pairs.append({"role": "user", "content": f"Transcript:\n\n{quote}"})
            pairs.append({"role": "assistant", "content": json.dumps({"severity": tier})})
    if not pairs:
        return []
    return [
        {
            "role": "system",
            "content": "Reference examples from the rubric, each with its correct severity:",
        }
    ] + pairs


def _load_runtime_fewshot() -> list[dict]:
    """Load the physician-corrected runtime few-shot pool (Task 12).

    Returns [] if disabled or the file is absent. Records are worked examples
    written by scripts/promote_corrections.py, each with `transcript`,
    `corrected_field`, and `corrected_label`.
    """
    if not runtime_fewshot_enabled() or not RUNTIME_FEWSHOT_PATH.exists():
        return []
    examples = []
    with open(RUNTIME_FEWSHOT_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                examples.append(json.loads(line))
    return examples[:FEWSHOT_MAX_EXAMPLES]


def _fewshot_messages() -> list[dict]:
    """Prepend physician-corrected worked examples as prior turns.

    This is how the correction loop closes — through prompt context, not weights.
    Promotion into the pool is human-approved (see promote_corrections.py).
    """
    examples = _load_runtime_fewshot()
    if not examples:
        return []
    msgs = [
        {
            "role": "system",
            "content": (
                "The following are physician-corrected worked examples. Treat "
                "their labels as authoritative when a new transcript is similar."
            ),
        }
    ]
    for ex in examples:
        field = ex.get("corrected_field", "severity")
        label = ex.get("corrected_label", "")
        msgs.append({"role": "user", "content": f"Transcript:\n\n{ex.get('transcript', '')}"})
        msgs.append({"role": "assistant", "content": json.dumps({field: label})})
    return msgs


def classify_transcript(transcript: str) -> dict:
    """Send a transcript to OpenAI for structured triage classification.

    Returns the parsed classification dict. `urgency` is not requested from the
    model; it is derived here from `severity` via SEVERITY_TO_URGENCY so callers
    (e.g. storage.py) can keep reading `classification["urgency"]` unchanged.

    Any physician-corrected examples in the runtime few-shot pool are prepended
    as worked examples (Task 12), unless RUNTIME_FEWSHOT_ENABLED is off.
    """
    messages = [{"role": "system", "content": _system_prompt()}]
    messages.extend(_rubric_fewshot())       # §2 anchor examples (rubric)
    messages.extend(_split_fewshot())        # generated fewshot split (incl. degraded)
    messages.extend(_fewshot_messages())     # physician corrections (Task 12)
    messages.append({"role": "user", "content": f"Transcript:\n\n{transcript}"})

    response = _client.chat.completions.create(
        model=OPENAI_CLASSIFICATION_MODEL,
        messages=messages,
        response_format=_response_schema(),
    )

    content = response.choices[0].message.content
    result = json.loads(content)

    # Enforce the max-length constraint from the spec (not expressible in JSON schema).
    if len(result.get("summary", "")) > 200:
        result["summary"] = result["summary"][:200]

    # Derive the legacy `urgency` label from `severity` (single source of truth).
    result["urgency"] = SEVERITY_TO_URGENCY.get(result["severity"], "routine")

    return result
