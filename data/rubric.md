# Triage Rubric — Clinical Ground Truth

> **⚠ PROVISIONAL DRAFT — NOT YET CLINICIAN-APPROVED.**
> The tier definitions in §1 were drafted by the team to unblock a prototype
> generation run. They are **not** a substitute for partner-physician sign-off:
> §1 must be reviewed and signed by the partner EP attending before generation
> scales past the first 30 records. The §2 anchors are now quoted **verbatim**
> from the partner scenario set (`data/source/oncall_comm_scenarios.html`).

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

Verbatim quotes from `data/source/oncall_comm_scenarios.html`, cited by scenario
number. (Note: the source set tags urgency as Critical / Urgent / Routine / FYI,
which map onto this rubric's `critical | urgent | routine | fyi` directly.)

### critical
- **Scenario 02** (CCU nurse, text): "Your ICD patient in bed 2 has had 3 shocks
  in 15 minutes, awake and distressed, looks like recurrent VT on the monitor."
  — electrical storm; note the caller apologises for waking the physician (see §6).
- **Scenario 03** (referring ED physician, phone): "a regular wide-complex
  tachycardia at 190, looks like VT, BP 84 systolic and borderline. Adenosine did
  nothing. Awake but clammy. I need EP input now."

### urgent
- **Scenario 01** (CCU nurse, text): "bed 4 flipped into AF with RVR about 20
  minutes ago. Rate 138 to 150, BP holding at 122/74, no chest pain. Rates not
  settling." — active arrhythmia, haemodynamically stable.
- **Scenario 06** (ward nurse, text): "swelling over the device pocket, firm and
  a bit tense, bruising spreading. No external bleeding … Concerned about a pocket
  hematoma."

### routine
- **Scenario 04** (community cardiologist, voicemail): "a patient in her fifties,
  very symptomatic paroxysmal AF, failed flecainide and sotalol, keen on ablation
  … Wanted to see if you would take the referral … no rush."
- **Scenario 05** (device-clinic NP, text): "Remote transmission … flagged 3
  episodes of AT/AF overnight, longest 4 hours, rates well controlled. CHADS score
  is 3, currently not anticoagulated."

### fyi
- **Scenario 07** (ward nurse, voicemail): "your post-ablation patient from this
  morning is settled and comfortable … No callback needed, just keeping you in the
  loop." — no-callback FYI (see §3).
- **Scenario 09** (NP, text): "FYI your cardioversion patient from Tuesday is doing
  well, back in sinus … Nothing needed from you."

### operational (crosses tiers; see §5)
- **Scenario 08** (OR nurse, phone): "we are turning over room 3 … the PFA
  consumables have not arrived from stores and anesthesia wants to know if you want
  general or conscious sedation." — time-sensitive logistics, not a clinical
  emergency; tagged Urgent in the source.

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
