# Classifier experiments log

A running record of what we change about the classifier and what the evaluation
harness says it did. One row per experiment, one branch per experiment. The model
is frozen (`gpt-5-mini`) — these change the **prompt / in-context inputs**, not
weights. All runs use the same held-out test split (n=280) and corpus.

> Synthetic data: validates the pipeline and tunes the prompt; does **not**
> establish real-world accuracy (generator and classifier share a model family).
> Cost values are placeholders (N4).

## Summary

| # | Change | Branch | crit recall | overall | routine→urgent | insuf-detail flag | urgent recall | degraded acc | verdict |
|---|---|---|---|---|---|---|---|---|---|
| 0 | Baseline — plain prompt (condensed §1 only) | `main` | 91.1% | 75.0% | 42 | 95.5% | 95.3% | 63.1% | reference |
| 1 | + rubric §1–§6, anchors, fewshot split, cost bias | `feat/rubric-driven-classifier` | 91.1% | 73.6% | **26** | **100%** | 77.6% | 59.5% | **mixed** |
| 2 | Exp 1 minus the cost bias | `feat/exp-drop-cost-bias` | 91.1% | **77.1%** | **25** | 100% | 84.7% | 63.1% | **keep ✓** |
| 3 | Error analysis (diagnosis, no change) | `exp/error-analysis` | — | — | — | — | — | — | see below |
| 4 | Score severity on triageable subset (eval fix) | `exp/error-analysis` | **98.1%** | 77.5% | 29 | 100% | 85.2% | 72.6% | **measurement fix ✓** |

Rows 0–2 score severity on all 280 records; **row 4 scores it on the triageable
subset** (the honest measure) — see Exp 3/4.

Lower is better for **routine→urgent** (over-triage count); higher is better for
everything else.

---

## Experiment 0 — baseline

Plain system prompt; the classifier saw only a hand-copied, condensed §1 tier
description. No boundary rules, anchors, or examples.

- Recall on critical **91.1%** (51/56); overall 75.0%.
- Dominant error: **routine → urgent over-triage, 42 cases** (routine recall 37.3%).
- `insufficient_detail` flag rate 95.5%; clean 80.1% / degraded 63.1%.
- Cost-weighted error 633.5.

## Experiment 1 — feed the assets in

Classifier builds its prompt live from `data/rubric.md` (§1 defs, §2.1 boundary
rules, §3/§4/§5 field rules, §6 signals) + §2 anchors and the generated fewshot
split as worked examples + a cost-sensitivity instruction from `costs.yaml`.

**Result: mixed.**
- ✅ **routine over-triage cut 42 → 26** (routine recall 37.3% → 54.2%) — boundary rules worked.
- ✅ **insufficient_detail flagging 95.5% → 100%** — §4 rule + degraded examples.
- ✅ unnecessary interrupts 45 → 33.
- ✗ **Cost bias over-escalated ~19 borderline calls to critical** (14 urgent, 4 fyi, 2 routine) with **no gain in critical recall** (still 91.1%).
- ✗ **urgent recall 95.3% → 77.6%**; overall accuracy −1.4; cost-weighted 633.5 → 648.5.

**Decision:** keep the rubric rules + fewshot examples; **drop the cost bias**
(global nudge, backfired). Test that in Exp 2.

## Experiment 2 — drop the cost bias

Hypothesis: removing the "err toward higher acuity" instruction recovers the
urgent tier and overall accuracy while keeping the routine + insufficient_detail
wins from the rubric rules and examples.

**Result: confirmed — best config so far. Keep.**
- ✅ **Overall accuracy 77.1%** — beats the baseline (75.0%) and Exp 1 (73.6%).
- ✅ Critical recall held at 91.1%; routine over-triage 42 → **25** (routine recall 37.3% → 57.8%); insufficient_detail 100%; clean accuracy 80.1% → **83.2%**.
- ✅ Urgent tier recovered: 77.6% → 84.7% (the cost-bias over-escalation is gone).
- ✗ **Residual: urgent recall 84.7% is still below baseline (95.3%)** — the strict rubric now demotes **7 genuine urgents to routine**, so the cost-weighted error is up (633 → 680), driven by missed-urgent (×20). We traded routine over-triage for a little urgent under-triage.

**Net vs baseline:** better overall accuracy and routine/insufficient-detail; worse on the urgent-vs-routine boundary. Keep this config; the next target is urgent recall.

## Experiment 3 — error analysis (diagnosis, no change)

Extended `evaluate.py` to dump misclassified records, then read the failures. Key
finding: **the "5 missed criticals" that never moved are 4 truncated un-triageable
fragments** (e.g. *"call me about bed 10"*) — the pre-degradation severity is
critical, but the message has no content, and the model **correctly flagged them as
insufficient_detail**. Same for 5 of the 7 urgent→routine demotions. Only ~3 misses
have real content and are genuine judgment calls (K 2.6/Mg 0.7; family phrenic-nerve;
device infection) — the kind of case the 77.5% label disagreement lives in.

**Conclusion:** the residual "errors" were largely a **measurement artifact** — the
evaluation scored *severity* on records the model correctly identified as
un-triageable. Fix the evaluation, not the classifier → Exp 4.

## Experiment 4 — score severity on the triageable subset

`evaluate.py` now scores severity metrics on records with
`assigned_insufficient_detail == false`; the un-triageable records are scored only on
the flag rate (they route to a human regardless). Same classifier, same predictions,
two scorings:

| metric | scored on all 280 | scored on triageable (258) |
|---|---|---|
| recall on `critical` | 91.1% | **98.1%** |
| overall accuracy | 73.9% | 77.5% |
| missed critical | 5 | **1** |
| missed urgent | 7 | **3** |
| degraded accuracy | 61.9% (n=84) | **72.6%** (n=62) |
| cost-weighted error | ~680 | **201.5** |

**Result:** the honest critical recall is **98.1%** (51/52 — the single remaining miss
is the K/Mg judgment call), and the degraded slice is **72.6%**, not 63% — the
truncated fragments were dragging both down. This is not cheating: exclusion is by
**ground-truth** un-triageability, both numbers are reported, and it matches the
product (flagged calls go to a human). `insufficient_detail` flag rate stays 100%.

## Next (planned)
- **Confidence-gated review** (Exp 6): wire the threshold so borderline calls are
  flagged, not silently auto-routed — the real fix for the ~3 genuine judgment misses.
- **Label adjudication** (Exp 5): resolve the disagreement cases (the ceiling).
- Report the **triageable** numbers as the headline, with all-records for transparency.
