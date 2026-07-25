#!/usr/bin/env python3
"""Task 10 (export) — emit a stratified sample for independent human rating.

Writes a CSV of `id,transcript` ONLY — no labels, no generation cell — plus an
empty `severity` column for the rater to fill in against rubric.md. Stratified
across severity tiers and degradation status. Default 40 records (Amendment I:
lean human rating, 2 raters minimum, ~20 min each).

Each team member copies the sheet to data/ratings/completed_<name>.csv, fills the
`severity` column, and compute_agreement.py ingests them.

Usage:
    python scripts/export_for_rating.py [--n 40] [--in raw.jsonl]
"""
from __future__ import annotations

import argparse
import csv
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus_utils import RATINGS_DIR, RAW_PATH, SEVERITY_TIERS, read_jsonl  # noqa: E402

DEFAULT_N = 40
SEED = 909


def _degraded(r: dict) -> bool:
    return bool(r.get("degradations"))


def stratified_sample(records, n, seed=SEED):
    rng = random.Random(seed)
    strata = defaultdict(list)
    for r in records:
        strata[(r["assigned_severity"], _degraded(r))].append(r)
    # proportional allocation with largest-remainder, at least reflect all strata
    total = len(records)
    picked = []
    for key, rows in sorted(strata.items(), key=lambda kv: str(kv[0])):
        rng.shuffle(rows)
        share = max(1, round(n * len(rows) / total)) if rows else 0
        picked += rows[:share]
    rng.shuffle(picked)
    return picked[:n]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=DEFAULT_N)
    ap.add_argument("--in", dest="inp", default=str(RAW_PATH))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    records = [r for r in read_jsonl(args.inp) if r.get("transcript")]
    if not records:
        sys.exit("No records with transcripts found — generate the corpus first.")

    sample = stratified_sample(records, args.n)
    RATINGS_DIR.mkdir(parents=True, exist_ok=True)
    out = Path(args.out) if args.out else RATINGS_DIR / "rating_sheet.csv"

    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "transcript", "severity"])  # severity left blank for the rater
        for r in sample:
            w.writerow([r["id"], r["transcript"], ""])

    print(f"Wrote {len(sample)} records to {out}")
    print(f"Valid severity labels: {', '.join(SEVERITY_TIERS)}")
    print("Copy to data/ratings/completed_<name>.csv, fill the 'severity' column, "
          "then run compute_agreement.py.")


if __name__ == "__main__":
    main()
