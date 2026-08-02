import asyncio
import logging

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import Response
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import Gather, VoiceResponse

from app import config
from app.config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN
from app.database import SessionLocal
from app.services.storage import call_to_dict, process_call_recording
from app.sse import broker

logger = logging.getLogger(__name__)

_warned_no_twilio_token = False


def _public_url(request: Request) -> str:
    """Reconstruct the externally-visible URL Twilio signed against.

    Behind Railway's proxy the request scheme/host are the internal ones, but
    Twilio signs the public https URL. Honor the forwarded headers when present.
    """
    proto = request.headers.get("x-forwarded-proto")
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if proto and host:
        return f"{proto}://{host}{request.url.path}"
    return str(request.url)


async def validate_twilio_signature(request: Request) -> None:
    """Validate the X-Twilio-Signature header on Twilio webhook requests.

    Mirrors the API auth policy: if TWILIO_AUTH_TOKEN is unset we allow in local
    dev (loud warning) but never in production.
    """
    global _warned_no_twilio_token
    if not TWILIO_AUTH_TOKEN:
        if config.IS_PRODUCTION:
            logger.error("TWILIO_AUTH_TOKEN unset in production — refusing webhook.")
            raise HTTPException(status_code=500, detail="Twilio auth is misconfigured.")
        if not _warned_no_twilio_token:
            logger.warning(
                "TWILIO_AUTH_TOKEN is not set — Twilio signature validation is "
                "DISABLED. Allowed for local dev only."
            )
            _warned_no_twilio_token = True
        return

    validator = RequestValidator(TWILIO_AUTH_TOKEN)
    signature = request.headers.get("X-Twilio-Signature", "")
    form = await request.form()
    params = {key: value for key, value in form.items()}
    if not validator.validate(_public_url(request), params, signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")


router = APIRouter(
    prefix="/voice",
    tags=["voice"],
    dependencies=[Depends(validate_twilio_signature)],
)

# Structured intake, Option B (privacy P5): the bed/room is captured by KEYPAD,
# so it never becomes audio, never reaches Whisper, and never lands in a
# transcript — and it is exact (Whisper mangles spoken "bed 512"). The rest is a
# single natural voicemail; the name in it is handled by redaction (P6).
ROOM_PROMPT = (
    "Using your keypad, enter the patient's bed or room number, then press pound. "
    "If there is no room number, or this is an emergency, press star to skip."
)
NARRATIVE_PROMPT = (
    "Now leave your message for the physician. Include your name, your role, "
    "the patient's name, what's going on, and what you need. Recording stops "
    "automatically after ninety seconds."
)


@router.post("/incoming")
async def incoming_call() -> Response:
    """Twilio webhook for an incoming call. Step 1: capture the room by keypad."""
    response = VoiceResponse()
    gather = Gather(
        num_digits=6,
        finish_on_key="#",
        action="/voice/narrative",
        method="POST",
        timeout=8,
    )
    gather.say(ROOM_PROMPT)
    response.append(gather)
    # If the caller presses nothing (or times out), fall through to the message.
    response.redirect("/voice/narrative", method="POST")
    return Response(content=str(response), media_type="application/xml")


@router.post("/narrative")
async def narrative(Digits: str = Form("")) -> Response:
    """Step 2: record the single narrative voicemail. The keypad room (if any) is
    carried on the recording callback URL so it never enters the audio."""
    room = "" if Digits in ("", "*") else Digits
    response = VoiceResponse()
    response.say(NARRATIVE_PROMPT)
    response.record(
        action=f"/voice/recording?room={room}",
        method="POST",
        max_length=90,
        play_beep=True,
        trim="trim-silence",
    )
    response.hangup()
    return Response(content=str(response), media_type="application/xml")


@router.post("/recording")
async def recording_complete(
    request: Request,
    CallSid: str = Form(...),
    From: str = Form(...),
    RecordingUrl: str = Form(...),
    RecordingSid: str = Form(""),
) -> Response:
    """Twilio webhook fired once a recording is complete.

    Downloads the audio, runs it through the transcription + classification
    pipeline (with the keypad room as a known identifier), stores the Call,
    broadcasts an SSE event, and deletes Twilio's retained copy (P8)."""
    room = request.query_params.get("room", "")
    audio_bytes, extension = await _download_recording(RecordingUrl)

    db = SessionLocal()
    try:
        call = await asyncio.to_thread(
            process_call_recording, db, audio_bytes, CallSid, From, extension, "voicemail", room
        )
    finally:
        db.close()

    await broker.publish(call_to_dict(call))
    # P8: remove Twilio's own retained copy so the audio does not sit at rest on
    # a third party. Deleting our downloaded copy alone does not close that gap.
    await _delete_twilio_recording(RecordingSid)

    response = VoiceResponse()
    response.hangup()
    return Response(content=str(response), media_type="application/xml")


async def _delete_twilio_recording(recording_sid: str) -> None:
    """Delete a recording from Twilio's storage via the REST API (privacy P8).

    No-op when retention is on or credentials/SID are missing. Never raises —
    a delete failure must not break the webhook response to Twilio."""
    if not recording_sid or config.RETAIN_AUDIO:
        return
    if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN):
        return
    url = (
        f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}"
        f"/Recordings/{recording_sid}.json"
    )
    try:
        async with httpx.AsyncClient() as client:
            await client.delete(url, auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN), timeout=30)
    except Exception:  # noqa: BLE001 — best-effort cleanup
        logger.warning("Failed to delete Twilio recording %s", recording_sid)


async def _download_recording(recording_url: str) -> tuple[bytes, str]:
    """Download a recording from Twilio as a WAV file, authenticated with
    the account's Twilio credentials."""
    url = recording_url
    if not url.endswith(".wav"):
        url = f"{url}.wav"

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url,
            auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
            follow_redirects=True,
            timeout=60,
        )
        resp.raise_for_status()

    return resp.content, "wav"
