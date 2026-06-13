import json

from openai import OpenAI

from app.config import OPENAI_API_KEY, OPENAI_CLASSIFICATION_MODEL

_client = OpenAI(api_key=OPENAI_API_KEY)

_SYSTEM_PROMPT = (
    "You are a clinical call triage assistant. You receive a transcript of a "
    "voicemail left by a clinician or staff member for a physician, recorded "
    "in SBAR format (Situation, Background, Assessment, Recommendation). "
    "Classify the call so it can be triaged correctly."
)

_RESPONSE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "call_classification",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "urgency": {
                    "type": "string",
                    "enum": ["urgent", "routine", "informational"],
                },
                "severity": {
                    "type": "string",
                    "description": (
                        "CTAS-style 4-tier severity for the physician triage queue. "
                        "'severe' = life/limb-threatening, needs attention now. "
                        "'emergent' = serious, needs attention soon. "
                        "'semi-urgent' = needs attention but can wait. "
                        "'non-urgent' = informational / routine, no urgent action needed."
                    ),
                    "enum": ["severe", "emergent", "semi-urgent", "non-urgent"],
                },
                "request_type": {
                    "type": "string",
                    "enum": [
                        "medication",
                        "lab_result",
                        "patient_status",
                        "consult",
                        "scheduling",
                        "other",
                    ],
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
                "urgency",
                "severity",
                "request_type",
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

    Returns the parsed classification dict (also containing the raw fields
    needed for storage).
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

    return result
