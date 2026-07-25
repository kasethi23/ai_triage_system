import json
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import AUDIO_STORAGE_DIR
from app.models import Call
from app.services.classification import classify_transcript
from app.services.transcription import transcribe_audio


def save_audio_file(audio_bytes: bytes, call_sid: str, extension: str = "wav") -> Path:
    """Persist raw audio bytes to disk and return the path."""
    extension = extension.lstrip(".")
    filename = f"{call_sid}_{uuid.uuid4().hex[:8]}.{extension}"
    path = AUDIO_STORAGE_DIR / filename
    with open(path, "wb") as f:
        f.write(audio_bytes)
    return path


def _classify_and_store(
    db: Session,
    transcript: str,
    call_sid: str,
    from_number: str,
    audio_path: str,
    channel: str,
) -> Call:
    """Shared tail of the pipeline: classify a transcript and persist a Call.

    Both the audio path (process_call_recording) and the text path
    (process_call_transcript) funnel through here so classification and
    persistence logic exists in exactly one place.
    """
    classification = classify_transcript(transcript)

    call = Call(
        call_sid=call_sid,
        from_number=from_number,
        audio_path=audio_path,
        transcript=transcript,
        channel=channel,
        urgency=classification["urgency"],
        request_type=classification["request_type"],
        no_callback=classification["no_callback"],
        insufficient_detail=classification["insufficient_detail"],
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

    return call


def process_call_recording(
    db: Session,
    audio_bytes: bytes,
    call_sid: str,
    from_number: str,
    extension: str = "wav",
    channel: str = "voicemail",
) -> Call:
    """Run the full audio pipeline: save audio, transcribe, classify, persist."""
    audio_path = save_audio_file(audio_bytes, call_sid, extension)
    transcript = transcribe_audio(audio_path)
    return _classify_and_store(
        db, transcript, call_sid, from_number, str(audio_path), channel
    )


def process_call_transcript(
    db: Session,
    transcript: str,
    call_sid: str,
    from_number: str,
    channel: str = "voicemail",
) -> Call:
    """Text-entry path: classify and store a transcript directly.

    Skips transcription and audio persistence (audio_path=""), then follows the
    identical classify-and-store path as process_call_recording. Used for
    generated/synthetic records and any text-channel ingestion.
    """
    return _classify_and_store(db, transcript, call_sid, from_number, "", channel)


def call_to_dict(call: Call) -> dict:
    return {
        "id": call.id,
        "call_sid": call.call_sid,
        "from_number": call.from_number,
        "received_at": call.received_at.isoformat(),
        "audio_path": call.audio_path,
        "transcript": call.transcript,
        "channel": call.channel,
        "urgency": call.urgency,
        "request_type": call.request_type,
        "no_callback": call.no_callback,
        "insufficient_detail": call.insufficient_detail,
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
