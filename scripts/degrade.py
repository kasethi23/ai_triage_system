#!/usr/bin/env python3
"""Task 7 — degrade a share of the corpus so it resembles real Whisper output.

A clean-only corpus overstates accuracy. This applies one of four transforms to
~degrade_fraction of records (default 30%, grid.yaml), appending the transform
name to `degradations[]` and preserving the clean text in
`pre_degradation_transcript` where the text is materially changed.

Rule-based and deterministic under the grid seed. Never changes
`assigned_severity`. The one exception is truncation, which sets
`assigned_insufficient_detail = true` and leaves the underlying severity as the
pre-degradation value.

Usage:
    python scripts/degrade.py                 # in place on data/generated/raw.jsonl
    python scripts/degrade.py --in x.jsonl --out y.jsonl
"""
from __future__ import annotations

import argparse
import random
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus_utils import GRID_PATH, PHYSICIAN_PLACEHOLDER, RAW_PATH, read_jsonl, write_jsonl  # noqa: E402

# Homophone substitutions on EP drug/device vocabulary (spec Task 7).
_HOMOPHONES = {
    "amiodarone": "amiodarine",
    "apixaban": "epixaban",
    "flecainide": "flecanide",
    "cardioversion": "cardio version",
    "rivaroxaban": "rivaroxiban",
    "dabigatran": "dabigatrin",
    "defibrillator": "defibrilator",
    "tachycardia": "tachycardic ya",
}

_DISFLUENCIES = ["um", "uh", "sorry", "let me start over"]


def _asr_errors(rng: random.Random, text: str) -> str:
    # 1) homophone substitution (case-insensitive, preserve nothing fancy)
    for correct, wrong in _HOMOPHONES.items():
        text = re.sub(rf"\b{re.escape(correct)}\b", wrong, text, flags=re.IGNORECASE)
    # 2) numeric corruption: drop a trailing digit, or cut "X over Y" to "X over"
    text = re.sub(r"\b(\d+)\s+over\s+\d+\b", r"\1 over", text, count=1)
    def _drop_digit(m: re.Match) -> str:
        d = m.group(0)
        return d[:-1] if len(d) >= 3 and rng.random() < 0.5 else d
    text = re.sub(r"\b\d{2,3}\b", _drop_digit, text, count=2)
    # 3) disfluencies: inject a couple at word boundaries
    words = text.split()
    if words:
        for _ in range(rng.randint(1, 2)):
            pos = rng.randrange(len(words) + 1)
            words.insert(pos, rng.choice(_DISFLUENCIES))
    return " ".join(words)


def _sbar_removal(text: str) -> str:
    # Keep only the leading "situation" sentence(s); drop background/recommendation.
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    if len(sentences) <= 1:
        return text
    keep = 1 if len(sentences) >= 3 else len(sentences) - 1
    return " ".join(sentences[:keep]).strip()


def _tone_distractor(rng: random.Random, text: str, severity: str) -> str:
    if severity in ("routine", "fyi"):
        # urgent register on a routine issue
        prefix = rng.choice(
            ["I need you right now — ", "This is really urgent, please — ", "Emergency, "]
        )
        return prefix + text
    # calm, apologetic language on a critical/urgent issue (scenario 02)
    prefix = rng.choice(
        [
            "So sorry to bother you, this is probably nothing, but ",
            "No rush at all, whenever you get a sec — ",
            "Apologies for calling, hate to wake you, but ",
        ]
    )
    return prefix + text[0].lower() + text[1:] if text else prefix


def _truncate(rng: random.Random, record: dict) -> str:
    role = record.get("generation_cell", {}).get("caller_role", "nurse")
    templates = [
        f"{PHYSICIAN_PLACEHOLDER}, it's the {role}, can you call me back when you get this.",
        f"Hi {PHYSICIAN_PLACEHOLDER}, call me about bed {rng.randint(1, 12)} when you get a chance.",
        f"{PHYSICIAN_PLACEHOLDER}, need to talk to you about a patient, call me back please.",
    ]
    return rng.choice(templates)


def degrade_record(rng: random.Random, record: dict, transform: str) -> None:
    text = record.get("transcript", "")
    if not text:
        return
    if transform == "truncation":
        record["pre_degradation_transcript"] = text
        record["transcript"] = _truncate(rng, record)
        record["assigned_insufficient_detail"] = True
    elif transform == "asr_errors":
        record["pre_degradation_transcript"] = text
        record["transcript"] = _asr_errors(rng, text)
    elif transform == "sbar_removal":
        new = _sbar_removal(text)
        if new != text:
            record["pre_degradation_transcript"] = text
            record["transcript"] = new
    elif transform == "tone_distractor":
        record["pre_degradation_transcript"] = text
        record["transcript"] = _tone_distractor(rng, text, record["assigned_severity"])
    record.setdefault("degradations", []).append(transform)


_TRANSFORMS = ["truncation", "asr_errors", "sbar_removal", "tone_distractor"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="inp", default=str(RAW_PATH))
    ap.add_argument("--out", default=None, help="Default: overwrite input in place")
    ap.add_argument("--fraction", type=float, default=None, help="Override grid degrade_fraction")
    args = ap.parse_args()

    grid = yaml.safe_load(open(GRID_PATH, encoding="utf-8"))
    fraction = args.fraction if args.fraction is not None else grid.get("degrade_fraction", 0.30)
    rng = random.Random(grid["seed"] + 7)

    records = read_jsonl(args.inp)
    # Only degrade records that already have a transcript and aren't already degraded.
    eligible = [r for r in records if r.get("transcript") and not r.get("degradations")]
    n_target = round(fraction * len(records))
    chosen = rng.sample(eligible, min(n_target, len(eligible)))

    # Spread transforms roughly evenly across the chosen set.
    for i, rec in enumerate(chosen):
        transform = _TRANSFORMS[i % len(_TRANSFORMS)]
        degrade_record(rng, rec, transform)

    out = args.out or args.inp
    write_jsonl(out, records)

    from collections import Counter

    applied = Counter(t for r in records for t in r.get("degradations", []))
    print(f"Degraded {len(chosen)}/{len(records)} records ({len(chosen) / max(len(records),1):.0%}).")
    print("transforms:", dict(applied))
    print("insufficient_detail set by truncation:",
          sum(1 for r in records if r.get("assigned_insufficient_detail") and "truncation" in r.get("degradations", [])))
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
