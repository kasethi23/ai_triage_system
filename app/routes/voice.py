import asyncio

import httpx
from fastapi import APIRouter, Form
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse

from app.config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN
from app.database import SessionLocal
from app.services.storage import call_to_dict, process_call_recording
from app.sse import broker

router = APIRouter(prefix="/voice", tags=["voice"])

GREETING = (
    "Please leave a message in S B A R format. "
    "State your name, your role, the patient, the situation, "
    "and what you need from the physician. "
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
