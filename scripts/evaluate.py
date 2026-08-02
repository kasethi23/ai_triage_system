#!/usr/bin/env python3
"""Task 11 — evaluate the classifier against the held-out test split.

Runs the frozen LLM classifier over test.jsonl (via process_call_transcript) and
compares predicted vs assigned labels. Reports:

- Confusion matrix for severity, raw and prevalence-reweighted.
- Cost-weighted error read from data/costs.yaml (placeholder warning printed).
- Recall on `critical` — the single headline metric.
- Behaviour on the insufficient_detail subset: flag rate vs guess rate (NFR1).
- Threshold sweep: confidence cutoff vs (missed-urgent, unnecessary-interrupt).
- Degradation slice: clean vs degraded accuracy (the most informative slice;
  full per-cell breakdown is deferred per Amendment I but provenance is kept).

Leakage guard (Amendment F, mandatory): fails loudly if any test transcript hash
appears in the fewshot split or the runtime few-shot pool. A classifier
evaluated on its own worked examples produces a meaningless number.

Results are written to data/results/ as JSON and a human-readable summary.

Usage:
    python scripts/evaluate.py                 # real classifier (needs OPENAI_API_KEY)
    python scripts/evaluate.py --mock           # offline: deterministic fake predictor
    python scripts/evaluate.py --limit 50
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from corpus_utils import (  # noqa: E402
    COSTS_PATH,
    DATA_DIR,
    RESULTS_DIR,
    SEVERITY_TIERS,
    SPLITS_DIR,
    load_split,
    read_jsonl,
    transcript_hash,
)

SEVERITY_RANK = {"critical": 3, "urgent": 2, "routine": 1, "fyi": 0}  # higher = more severe
RUNTIME_FEWSHOT = DATA_DIR / "runtime_fewshot.jsonl"

LIMITATION = (
    "LIMITATION: the generator and the classifier share a model family and "
    "therefore share blind spots. These synthetic results validate the pipeline "
    "and tune the threshold; they do NOT establish real-world accuracy."
)


# --- leakage guard (Amendment F) ---------------------------------------------

def _guard_no_leakage(test_records: list[dict]) -> None:
    forbidden = set()
    fewshot = SPLITS_DIR / "fewshot.jsonl"
    if fewshot.exists():
        forbidden |= {transcript_hash(r["transcript"]) for r in read_jsonl(fewshot)}
    if RUNTIME_FEWSHOT.exists():
        forbidden |= {transcript_hash(r["transcript"]) for r in read_jsonl(RUNTIME_FEWSHOT)}
    overlap = [r["id"] for r in test_records if transcript_hash(r["transcript"]) in forbidden]
    if overlap:
        raise SystemExit(
            f"[leakage guard] {len(overlap)} test records overlap the fewshot / runtime "
            f"pool by transcript hash (e.g. {overlap[:3]}). Evaluation aborted."
        )


# --- prediction --------------------------------------------------------------

def predict_real(test_records, limit=None):
    """Run the true classifier through process_call_transcript on an ephemeral DB."""
    import os
    import tempfile

    db_path = Path(tempfile.gettempdir()) / "conduit_eval.db"
    if db_path.exists():
        db_path.unlink()
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

    from app.database import SessionLocal, init_db
    from app.services.storage import process_call_transcript

    init_db()
    rows = []
    db = SessionLocal()
    try:
        for i, r in enumerate(test_records[: limit or len(test_records)], 1):
            call = process_call_transcript(
                db, r["transcript"], f"EVAL_{r['id']}", "+15555550000",
                channel=r.get("generation_cell", {}).get("channel", "voicemail"),
            )
            rows.append(_row(r, call.severity, call.confidence, call.insufficient_detail))
            if i % 10 == 0 or i == len(test_records):
                print(f"  classified {i}/{len(test_records)}")
    finally:
        db.close()
    return rows


def predict_mock(test_records, limit=None):
    """Offline deterministic predictor: mostly correct with adjacent-tier slips,
    so the reporting pipeline can be exercised without an API key."""
    import hashlib

    rows = []
    for r in test_records[: limit or len(test_records)]:
        h = int(hashlib.sha256(r["id"].encode()).hexdigest(), 16)
        assigned = r["assigned_severity"]
        rank = SEVERITY_RANK[assigned]
        # ~25% slip to an adjacent tier
        if h % 4 == 0:
            rank = max(0, min(3, rank + (1 if (h // 4) % 2 else -1)))
        pred = next(t for t, v in SEVERITY_RANK.items() if v == rank)
        conf = 0.5 + (h % 50) / 100.0
        pred_insuf = bool(r.get("assigned_insufficient_detail")) and (h % 3 != 0)
        rows.append(_row(r, pred, conf, pred_insuf))
    return rows


def _row(record, predicted, confidence, pred_insufficient):
    return {
        "id": record["id"],
        "assigned": record["assigned_severity"],
        "predicted": predicted,
        "confidence": confidence,
        "assigned_insufficient": bool(record.get("assigned_insufficient_detail")),
        "pred_insufficient": bool(pred_insufficient),
        "degraded": bool(record.get("degradations")),
        "cell": record.get("generation_cell", {}),
    }


# --- metrics -----------------------------------------------------------------

def confusion_matrix(rows):
    conf = {a: Counter() for a in SEVERITY_TIERS}
    for r in rows:
        conf[r["assigned"]][r["predicted"]] += 1
    return conf


def reweight_confusion(conf, prevalence):
    """Scale each assigned-row to its true prevalence share (rows sum to prevalence)."""
    out = {}
    for a in SEVERITY_TIERS:
        total = sum(conf[a].values())
        w = prevalence.get(a, 0.0)
        out[a] = {p: (conf[a].get(p, 0) / total * w if total else 0.0) for p in SEVERITY_TIERS}
    return out


def recall(conf, tier):
    total = sum(conf[tier].values())
    return conf[tier].get(tier, 0) / total if total else float("nan")


def cost_weighted_error(rows, costs):
    total = 0.0
    breakdown = Counter()
    for r in rows:
        a, p = r["assigned"], r["predicted"]
        if a != p:
            if a == "critical":
                key = "missed_critical"
            elif a == "urgent" and p in ("routine", "fyi"):
                key = "missed_urgent"
            elif a in ("routine", "fyi") and p in ("critical", "urgent"):
                key = "unnecessary_interrupt"
            else:
                key = "over_triage_one_tier"
            total += costs.get(key, 0)
            breakdown[key] += 1
        # NFR1: insufficient_detail guessed instead of flagged
        if r["assigned_insufficient"] and not r["pred_insufficient"]:
            total += costs.get("insufficient_detail_guessed", 0)
            breakdown["insufficient_detail_guessed"] += 1
    return total, breakdown


def insufficient_detail_behaviour(rows):
    subset = [r for r in rows if r["assigned_insufficient"]]
    flagged = sum(1 for r in subset if r["pred_insufficient"])
    return {
        "n": len(subset),
        "flagged": flagged,
        "guessed": len(subset) - flagged,
        "flag_rate": flagged / len(subset) if subset else float("nan"),
    }


def threshold_sweep(rows, steps=11):
    """Below cutoff -> flag for review (no error). Above -> auto-route on predicted."""
    out = []
    for i in range(steps):
        cutoff = i / (steps - 1)
        auto = [r for r in rows if r["confidence"] >= cutoff]
        missed_urgent = sum(
            1 for r in auto
            if r["assigned"] in ("critical", "urgent") and r["predicted"] in ("routine", "fyi")
        )
        unnecessary = sum(
            1 for r in auto
            if r["assigned"] in ("routine", "fyi") and r["predicted"] in ("critical", "urgent")
        )
        out.append({
            "cutoff": round(cutoff, 2),
            "auto_routed": len(auto),
            "flagged": len(rows) - len(auto),
            "missed_urgent": missed_urgent,
            "unnecessary_interrupt": unnecessary,
        })
    return out


def degradation_slice(rows):
    out = {}
    for label, degraded in (("clean", False), ("degraded", True)):
        subset = [r for r in rows if r["degraded"] == degraded]
        correct = sum(1 for r in subset if r["assigned"] == r["predicted"])
        out[label] = {"n": len(subset), "accuracy": correct / len(subset) if subset else float("nan")}
    return out


# --- reporting ---------------------------------------------------------------

def _fmt_confusion(conf, reweighted=False):
    lines = ["  assigned\\pred " + " ".join(f"{t[:8]:>9s}" for t in SEVERITY_TIERS)]
    for a in SEVERITY_TIERS:
        if reweighted:
            cells = " ".join(f"{conf[a].get(p,0):9.4f}" for p in SEVERITY_TIERS)
        else:
            cells = " ".join(f"{conf[a].get(p,0):9d}" for p in SEVERITY_TIERS)
        lines.append(f"  {a:13s} " + cells)
    return "\n".join(lines)


def build_summary(rows, costs, prevalence) -> str:
    conf = confusion_matrix(rows)
    rw = reweight_confusion(conf, prevalence)
    total = len(rows)
    overall = sum(conf[t].get(t, 0) for t in SEVERITY_TIERS) / total if total else float("nan")
    cost_total, cost_break = cost_weighted_error(rows, costs)
    insuf = insufficient_detail_behaviour(rows)
    sweep = threshold_sweep(rows)
    deg = degradation_slice(rows)

    L = []
    L.append("CONDUIT CLASSIFIER EVALUATION")
    L.append("=" * 60)
    L.append(LIMITATION)
    L.append("")
    L.append(f"Test records: {total}   Overall accuracy: {overall:.1%}")
    L.append("")
    L.append(f">>> HEADLINE — recall on `critical`: {recall(conf, 'critical'):.1%}")
    L.append("")
    L.append("Confusion matrix (raw counts):")
    L.append(_fmt_confusion(conf))
    L.append("")
    L.append("Confusion matrix (prevalence-reweighted; rows sum to true prevalence):")
    L.append(_fmt_confusion(rw, reweighted=True))
    L.append("")
    L.append("Cost-weighted error (data/costs.yaml):")
    L.append("  !! PLACEHOLDER COSTS — not clinically grounded until elicited (N4).")
    L.append(f"  total cost: {cost_total:.1f}   mean/record: {cost_total/total if total else 0:.3f}")
    for k, v in cost_break.most_common():
        L.append(f"    {k}: {v}  (unit cost {costs.get(k)})")
    L.append("")
    L.append("insufficient_detail behaviour (NFR1 — flag vs guess):")
    L.append(f"  subset n={insuf['n']}  flagged={insuf['flagged']}  guessed={insuf['guessed']}  "
             f"flag_rate={insuf['flag_rate']:.1%}")
    L.append("")
    L.append("Degradation slice (clean vs degraded accuracy):")
    for k, v in deg.items():
        L.append(f"  {k:9s} n={v['n']:4d}  accuracy={v['accuracy']:.1%}")
    L.append("")
    L.append("Threshold sweep (cutoff -> auto-routed / missed-urgent / unnecessary-interrupt):")
    L.append("  cutoff  auto  flagged  missed_urgent  unnec_interrupt")
    for s in sweep:
        L.append(f"  {s['cutoff']:.2f}   {s['auto_routed']:4d}  {s['flagged']:6d}  "
                 f"{s['missed_urgent']:12d}  {s['unnecessary_interrupt']:14d}")
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mock", action="store_true", help="Offline deterministic predictor (no API)")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument(
        "--no-runtime-fewshot",
        action="store_true",
        help="Run with the runtime few-shot pool DISABLED, to measure the effect "
        "of accumulated physician corrections (Task 12).",
    )
    args = ap.parse_args()

    if args.no_runtime_fewshot:
        os.environ["RUNTIME_FEWSHOT_ENABLED"] = "false"
        print("Runtime few-shot pool DISABLED for this run.")

    test = load_split("test", allow_test=True)
    if not test:
        sys.exit("Empty test split — run make_splits.py first.")
    _guard_no_leakage(test)

    print(f"Evaluating {len(test)} test records{' (MOCK)' if args.mock else ''}...")
    rows = predict_mock(test, args.limit) if args.mock else predict_real(test, args.limit)

    costs = yaml.safe_load(open(COSTS_PATH, encoding="utf-8"))
    grid = yaml.safe_load(open(DATA_DIR / "grid.yaml", encoding="utf-8"))
    prevalence = grid.get("prevalence", {})

    summary = build_summary(rows, costs, prevalence)
    print("\n" + summary)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    conf = confusion_matrix(rows)
    result = {
        "generated_at": stamp,
        "mock": args.mock,
        "limitation": LIMITATION,
        "n_test": len(rows),
        "confusion_raw": {a: dict(conf[a]) for a in SEVERITY_TIERS},
        "confusion_reweighted": reweight_confusion(conf, prevalence),
        "recall_critical": recall(conf, "critical"),
        "cost_weighted": dict(zip(("total", "breakdown"),
                                  (lambda t, b: (t, dict(b)))(*cost_weighted_error(rows, costs)))),
        "insufficient_detail": insufficient_detail_behaviour(rows),
        "degradation_slice": degradation_slice(rows),
        "threshold_sweep": threshold_sweep(rows),
        "prevalence": prevalence,
        "costs_are_placeholder": True,
    }
    (RESULTS_DIR / f"eval_{stamp}.json").write_text(json.dumps(result, indent=2))
    (RESULTS_DIR / f"eval_{stamp}.txt").write_text(summary + "\n")
    print(f"\nWrote data/results/eval_{stamp}.json and .txt")


if __name__ == "__main__":
    main()
