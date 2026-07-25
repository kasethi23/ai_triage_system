#!/usr/bin/env python3
"""Task 10 (agreement) — multi-rater agreement on the human-rated sample.

Ingests completed rating CSVs (data/ratings/completed_*.csv), writes the labels
back into `human_labels[]` on the raw records, and computes:

- Pairwise Cohen's kappa between raters
- Fleiss' kappa across all raters (only if 3+ raters, per Amendment I)
- Agreement between the majority human label and `assigned_severity`
- A per-tier confusion matrix of human-majority vs assigned

A kappa below ~0.6 means the RUBRIC is underspecified, not that raters are
careless — revise rubric.md and regenerate rather than proceeding.

Usage:
    python scripts/compute_agreement.py [--raw raw.jsonl] [--ratings-dir data/ratings]
"""
from __future__ import annotations

import argparse
import csv
import glob
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus_utils import RATINGS_DIR, RAW_PATH, SEVERITY_TIERS, read_jsonl, write_jsonl  # noqa: E402

KAPPA_FLOOR = 0.6


def _load_rater_csvs(ratings_dir: Path) -> dict[str, dict[str, str]]:
    """Return {rater_name: {record_id: severity}}."""
    raters: dict[str, dict[str, str]] = {}
    for path in sorted(glob.glob(str(ratings_dir / "completed_*.csv"))):
        name = Path(path).stem.replace("completed_", "")
        labels = {}
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                sev = (row.get("severity") or "").strip().lower()
                if sev:
                    if sev not in SEVERITY_TIERS:
                        sys.exit(f"{path}: id {row.get('id')} has invalid severity '{sev}'")
                    labels[row["id"]] = sev
        if labels:
            raters[name] = labels
    return raters


def cohens_kappa(a: dict[str, str], b: dict[str, str]) -> tuple[float, int]:
    ids = sorted(set(a) & set(b))
    if not ids:
        return float("nan"), 0
    n = len(ids)
    po = sum(1 for i in ids if a[i] == b[i]) / n
    ca = Counter(a[i] for i in ids)
    cb = Counter(b[i] for i in ids)
    pe = sum((ca.get(c, 0) / n) * (cb.get(c, 0) / n) for c in SEVERITY_TIERS)
    kappa = (po - pe) / (1 - pe) if pe != 1 else float("nan")
    return kappa, n


def fleiss_kappa(raters: dict[str, dict[str, str]]) -> tuple[float, int]:
    """Fleiss' kappa over items rated by ALL raters (fixed rater count)."""
    common = set.intersection(*(set(v) for v in raters.values())) if raters else set()
    ids = sorted(common)
    n_raters = len(raters)
    if not ids or n_raters < 2:
        return float("nan"), 0
    cats = SEVERITY_TIERS
    N = len(ids)
    # n_ij = number of raters that assigned category j to item i
    P_i = []
    cat_totals = Counter()
    for i in ids:
        counts = Counter(raters[r][i] for r in raters)
        cat_totals.update(counts)
        s = sum(counts[c] * (counts[c] - 1) for c in cats)
        P_i.append(s / (n_raters * (n_raters - 1)))
    P_bar = sum(P_i) / N
    p_j = {c: cat_totals[c] / (N * n_raters) for c in cats}
    P_e = sum(p_j[c] ** 2 for c in cats)
    kappa = (P_bar - P_e) / (1 - P_e) if P_e != 1 else float("nan")
    return kappa, N


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", default=str(RAW_PATH))
    ap.add_argument("--ratings-dir", default=str(RATINGS_DIR))
    args = ap.parse_args()

    raters = _load_rater_csvs(Path(args.ratings_dir))
    if len(raters) < 2:
        sys.exit(f"Need >=2 completed rating files in {args.ratings_dir} (found {len(raters)}).")

    print(f"Raters: {', '.join(raters)}  ({len(raters)} total)\n")

    # Pairwise Cohen's kappa
    print("== Pairwise Cohen's kappa ==")
    for r1, r2 in combinations(sorted(raters), 2):
        k, n = cohens_kappa(raters[r1], raters[r2])
        flag = "" if (k != k or k >= KAPPA_FLOOR) else "  <-- below 0.6, revise rubric"
        print(f"  {r1} vs {r2}: kappa={k:.3f} (n={n}){flag}")

    # Fleiss' kappa (3+ raters only, per Amendment I)
    if len(raters) >= 3:
        fk, n = fleiss_kappa(raters)
        print(f"\n== Fleiss' kappa (all raters) ==\n  kappa={fk:.3f} (n={n})"
              + ("" if fk != fk or fk >= KAPPA_FLOOR else "  <-- below 0.6, revise rubric"))
    else:
        print("\n(Fleiss' kappa skipped — needs 3+ raters.)")

    # Majority human label vs assigned_severity
    raw = read_jsonl(args.raw)
    by_id = {r["id"]: r for r in raw}
    all_ids = sorted(set().union(*(set(v) for v in raters.values())))

    human_majority: dict[str, str] = {}
    for rid in all_ids:
        votes = [raters[r][rid] for r in raters if rid in raters[r]]
        human_majority[rid] = Counter(votes).most_common(1)[0][0]
        # write labels back into human_labels[]
        if rid in by_id:
            by_id[rid]["human_labels"] = [
                {"rater": r, "severity": raters[r][rid]} for r in sorted(raters) if rid in raters[r]
            ]

    matched = [rid for rid in all_ids if rid in by_id]
    agree = sum(1 for rid in matched if human_majority[rid] == by_id[rid]["assigned_severity"])
    print("\n== Human-majority vs assigned_severity ==")
    print(f"  agreement: {agree}/{len(matched)} = {agree / max(len(matched),1):.1%}")

    # Per-tier confusion matrix (rows = human majority, cols = assigned)
    print("\n== Confusion matrix (row=human majority, col=assigned) ==")
    conf = defaultdict(Counter)
    for rid in matched:
        conf[human_majority[rid]][by_id[rid]["assigned_severity"]] += 1
    header = "  human\\assigned " + " ".join(f"{t[:8]:>8s}" for t in SEVERITY_TIERS)
    print(header)
    for h in SEVERITY_TIERS:
        print(f"  {h:15s} " + " ".join(f"{conf[h].get(a,0):8d}" for a in SEVERITY_TIERS))

    write_jsonl(args.raw, raw)
    print(f"\nWrote human_labels[] back into {args.raw}")


if __name__ == "__main__":
    main()
