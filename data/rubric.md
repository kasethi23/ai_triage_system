# Triage Rubric — Clinical Ground Truth

> **⚠ PROVISIONAL DRAFT — NOT YET CLINICIAN-APPROVED.**
> The clinical content below was drafted by the team to unblock a prototype
> generation run. It is **not** a substitute for partner-physician sign-off. §1
> and §2 must be reviewed and signed by the partner EP attending before
> generation scales past the first 30 records, and the anchor examples in §2 are
> **illustrative placeholders** until the source scenario set is added and the
> real verbatim quotes are inserted.

> **TEAM-WRITTEN DOCUMENT.** Authored and maintained by the team, not generated.
> It is the clinical ground truth for the whole pipeline and the artifact shown
> to the faculty advisor and WRHN. The classifier schema descriptions
> (`classification.py`), generation prompts (`generate_calls.py`), and evaluation
> (`evaluate.py`) are all conditioned on this file.
>
> **Scope: electrophysiology (EP) only** (confirmed decision; Amendment H). No
> ACS, heart failure, valve, or cardiac-surgery content.

Severity enum (confirmed, Amendment B): `critical | urgent | routine | fyi`.

---

## 1. Severity tier definitions

Judged on **required response time and action**, not vocabulary or emotional
register.

### critical
Immediately life- or limb-threatening, or an arrhythmic/device emergency where
minutes change the outcome. The attending must be **interrupted now** and respond
within minutes. Triggers include sustained VT/VF, electrical storm, cardiac
tamponade, complete heart block with haemodynamic compromise, or acute
deterioration after a procedure.

### urgent
Serious and time-sensitive; needs the attending's attention **soon (target within
about an hour)** but is not an immediate interrupt. The patient is stable-but-
worsening, or the problem will escalate if left unaddressed — e.g. AF with rapid
ventricular response responding poorly to rate control, a single inappropriate
ICD shock in a stable patient, a new lead malfunction, or a suspected device
pocket infection.

### routine
A genuine clinical request that **can wait hours** and be handled in normal
workflow; no interruption needed — e.g. a medication clarification, a stable
device-interrogation question, a non-urgent consult, or scheduling that affects
care.

### fyi
Informational only; **no action required** from the attending. Logged for
awareness — e.g. a stable remote transmission within limits, a completed hand-off
note, or confirmation a patient was seen.

## 2. Anchor examples

> Illustrative placeholders — **replace with verbatim quotes** from
> `data/source/oncall_comm_scenarios.html`, each citing its scenario number, once
> the source set is added.

### critical
- "He's in electrical storm — three shocks in the last hour and still in VT." *(illustrative; cite scenario #)*
- "BP is 70 systolic, he's obtunded, looks like tamponade post-ablation." *(illustrative; cite scenario #)*

### urgent
- "AF with RVR at 150, rate control isn't holding, he's uncomfortable." *(illustrative; cite scenario #)*
- "Single ICD shock, patient feels fine now, interrogation shows an inappropriate detection." *(illustrative; cite scenario #)*

### routine
- "Can we clarify the apixaban hold plan before Thursday's ablation?" *(illustrative; cite scenario #)*
- "Device clinic question about a stable interrogation, no symptoms." *(illustrative; cite scenario #)*

### fyi
- "Just closing the loop — the remote transmission was within limits, no action needed." *(illustrative; cite scenario #)*
- "FYI, the patient was seen and discharged, nothing required from you." *(illustrative; cite scenario #)*

## 2.1 Boundary disambiguation rules

### critical vs urgent
Escalate to **critical** only if there is an immediate threat to life/limb, OR
haemodynamic instability (hypotension, syncope, shock), OR an ongoing arrhythmic
emergency (sustained VT/VF, electrical storm, tamponade). Decisive test: *would a
minutes-scale delay plausibly change the outcome?* Yes → critical; no → urgent.

### routine vs fyi
Classify as **fyi** only when the caller needs **no decision, order, or reply**
from the attending — pure information or loop-closure. If any response is expected,
even a non-urgent one, it is **routine**, not fyi.

## 3. `no_callback` rule

True **only when the caller explicitly states** no response or callback is needed
(a loop-closing FYI). Distinct from low severity: a `routine`/`fyi` call may still
need a reply. Do not infer from tone or politeness. Illustrative anchors:
scenarios 07 and 09.

## 4. `insufficient_detail` rule (minimum information set)

The minimum set required to triage is: (1) **who/where** — the patient or a
location; (2) **what** — the clinical concern; (3) **the ask** — what is needed
from the attending. If any is missing such that severity cannot be judged (e.g.
"call me back about bed 7"), set `insufficient_detail: true`. Per NFR1 these are
**flagged, not guessed at** — still emit a best-guess `severity`, but the flag
governs UI treatment.

## 5. `request_type` definitions

- `medication` — drug dosing, interactions, holds, or anticoagulation management
  questions. *(No source anchor — provisional.)*
- `lab_result` — reporting or asking about a test value (e.g. INR, potassium).
  *(No source anchor — provisional.)*
- `patient_status` — a change in the patient's condition, vitals, rhythm, or
  symptoms.
- `consult` — a request for the EP attending's opinion, assessment, or plan.
- `scheduling` — booking, timing, or logistics of a procedure or follow-up that
  affects care. *(No source anchor — provisional.)*
- `operational` — time-sensitive but **non-clinical** logistics: OR turnover,
  missing consumables, staffing, equipment. Anchor: scenario 08.
- `other` — anything not covered above and with no logistics dimension.

**`operational` vs `other`:** `operational` is actionable logistics under time
pressure that the attending can influence; `other` is miscellaneous with no
logistics dimension and no clear clinical request.

## 6. Signals that must not be used

Do **not** rely on: the caller's emotional register (calm, apologetic, panicked),
politeness or apology, message length, caller seniority, or urgency words
themselves. Judge on required response time and action. See scenario 02: a nurse
apologises for waking the physician while describing electrical storm — tone is
inversely related to acuity there.

## 7. Enum-naming decision

Resolved: severity enum renamed to `critical | urgent | routine | fyi`
(Amendment B, confirmed). Recorded here for traceability.

## 8. Estimated tier prevalence

Estimated true prevalence in real EP on-call traffic. The call metadata
(`data/source/oncall_call_load_scoping.html`, N1) has no content and therefore no
labels, so these remain estimates. All reported evaluation rates are reweighted
against these figures (kept in sync with `grid.yaml`'s `prevalence` block).

| Tier | Estimated prevalence |
|---|---|
| critical | ~2% |
| urgent | ~13% |
| routine | ~45% |
| fyi | ~40% |
