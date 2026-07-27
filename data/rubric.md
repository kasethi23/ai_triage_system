# Triage Rubric — Clinical Ground Truth

> **TEAM-WRITTEN DOCUMENT.** This file is authored and maintained by the team,
> not generated. It is the clinical ground truth for the whole pipeline and the
> artifact shown to the faculty advisor and to WRHN. Everything downstream —
> the classifier schema descriptions (Task 1), generation prompts (Tasks 5–6),
> and evaluation (Task 11) — is conditioned on this file.
>
> **Scope: electrophysiology (EP) only.** Do not write ACS, heart failure,
> valve, or cardiac-surgery content (confirmed team decision; Amendment H).
>
> **Do not proceed to Task 5 until §1 and §2 are filled in and the remaining
> `TODO`s are resolved.**
>
> **Clinician sign-off (mandatory):** §1 and §2 must be reviewed by the partner
> physician before generation scales past the first 30 records.

Severity enum (confirmed, Amendment B): `critical | urgent | routine | fyi`.

---

## 1. Severity tier definitions

State each tier in terms of **required response time and action**, not
vocabulary or emotional register.

### critical

TODO — one paragraph. Life/limb-threatening; attending interrupted, responds
within minutes.

### urgent

TODO — one paragraph. Serious and time-sensitive; attention within the hour;
not an immediate interrupt.

### routine

TODO — one paragraph. Genuine request that can wait hours; handled in normal
workflow.

### fyi

TODO — one paragraph. Informational only; no action required from the
attending.

## 2. Anchor examples

2–3 verbatim examples per tier, quoted from `data/source/oncall_comm_scenarios.html`,
each citing its scenario number.

### critical
TODO — quote 2–3 anchors, cite scenario #.

### urgent
TODO — quote 2–3 anchors, cite scenario #.

### routine
TODO — quote 2–3 anchors, cite scenario #.

### fyi
TODO — quote 2–3 anchors, cite scenario #.

## 2.1 Boundary disambiguation rules

The two boundaries that will dominate the error rate. Write ordered,
decidable rules — the kind that generalise to topics with no anchor.

### critical vs urgent
TODO.

### routine vs fyi
TODO.

## 3. `no_callback` rule

TODO — true only when the caller explicitly states no response/callback is
needed (loop-closing FYI). Distinct from low severity: a `routine`/`fyi` call
may still need a reply. Anchor: scenarios 07 and 09.

## 4. `insufficient_detail` rule (minimum information set)

TODO — define the minimum set of information required to triage. True when the
transcript lacks it (e.g. "call me back about bed 7"). Per NFR1 these are
flagged, not guessed at.

## 5. `request_type` definitions

Define each value. `operational` vs `other` must be explicit.

- `medication` — TODO (no anchor in source scenarios).
- `lab_result` — TODO (no anchor in source scenarios).
- `patient_status` — TODO.
- `consult` — TODO.
- `scheduling` — TODO (no anchor in source scenarios).
- `operational` — TODO. Time-sensitive but non-clinical logistics (OR turnover,
  consumables, staffing). Anchor: scenario 08.
- `other` — TODO. What separates it from `operational`.

## 6. Signals that must not be used

TODO — list signals the classifier must not rely on (e.g. caller's emotional
register, message length, apology/politeness). See scenario 02: nurse apologises
while describing electrical storm.

## 7. Enum-naming decision

Resolved: severity enum renamed to `critical | urgent | routine | fyi`
(Amendment B, confirmed). Recorded here for traceability.

## 8. Estimated tier prevalence

Estimated true prevalence of each tier in real EP on-call traffic. The call
metadata (`data/source/oncall_call_load_scoping.html`, N1) has no content and
therefore no labels, so these remain estimates. All reported evaluation rates
are reweighted against these figures.

| Tier | Estimated prevalence |
|---|---|
| critical | TODO (~2%) |
| urgent | TODO |
| routine | TODO |
| fyi | TODO |
