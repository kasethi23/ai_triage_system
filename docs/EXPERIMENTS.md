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
| 2 | Exp 1 minus the cost bias | `feat/exp-drop-cost-bias` | _pending_ | | | | | | |

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

_Running…_
