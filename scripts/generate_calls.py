#!/usr/bin/env python3
"""Task 6 — label-first synthetic call generator.

For each planned generation cell we ASSERT the severity label in the prompt and
ask the model for a message consistent with it. We never ask a model to label
its own output. Output: data/generated/raw.jsonl with full provenance.

The plan (which cells, how many, burst membership, timestamps) is deterministic
under the grid `seed`. Use --dry-run to build and inspect the plan without an
API key; use --limit N to generate the first N so the team can read 30 by hand,
revise the rubric, and only then scale to 400.

Usage:
    python scripts/generate_calls.py --dry-run
    python scripts/generate_calls.py --limit 30
    python scripts/generate_calls.py            # full corpus (needs OPENAI_API_KEY)
"""
from __future__ import annotations

import argparse
import datetime as dt
import random
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))          # corpus_utils
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # app.*

from corpus_utils import (  # noqa: E402
    GRID_PATH,
    PHYSICIAN_PLACEHOLDER,
    RAW_PATH,
    REQUEST_TYPES,
    SEVERITY_TIERS,
    load_rubric_tier_definitions,
    write_jsonl,
)

# Roles that never place clinical requests — constrain request_type for realism.
_NONCLINICAL_ROLES = {"pharmacy", "patient family"}

# Fraction of records per tier that are explicit loop-closing FYIs (no_callback).
_NO_CALLBACK_RATE = {"critical": 0.0, "urgent": 0.0, "routine": 0.10, "fyi": 0.45}

_TOD_HOURS = {
    "overnight": (0, 6),
    "morning": (6, 12),
    "afternoon": (12, 18),
    "evening": (18, 24),
}


def _load_grid() -> dict:
    with open(GRID_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _weighted_choice(rng: random.Random, weights: dict[str, float]) -> str:
    keys = list(weights)
    return rng.choices(keys, weights=[weights[k] for k in keys], k=1)[0]


def _allowed_request_types(grid: dict, caller_role: str) -> list[str]:
    pruned = {
        p["request_type"]
        for p in grid.get("prune_role_request", [])
        if p["caller_role"] == caller_role
    }
    allowed = [r for r in REQUEST_TYPES if r not in pruned]
    if caller_role in _NONCLINICAL_ROLES:
        # keep non-clinical callers to plausible request types
        allowed = [r for r in allowed if r in {"medication", "scheduling", "patient_status", "other"}]
    return allowed or ["other"]


def _topics_for_tier(grid: dict, tier: str) -> list[str]:
    return [t for t, tiers in grid["clinical_topics"].items() if tier in tiers]


def _synth_time(rng: random.Random, base_day: dt.datetime, tod: str) -> dt.datetime:
    lo, hi = _TOD_HOURS[tod]
    hour = rng.randrange(lo, hi)
    return base_day.replace(hour=hour, minute=rng.randrange(60), second=rng.randrange(60))


def build_plan(grid: dict, limit: int | None = None) -> list[dict]:
    """Deterministically expand the grid into a list of planned records.

    Each planned record carries assigned_* labels and a full generation_cell but
    no transcript yet. Arrival bursts are carved out afterward.
    """
    rng = random.Random(grid["seed"])
    roles = grid["dimensions"]["caller_role"]
    tod_w = grid["weights"]["time_of_day"]
    chan_w = grid["weights"]["channel"]

    records: list[dict] = []
    counter = 0
    for tier in SEVERITY_TIERS:
        n = grid["tier_counts"][tier]
        topics = _topics_for_tier(grid, tier)
        for _ in range(n):
            counter += 1
            caller_role = rng.choice(roles)
            request_type = rng.choice(_allowed_request_types(grid, caller_role))
            channel = _weighted_choice(rng, chan_w)
            tod = _weighted_choice(rng, tod_w)
            topic = rng.choice(topics)
            no_callback = rng.random() < _NO_CALLBACK_RATE[tier]
            records.append(
                {
                    "id": f"gen_{counter:04d}",
                    "transcript": "",
                    "assigned_severity": tier,
                    "assigned_request_type": request_type,
                    "assigned_no_callback": no_callback,
                    "assigned_insufficient_detail": False,
                    "generation_cell": {
                        "caller_role": caller_role,
                        "request_type": request_type,
                        "channel": channel,
                        "time_of_day": tod,
                        "clinical_topic": topic,
                    },
                    "degradations": [],
                    "generator_model": None,
                    "seed": grid["seed"] + counter,
                    "human_labels": [],
                }
            )

    _assign_timestamps_and_bursts(rng, grid, records)

    # Group into units (single record, or a whole burst) then shuffle the units
    # so any --limit prefix is tier-representative while burst members stay
    # contiguous.
    units: dict[str, list[dict]] = {}
    singles: list[list[dict]] = []
    for r in records:
        bid = r.get("burst_id")
        if bid:
            units.setdefault(bid, []).append(r)
        else:
            singles.append([r])
    all_units = singles + list(units.values())
    rng.shuffle(all_units)
    flat = [r for unit in all_units for r in unit]

    if limit is not None:
        flat = flat[:limit]
    return flat


def _assign_timestamps_and_bursts(rng: random.Random, grid: dict, records: list[dict]) -> None:
    week_start = dt.datetime(2025, 3, 3, tzinfo=dt.timezone.utc)  # a Monday; synthetic

    # Default: an independent synthetic received_at per record.
    for r in records:
        day = week_start + dt.timedelta(days=rng.randrange(7))
        r["received_at"] = _synth_time(rng, day, r["generation_cell"]["time_of_day"]).isoformat()

    # Carve >= min_bursts arrival bursts (Amendment D). Each burst: 3-4 records,
    # spanning >= 2 tiers, including >= 1 fyi, timestamps inside a 5-min window.
    cfg = grid["bursts"]
    fyi_pool = [r for r in records if r["assigned_severity"] == "fyi"]
    other_pool = [r for r in records if r["assigned_severity"] != "fyi"]
    rng.shuffle(fyi_pool)
    rng.shuffle(other_pool)

    n_bursts = cfg["min_bursts"]
    lo, hi = cfg["size_range"]
    window = cfg["window_minutes"]
    for b in range(n_bursts):
        if not fyi_pool or len(other_pool) < 2:
            break
        size = rng.randint(lo, hi)
        members = [fyi_pool.pop()]                      # >= 1 fyi
        for _ in range(size - 1):
            if other_pool:
                members.append(other_pool.pop())
        # ensure >= 2 tiers (guaranteed: fyi + non-fyi)
        burst_id = f"burst_{b + 1:02d}"
        base_day = week_start + dt.timedelta(days=rng.randrange(7))
        base = _synth_time(rng, base_day, rng.choice(list(_TOD_HOURS)))
        for m in members:
            offset = rng.randint(0, window * 60)
            m["burst_id"] = burst_id
            m["received_at"] = (base + dt.timedelta(seconds=offset)).isoformat()


# --- Prompt + generation -----------------------------------------------------

def build_prompt(record: dict, tier_defs: dict[str, str]) -> str:
    cell = record["generation_cell"]
    tier = record["assigned_severity"]
    definition = tier_defs.get(tier, "").strip() or f"(severity '{tier}'; see rubric.md)"
    extra = ""
    if record["assigned_no_callback"]:
        extra += (
            " This is a loop-closing FYI: the caller explicitly states no callback "
            "or response is needed."
        )
    return (
        f"You are a {cell['caller_role']} leaving a {cell['channel']} message for "
        f"{PHYSICIAN_PLACEHOLDER}, an on-call electrophysiology attending, at "
        f"{cell['time_of_day']}. The message concerns {cell['request_type'].replace('_', ' ')} "
        f"relating to {cell['clinical_topic'].replace('_', ' ')}. Its correct severity is "
        f"**{tier}**, defined as: {definition}\n\n"
        "Write only the message text, as it would be spoken. Do not state the "
        "severity. Keep it to roughly 2-4 sentences regardless of urgency "
        "(do not make urgent messages longer). Refer to the physician only as "
        f"'{PHYSICIAN_PLACEHOLDER}'; never invent a real physician name.{extra}"
    )


def generate_transcript(client, model: str, prompt: str, seed: int) -> str:
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        seed=seed,
    )
    return resp.choices[0].message.content.strip()


def _assert_no_forbidden_name(transcript: str, forbidden: list[str], rec_id: str) -> None:
    low = transcript.lower()
    for name in forbidden:
        if name and name.lower() in low:
            raise SystemExit(
                f"[13.5] record {rec_id} contains forbidden physician name '{name}'. "
                "Regenerate; real names must never enter the repo."
            )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None, help="Generate only the first N records")
    ap.add_argument("--model", default=None, help="Generator model (default: OPENAI_CLASSIFICATION_MODEL)")
    ap.add_argument("--dry-run", action="store_true", help="Build the plan and print distribution; no API calls")
    ap.add_argument(
        "--forbid-name",
        action="append",
        default=[],
        help="Physician real name(s) that must not appear in output (repeatable). "
        "The team must pass the partner attending's name here (Amendment G 13.5).",
    )
    ap.add_argument("--out", default=str(RAW_PATH), help="Output JSONL path")
    args = ap.parse_args()

    grid = _load_grid()
    plan = build_plan(grid, args.limit)

    if args.dry_run:
        _print_plan_summary(plan)
        return

    tier_defs = load_rubric_tier_definitions()
    from app.config import OPENAI_CLASSIFICATION_MODEL  # noqa: E402
    from openai import OpenAI  # noqa: E402

    model = args.model or OPENAI_CLASSIFICATION_MODEL
    client = OpenAI()

    for i, rec in enumerate(plan, 1):
        prompt = build_prompt(rec, tier_defs)
        rec["transcript"] = generate_transcript(client, model, prompt, rec["seed"])
        rec["generator_model"] = model
        _assert_no_forbidden_name(rec["transcript"], args.forbid_name, rec["id"])
        if i % 10 == 0 or i == len(plan):
            print(f"  generated {i}/{len(plan)}")

    write_jsonl(args.out, plan)
    print(f"\nWrote {len(plan)} records to {args.out}")


def _print_plan_summary(plan: list[dict]) -> None:
    from collections import Counter

    tiers = Counter(r["assigned_severity"] for r in plan)
    roles = Counter(r["generation_cell"]["caller_role"] for r in plan)
    chans = Counter(r["generation_cell"]["channel"] for r in plan)
    tods = Counter(r["generation_cell"]["time_of_day"] for r in plan)
    topics = Counter(r["generation_cell"]["clinical_topic"] for r in plan)
    bursts = {r["burst_id"] for r in plan if r.get("burst_id")}
    no_cb = sum(1 for r in plan if r["assigned_no_callback"])

    print(f"PLAN: {len(plan)} records (dry-run, no transcripts)\n")
    print("severity:", dict(tiers))
    print("channel: ", dict(chans))
    print("time_of_day:", dict(tods))
    print("caller_role:", dict(roles))
    print("no_callback:", no_cb)
    print(f"bursts: {len(bursts)}")
    # burst coherence check
    from collections import defaultdict

    bmembers = defaultdict(list)
    for r in plan:
        if r.get("burst_id"):
            bmembers[r["burst_id"]].append(r)
    bad = [
        b for b, ms in bmembers.items()
        if len({m["assigned_severity"] for m in ms}) < 2
        or not any(m["assigned_severity"] == "fyi" for m in ms)
    ]
    print(f"bursts spanning >=2 tiers incl fyi: {len(bmembers) - len(bad)}/{len(bmembers)}")
    print("\ntopics:", dict(topics))


if __name__ == "__main__":
    main()
