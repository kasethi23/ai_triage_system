import asyncio
import logging

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import Response
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import VoiceResponse

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

GREETING = (
    "Please leave a message for the physician. "
    "Include your name, your role, the patient's name, "
    "what's going on, and what you need. "
    "Recording will stop automatically after ninety seconds."
)


@router.post("/incoming")
async def incoming_call() -> Response:
    """Twilio webhook for an incoming call. Greets the caller and records."""
    response = VoiceResponse()
    response.say(GREETING)
    response.record(
        action="/voice/recording",
        method="POST",
        max_length=90,
        play_beep=True,
        trim="trim-silence",
    )
    response.hangup()
    return Response(content=str(response), media_type="application/xml")


@router.post("/recording")
async def recording_complete(
    CallSid: str = Form(...),
    From: str = Form(...),
    RecordingUrl: str = Form(...),
) -> Response:
    """Twilio webhook fired once a recording is complete.

    Downloads the audio, runs it through the transcription + classification
    pipeline, stores the resulting Call row, and broadcasts an SSE event.
    """
    audio_bytes, extension = await _download_recording(RecordingUrl)

    db = SessionLocal()
    try:
        call = await asyncio.to_thread(
            process_call_recording, db, audio_bytes, CallSid, From, extension
        )
    finally:
        db.close()

    await broker.publish(call_to_dict(call))

    response = VoiceResponse()
    response.hangup()
    return Response(content=str(response), media_type="application/xml")


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
