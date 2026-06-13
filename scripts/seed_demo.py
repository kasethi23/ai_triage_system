#!/usr/bin/env python3
"""Run the full call-triage pipeline on a local audio file.

Simulates what happens after Twilio's /voice/recording webhook fires:
downloads -> transcribes -> classifies -> stores a Call row. Useful for
testing transcription + classification without placing a real call.

The resulting row is written to the same sqlite database the FastAPI app
uses, so it will immediately show up in `GET /calls`. Note: the live SSE
stream (`GET /calls/stream`) will NOT show this event, since this script
runs in a separate process from the server's in-memory pub/sub.

Usage:
    python scripts/seed_demo.py path/to/recording.wav --from-number "+15555550123"
"""

import argparse
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal, init_db  # noqa: E402
from app.services.storage import call_to_dict, process_call_recording  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio_file", type=Path, help="Path to a local audio file")
    parser.add_argument(
        "--from-number",
        default="+15555550123",
        help="Fake caller phone number (default: +15555550123)",
    )
    parser.add_argument(
        "--call-sid",
        default=None,
        help="Fake Twilio CallSid (random if omitted)",
    )
    args = parser.parse_args()

    if not args.audio_file.exists():
        sys.exit(f"Audio file not found: {args.audio_file}")

    call_sid = args.call_sid or f"DEMO{uuid.uuid4().hex[:24].upper()}"
    extension = args.audio_file.suffix.lstrip(".") or "wav"
    audio_bytes = args.audio_file.read_bytes()

    init_db()
    db = SessionLocal()
    try:
        print(f"Processing {args.audio_file} as call_sid={call_sid} from={args.from_number}...")
        call = process_call_recording(db, audio_bytes, call_sid, args.from_number, extension)
    finally:
        db.close()

    print("\nStored call:")
    print(json.dumps(call_to_dict(call), indent=2))


if __name__ == "__main__":
    main()
