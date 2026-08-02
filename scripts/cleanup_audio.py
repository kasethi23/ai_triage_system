#!/usr/bin/env python3
"""Delete stored audio recordings (privacy P8).

Removes files from AUDIO_STORAGE_DIR and clears `audio_path` on every Call, for
databases created before RETAIN_AUDIO=false became the default. Local disk only —
Twilio's retained copies are deleted at ingestion time by voice.py, not here.

Usage:
    python scripts/cleanup_audio.py            # dry run: report what would be deleted
    python scripts/cleanup_audio.py --yes      # actually delete
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import AUDIO_STORAGE_DIR  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402
from app.models import Call  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--yes", action="store_true", help="Actually delete (default: dry run)")
    args = ap.parse_args()

    files = [p for p in Path(AUDIO_STORAGE_DIR).glob("*") if p.is_file()]
    total_bytes = sum(p.stat().st_size for p in files)
    print(f"AUDIO_STORAGE_DIR: {AUDIO_STORAGE_DIR}")
    print(f"{len(files)} audio file(s), {total_bytes / 1e6:.1f} MB")

    init_db()
    db = SessionLocal()
    try:
        with_audio = db.query(Call).filter(Call.audio_path != "").count()
    finally:
        db.close()
    print(f"{with_audio} Call row(s) still reference an audio_path")

    if not args.yes:
        print("\nDry run — pass --yes to delete the files and clear audio_path.")
        return

    for p in files:
        try:
            p.unlink()
        except OSError as e:
            print(f"  could not delete {p}: {e}")
    db = SessionLocal()
    try:
        for call in db.query(Call).filter(Call.audio_path != "").all():
            call.audio_path = ""
        db.commit()
    finally:
        db.close()
    print(f"Deleted {len(files)} file(s) and cleared {with_audio} audio_path(s).")


if __name__ == "__main__":
    main()
