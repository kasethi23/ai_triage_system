from pathlib import Path

from openai import OpenAI

from app.config import OPENAI_API_KEY, OPENAI_TRANSCRIPTION_MODEL

_client = OpenAI(api_key=OPENAI_API_KEY)


def transcribe_audio(audio_path: Path) -> str:
    """Transcribe an audio file using the OpenAI Whisper API."""
    with open(audio_path, "rb") as audio_file:
        transcription = _client.audio.transcriptions.create(
            model=OPENAI_TRANSCRIPTION_MODEL,
            file=audio_file,
        )
    return transcription.text
