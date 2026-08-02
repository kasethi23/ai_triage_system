#!/usr/bin/env python3
"""Task 12 — promote physician corrections into the runtime few-shot pool.

Reviews the `corrections` table and promotes SELECTED rows into
data/runtime_fewshot.jsonl, which classify_transcript prepends to the prompt as
worked examples. Promotion is deliberate and human-approved — never automatic —
because a single physician error would otherwise propagate into every subsequent
classification.

Any promoted transcript is thereby disqualified from the evaluation test set;
evaluate.py enforces this with a load-time hash guard.

Usage:
    python scripts/promote_corrections.py --list          # review candidates
    python scripts/promote_corrections.py --ids 3,7,9     # promote specific rows
    python scripts/promote_corrections.py --all --yes     # promote all (confirm)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from corpus_utils import transcript_hash  # noqa: E402


def _load_existing_hashes(path: Path) -> set[str]:
    if not path.exists():
        return set()
    hashes = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                hashes.add(json.loads(line).get("transcript_hash", ""))
    return hashes


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="List correction candidates and exit")
    ap.add_argument("--ids", default=None, help="Comma-separated correction ids to promote")
    ap.add_argument("--all", action="store_true", help="Promote all corrections")
    ap.add_argument("--yes", action="store_true", help="Skip the confirmation prompt for --all")
    args = ap.parse_args()

    from app.config import RUNTIME_FEWSHOT_PATH
    from app.database import SessionLocal, init_db
    from app.models import Correction

    init_db()
    db = SessionLocal()
    try:
        rows = db.query(Correction).order_by(Correction.created_at.desc()).all()

        if args.list or (not args.ids and not args.all):
            print(f"{len(rows)} correction(s) in the pool:")
            for c in rows:
                snippet = (c.transcript or "")[:60].replace("\n", " ")
                print(f"  [{c.id}] {c.corrected_field}: {c.model_label!r} -> "
                      f"{c.corrected_label!r}  | {snippet}...")
            if not args.list:
                print("\nNothing promoted. Pass --ids or --all to promote (human-approved).")
            return

        if args.ids:
            wanted = {int(x) for x in args.ids.split(",") if x.strip()}
            selected = [c for c in rows if c.id in wanted]
        else:  # --all
            if not args.yes:
                resp = input(f"Promote ALL {len(rows)} corrections into the few-shot pool? [y/N] ")
                if resp.strip().lower() != "y":
                    print("Aborted.")
                    return
            selected = rows

        existing = _load_existing_hashes(RUNTIME_FEWSHOT_PATH)
        RUNTIME_FEWSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        promoted = 0
        with open(RUNTIME_FEWSHOT_PATH, "a", encoding="utf-8") as f:
            for c in selected:
                h = transcript_hash(c.transcript or "")
                if h in existing:
                    continue
                record = {
                    "transcript": c.transcript,
                    "corrected_field": c.corrected_field,
                    "corrected_label": c.corrected_label,
                    "source": "correction",
                    "correction_id": c.id,
                    "promoted_at": datetime.now(timezone.utc).isoformat(),
                    "transcript_hash": h,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                existing.add(h)
                promoted += 1

        print(f"Promoted {promoted} correction(s) into {RUNTIME_FEWSHOT_PATH}")
        print("Reminder: these transcripts are now disqualified from the eval test set "
              "(evaluate.py enforces this by hash).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
