#!/usr/bin/env python3
"""Task 9 — deterministic stratified splits: fewshot / dev / test.

- Stratified by severity AND by degradation status, so test contains a
  representative share of degraded records.
- fewshot ~5%, dev ~25%, test ~70%.
- Deterministic under a fixed seed; the seed is recorded in the output manifest.
- Arrival bursts (Amendment D) are assigned WHOLE to a single split and never to
  fewshot — they go to dev/test only, so the queue-ordering metric has intact
  bursts and no burst is split across dev and test.
- The `test` split must never be read by generation/prompt code — enforced by
  corpus_utils.load_split()'s load-time guard.

Usage:
    python scripts/make_splits.py [--in raw.jsonl] [--seed N]
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus_utils import RAW_PATH, SPLITS_DIR, read_jsonl, write_jsonl  # noqa: E402

FRACTIONS = {"fewshot": 0.05, "dev": 0.25, "test": 0.70}
DEFAULT_SEED = 4242


def _largest_remainder(n: int, fractions: dict[str, float]) -> dict[str, int]:
    raw = {k: n * v for k, v in fractions.items()}
    base = {k: int(x) for k, x in raw.items()}
    remainder = n - sum(base.values())
    # distribute leftover to the largest fractional parts, deterministic order
    order = sorted(fractions, key=lambda k: (-(raw[k] - base[k]), k))
    for i in range(remainder):
        base[order[i % len(order)]] += 1
    return base


def _degraded(record: dict) -> bool:
    return bool(record.get("degradations"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="inp", default=str(RAW_PATH))
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    records = read_jsonl(args.inp)
    assigned: dict[str, str] = {}  # record id -> split

    # 1) Bursts: assign each whole burst to dev or test (never fewshot).
    bursts: dict[str, list[dict]] = defaultdict(list)
    singles: list[dict] = []
    for r in records:
        (bursts[r["burst_id"]].append(r) if r.get("burst_id") else singles.append(r))

    burst_ids = sorted(bursts)
    rng.shuffle(burst_ids)
    dev_test = {"dev": FRACTIONS["dev"], "test": FRACTIONS["test"]}
    tot = sum(dev_test.values())
    dev_test = {k: v / tot for k, v in dev_test.items()}
    burst_alloc = _largest_remainder(len(burst_ids), dev_test)
    idx = 0
    for split, count in burst_alloc.items():
        for _ in range(count):
            for r in bursts[burst_ids[idx]]:
                assigned[r["id"]] = split
            idx += 1

    # 2) Singles: stratify by (severity, degraded) and split each stratum.
    strata: dict[tuple, list[dict]] = defaultdict(list)
    for r in singles:
        strata[(r["assigned_severity"], _degraded(r))].append(r)

    for _, rows in sorted(strata.items(), key=lambda kv: (str(kv[0]))):
        rng.shuffle(rows)
        alloc = _largest_remainder(len(rows), FRACTIONS)
        i = 0
        for split in ("fewshot", "dev", "test"):
            for _ in range(alloc[split]):
                assigned[rows[i]["id"]] = split
                i += 1

    # 3) Write splits, tagging each record with its split.
    out: dict[str, list[dict]] = {"fewshot": [], "dev": [], "test": []}
    for r in records:
        split = assigned[r["id"]]
        r["split"] = split
        out[split].append(r)

    SPLITS_DIR.mkdir(parents=True, exist_ok=True)
    for split, rows in out.items():
        write_jsonl(SPLITS_DIR / f"{split}.jsonl", rows)

    manifest = {
        "seed": args.seed,
        "fractions": FRACTIONS,
        "counts": {s: len(rows) for s, rows in out.items()},
        "total": len(records),
        "bursts_total": len(burst_ids),
        "degraded_per_split": {
            s: sum(1 for r in rows if _degraded(r)) for s, rows in out.items()
        },
        "note": "test.jsonl must never be read by generation/prompt code (Task 9).",
    }
    (SPLITS_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))

    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
