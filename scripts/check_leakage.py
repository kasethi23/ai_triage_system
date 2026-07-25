#!/usr/bin/env python3
"""Task 8 — leakage checks. Run BEFORE any evaluation is trusted.

Two independent checks:

1. Keyword / bag-of-words baseline. Trains a bag-of-words multiclass logistic
   regression on transcript -> assigned_severity. If a dumb lexical model
   exceeds ~85% accuracy, the generator is leaking the label through vocabulary
   and the LLM result is meaningless — regenerate.

2. Length correlation. Mean/median token count per tier. LLMs unconsciously
   write longer text for urgent cases; if length alone separates the tiers,
   regenerate with an explicit length constraint in the prompt.

Prints the numbers and a clear PASS/FAIL, not just a boolean. Pure stdlib so it
runs offline with no ML dependency.

Usage:
    python scripts/check_leakage.py [--in data/generated/raw.jsonl]
"""
from __future__ import annotations

import argparse
import math
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus_utils import RAW_PATH, SEVERITY_TIERS, read_jsonl, tokenize  # noqa: E402

ACCURACY_THRESHOLD = 0.85
VOCAB_SIZE = 500
SEED = 13


def _stratified_split(records, test_frac=0.3, seed=SEED):
    rng = random.Random(seed)
    by_tier = defaultdict(list)
    for r in records:
        by_tier[r["assigned_severity"]].append(r)
    train, test = [], []
    for tier, rows in by_tier.items():
        rng.shuffle(rows)
        k = max(1, int(len(rows) * test_frac))
        test += rows[:k]
        train += rows[k:]
    rng.shuffle(train)
    rng.shuffle(test)
    return train, test


def _build_vocab(records, size=VOCAB_SIZE):
    counts = Counter()
    for r in records:
        counts.update(set(tokenize(r["transcript"])))
    return {tok: i for i, (tok, _) in enumerate(counts.most_common(size))}


def _featurize(record, vocab):
    vec = [0.0] * (len(vocab) + 1)
    vec[-1] = 1.0  # bias
    for tok in set(tokenize(record["transcript"])):
        j = vocab.get(tok)
        if j is not None:
            vec[j] = 1.0
    return vec


def _train_logreg(train, vocab, classes, epochs=60, lr=0.2, l2=1e-4, seed=SEED):
    """Minimal multiclass softmax logistic regression (SGD). No numpy."""
    rng = random.Random(seed)
    dim = len(vocab) + 1
    W = {c: [0.0] * dim for c in classes}
    data = [(_featurize(r, vocab), r["assigned_severity"]) for r in train]
    for _ in range(epochs):
        rng.shuffle(data)
        for x, y in data:
            active = [j for j, v in enumerate(x) if v] or [dim - 1]
            scores = {c: sum(W[c][j] for j in active) for c in classes}
            m = max(scores.values())
            exp = {c: math.exp(scores[c] - m) for c in classes}
            z = sum(exp.values())
            for c in classes:
                p = exp[c] / z
                g = p - (1.0 if c == y else 0.0)
                for j in active:
                    W[c][j] -= lr * (g + l2 * W[c][j])
    return W


def _predict(W, x, classes):
    active = [j for j, v in enumerate(x) if v] or [len(x) - 1]
    scores = {c: sum(W[c][j] for j in active) for c in classes}
    return max(scores, key=scores.get)


def keyword_baseline(records) -> float:
    train, test = _stratified_split(records)
    vocab = _build_vocab(train)
    classes = [t for t in SEVERITY_TIERS if any(r["assigned_severity"] == t for r in train)]
    W = _train_logreg(train, vocab, classes)
    correct = sum(1 for r in test if _predict(W, _featurize(r, vocab), classes) == r["assigned_severity"])
    return correct / max(len(test), 1)


def length_correlation(records):
    lengths = defaultdict(list)
    for r in records:
        lengths[r["assigned_severity"]].append(len(tokenize(r["transcript"])))
    stats = {}
    for tier in SEVERITY_TIERS:
        vals = lengths.get(tier, [])
        if vals:
            stats[tier] = {"mean": statistics.mean(vals), "median": statistics.median(vals), "n": len(vals)}
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="inp", default=str(RAW_PATH))
    args = ap.parse_args()

    records = [r for r in read_jsonl(args.inp) if r.get("transcript")]
    if not records:
        sys.exit("No records with transcripts found — generate the corpus first.")

    print(f"Loaded {len(records)} records with transcripts.\n")

    # Check 1 — lexical baseline
    acc = keyword_baseline(records)
    passed1 = acc <= ACCURACY_THRESHOLD
    print("== Check 1: bag-of-words logistic-regression baseline ==")
    print(f"  held-out accuracy: {acc:.1%}  (threshold {ACCURACY_THRESHOLD:.0%})")
    print(f"  {'PASS' if passed1 else 'FAIL'} — "
          + ("lexical signal is within expected range." if passed1
             else "vocabulary is leaking the label; regenerate."))

    # Check 2 — length correlation
    print("\n== Check 2: length correlation ==")
    stats = length_correlation(records)
    for tier in SEVERITY_TIERS:
        if tier in stats:
            s = stats[tier]
            print(f"  {tier:9s} n={s['n']:4d}  mean={s['mean']:6.1f}  median={s['median']:6.1f} tokens")
    means = [stats[t]["mean"] for t in SEVERITY_TIERS if t in stats]
    spread = (max(means) / min(means)) if means and min(means) > 0 else 1.0
    # Heuristic: large spread that tracks severity rank suggests length leakage.
    ranked = [t for t in SEVERITY_TIERS if t in stats]
    monotonic = all(stats[ranked[i]]["mean"] >= stats[ranked[i + 1]]["mean"] for i in range(len(ranked) - 1))
    passed2 = not (spread > 1.5 and monotonic)
    print(f"  mean-length spread (max/min): {spread:.2f}; monotonic by severity: {monotonic}")
    print(f"  {'PASS' if passed2 else 'FAIL'} — "
          + ("length does not separate tiers." if passed2
             else "length tracks severity; add a length constraint and regenerate."))

    print("\nOVERALL:", "PASS" if (passed1 and passed2) else "FAIL — corpus is invalid, regenerate.")
    if not (passed1 and passed2):
        sys.exit(1)


if __name__ == "__main__":
    main()
