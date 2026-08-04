import json
import os
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import AUDIO_STORAGE_DIR, DEIDENTIFY_TRANSCRIPTS, RETAIN_AUDIO
from app.models import Call, CallIdentifiers, CallView
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


def _classify_and_store(
    db: Session,
    transcript: str,
    call_sid: str,
    from_number: str,
    audio_path: str,
    channel: str,
    known_room: str = "",
) -> Call:
    """Shared tail of the pipeline: classify a transcript and persist a Call
    plus its CallIdentifiers row (privacy P4).

    Both the audio path (process_call_recording) and the text path
    (process_call_transcript) funnel through here so classification and
    persistence logic exists in exactly one place.
    """
    # Redaction sits BETWEEN transcription and classification (privacy P6): the
    # classifier only ever sees redacted text, so identifiers never cross to the
    # third-party API. Gated + default off. The token map is stored (P4) and lets
    # the authorised re-identification path (P7) restore the original text.
    text_to_classify = transcript
    token_map: dict = {}
    if DEIDENTIFY_TRANSCRIPTS:
        from app.services.deident import redact

        text_to_classify, token_map = redact(transcript, known={"room": known_room})

    classification = classify_transcript(text_to_classify)

    # The calls row carries NO identifiers — clean by construction (P4).
    call = Call(
        call_sid=call_sid,
        from_number=from_number,
        audio_path=audio_path,
        transcript=text_to_classify,
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
    )
    db.add(call)
    db.commit()
    db.refresh(call)

    # Identifiers go in their own table, joined on call id. With redaction on,
    # the classifier saw tokens ([PERSON_1]…) and echoes them back in its
    # identifier fields — substitute the originals so this table holds the
    # real values the authorised path (P7) is meant to reveal.
    def _restore(value: str) -> str:
        if not (value and token_map):
            return value
        from app.services.deident import reidentify as _reidentify

        return _reidentify(value, token_map)

    db.add(
        CallIdentifiers(
            call_id=call.id,
            patient_name=_restore(classification.get("patient_name", "Unknown")),
            # Room comes from structured intake (keypad, P5) when available,
            # otherwise from the classifier.
            room=known_room or _restore(classification.get("room", "")),
            caller_name=_restore(classification.get("caller_name", "")),
            caller_role=_restore(classification.get("caller_role", "")),
            token_map_json=json.dumps(token_map),
        )
    )
    db.commit()

    return call


def process_call_recording(
    db: Session,
    audio_bytes: bytes,
    call_sid: str,
    from_number: str,
    extension: str = "wav",
    channel: str = "voicemail",
    known_room: str = "",
) -> Call:
    """Run the full audio pipeline: save audio, transcribe, classify, persist, push."""
    audio_path = save_audio_file(audio_bytes, call_sid, extension)
    transcript = transcribe_audio(audio_path)
    call = _classify_and_store(
        db, transcript, call_sid, from_number, str(audio_path), channel, known_room
    )

    # Delete the local recording once transcription has succeeded (privacy P8).
    # Voice is biometric and can't be tokenised, so unless retention is explicitly
    # on, the audio does not sit at rest.
    if not RETAIN_AUDIO:
        try:
            os.remove(audio_path)
        except OSError:
            pass
        call.audio_path = ""
        db.commit()
        db.refresh(call)

    # Dispatch APNs push. Real calls only — the synthetic text path must never
    # push. Never raises, so a push failure can never break call ingestion. Push
    # needs the identifiers, which now live in their own table.
    dispatch_push_for_call(db, {**call_to_dict(call), **identifiers_for(db, call.id)})
    return call


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


def identifiers_for(db: Session, call_id: int) -> dict:
    """Return the identifier fields for a call (empty if none). Not exported by
    call_to_dict — only the authorised re-identification path (P7) surfaces these."""
    ci = db.get(CallIdentifiers, call_id)
    if ci is None:
        return {"patient_name": "", "room": "", "caller_name": "", "caller_role": ""}
    return {
        "patient_name": ci.patient_name,
        "room": ci.room,
        "caller_name": ci.caller_name,
        "caller_role": ci.caller_role,
    }


def reidentify(db: Session, call_id: int, user: str, route: str) -> dict | None:
    """Return the fully re-identified call and log the access (privacy P7).

    Joins CallIdentifiers, substitutes the redaction token map back into the
    transcript, and writes a CallView audit row. Returns None if no such call.
    Callers must already be authenticated (P2)."""
    call = db.get(Call, call_id)
    if call is None:
        return None

    ci = db.get(CallIdentifiers, call_id)
    record = {**call_to_dict(call), **identifiers_for(db, call_id)}
    revealed = False
    if ci is not None:
        token_map = json.loads(ci.token_map_json or "{}")
        if token_map:
            from app.services.deident import reidentify as _restore

            record["transcript"] = _restore(call.transcript, token_map)
        revealed = bool(ci.patient_name or ci.room or ci.caller_name or token_map)

    db.add(
        CallView(call_id=call_id, user=user, revealed_identifiers=revealed, route=route)
    )
    db.commit()
    return record


def call_to_dict(call: Call) -> dict:
    """Redacted-by-construction view of a call — NO identifiers (privacy P4).

    The physician sees identifiers only through the authorised, logged
    re-identification path (P7)."""
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
        "resolved": call.resolved,
    }
