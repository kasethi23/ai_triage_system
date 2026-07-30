import json
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import AUDIO_STORAGE_DIR
from app.models import Call
from app.services.classification import classify_transcript
from app.services.push import dispatch_push_for_call
from app.services.transcription import transcribe_audio


def save_audio_file(audio_bytes: bytes, call_sid: str, extension: str = "wav") -> Path:
    """Persist raw audio bytes to disk and return the path."""
    extension = extension.lstrip(".")
    filename = f"{call_sid}_{uuid.uuid4().hex[:8]}.{extension}"
    path = AUDIO_STORAGE_DIR / filename
    with open(path, "wb") as f:
        f.write(audio_bytes)
    return path


def process_call_recording(
    db: Session,
    audio_bytes: bytes,
    call_sid: str,
    from_number: str,
    extension: str = "wav",
) -> Call:
    """Run the full pipeline: save audio, transcribe, classify, persist Call row."""
    audio_path = save_audio_file(audio_bytes, call_sid, extension)

    transcript = transcribe_audio(audio_path)
    classification = classify_transcript(transcript)

    call = Call(
        call_sid=call_sid,
        from_number=from_number,
        audio_path=str(audio_path),
        transcript=transcript,
        urgency=classification["urgency"],
        request_type=classification["request_type"],
        confidence=classification["confidence"],
        summary=classification["summary"],
        suggested_action=classification["suggested_action"],
        raw_classification_json=json.dumps(classification),
        severity=classification["severity"],
        patient_name=classification["patient_name"],
        room=classification["room"],
        caller_name=classification["caller_name"],
        caller_role=classification["caller_role"],
    )

    db.add(call)
    db.commit()
    db.refresh(call)

    # Dispatch APNs push per the policy in app/services/push.py. This runs for
    # both real Twilio calls and seed_demo.py runs. It never raises, so a push
    # failure can never break call ingestion.
    dispatch_push_for_call(db, call_to_dict(call))

    return call


def call_to_dict(call: Call) -> dict:
    return {
        "id": call.id,
        "call_sid": call.call_sid,
        "from_number": call.from_number,
        "received_at": call.received_at.isoformat(),
        "audio_path": call.audio_path,
        "transcript": call.transcript,
        "urgency": call.urgency,
        "request_type": call.request_type,
        "confidence": call.confidence,
        "summary": call.summary,
        "suggested_action": call.suggested_action,
        "raw_classification_json": call.raw_classification_json,
        "severity": call.severity,
        "patient_name": call.patient_name,
        "room": call.room,
        "caller_name": call.caller_name,
        "caller_role": call.caller_role,
        "resolved": call.resolved,
    }
