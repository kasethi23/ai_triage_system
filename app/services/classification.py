import json

from openai import OpenAI

from app.config import OPENAI_API_KEY, OPENAI_CLASSIFICATION_MODEL

_client = OpenAI(api_key=OPENAI_API_KEY)

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

_SYSTEM_PROMPT = (
    "You are a clinical call triage assistant for an on-call electrophysiology "
    "(EP) attending. You receive a transcript of a message left by clinical "
    "staff, ideally in SBAR format (Situation, Background, Assessment, "
    "Recommendation), though many real messages lack that structure. Classify "
    "the call so it can be triaged correctly. Judge severity on required "
    "response time and action, not on vocabulary or emotional register."
)

# Severity tier definitions. These mirror data/rubric.md §1 (the team-written
# clinical ground truth) and MUST be kept in sync with it — the rubric is the
# authority, this is a copy embedded in the schema so the model sees the
# definitions. Framed in terms of required response time and action, matching
# the physician's interrupt-now / hold / log decision.
_SEVERITY_DESCRIPTION = (
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

_RESPONSE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "call_classification",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "severity": {
                    "type": "string",
                    "description": _SEVERITY_DESCRIPTION,
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


def classify_transcript(transcript: str) -> dict:
    """Send a transcript to OpenAI for structured triage classification.

    Returns the parsed classification dict. `urgency` is not requested from the
    model; it is derived here from `severity` via SEVERITY_TO_URGENCY so callers
    (e.g. storage.py) can keep reading `classification["urgency"]` unchanged.
    """
    response = _client.chat.completions.create(
        model=OPENAI_CLASSIFICATION_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"Transcript:\n\n{transcript}"},
        ],
        response_format=_RESPONSE_SCHEMA,
    )

    content = response.choices[0].message.content
    result = json.loads(content)

    # Enforce the max-length constraint from the spec (not expressible in JSON schema).
    if len(result.get("summary", "")) > 200:
        result["summary"] = result["summary"][:200]

    # Derive the legacy `urgency` label from `severity` (single source of truth).
    result["urgency"] = SEVERITY_TO_URGENCY.get(result["severity"], "routine")

    return result
