# Project handoff — ClinRoute (MSE 401 Group 18)

A summary of the work completed, the decisions behind it, the current state of the
repo, and what's left for the team. EP call-triage tool, partner WRHN.

---

## TL;DR

Both major specs are **implemented and merged to `main`**:

1. **Synthetic call dataset + evaluation harness** — a labelled 400-record EP call
   corpus was generated, degraded, leakage-checked, split, and the classifier was
   evaluated on it.
2. **Privacy architecture (P1–P10)** — de-identification, auth, CORS, identifier
   separation, gated re-identification with audit logging, audio retention, and a
   `SECURITY.md`.

The parallel **iOS app branch was reconciled** onto the main backend, and the
severity enum was standardised everywhere.

Headline evaluation result: **98.1% recall on triageable `critical`** calls
(91.1% across all records, incl. un-triageable degraded fragments), inter-rater
**Cohen's κ = 0.966**. The classifier is **not trained** — it builds its prompt
live from `data/rubric.md`, so editing the rubric changes classifications. (Synthetic
data — validates the pipeline, not real-world accuracy; see caveats.)

---

## Design decisions (all of them)

Grouped by area. Includes the foundational MVP architecture decisions as well as
everything decided during this build-out, so the reasoning is captured in one place.

### System architecture
- **Stack:** FastAPI (Python) backend, SQLite datastore, React + TypeScript web
  console, native SwiftUI iOS app. Chosen for speed of prototyping and because the
  team already had the MVP in this shape.
- **Telephony via Twilio** — records the voicemail and posts a webhook. No
  self-hosted PBX (documented as the production direction).
- **Transcription via OpenAI Whisper (hosted)** — accepted that audio leaves the
  machine for the prototype; local Whisper is the recommended production path.
- **Classification via a hosted LLM (`gpt-5-mini`) with a strict JSON schema** —
  **no model training.** The classifier is a *frozen prompt*; "training data" here
  means a labelled test set, not weights. Structured output (not free-form parsing)
  so the result is always a valid, typed object.
- **SQLite** as the store (plaintext file — a known at-rest limitation for the
  prototype). **SSE** pushes new calls to the web console; **APNs** pushes to iOS.
- **Deployment on Railway** (Procfile, `/data` volume for SQLite + audio).
- **The product is a three-way decision — interrupt now / hold / log.**
  Classification exists to serve that decision, not as an end in itself.

### Classifier & labels
- **Severity is the primary label**, renamed to `critical | urgent | routine | fyi`
  (was `severe | emergent | semi-urgent | non-urgent`) to match the partner's
  vocabulary and remove a standing source of labelling error.
- **`urgency` is derived in Python** from `severity` (single `SEVERITY_TO_URGENCY`
  map), kept only for requirements traceability (FR2) — the model is not asked for
  it, so the two labels can never disagree.
- **Severity is judged on required response time and action, not vocabulary or
  emotional register** (a calm/apologetic caller can still be critical).
- **`channel`** (text/voicemail/phone) is set from the ingestion path, **not**
  LLM-inferred. **`no_callback`** and **`insufficient_detail`** are LLM-inferred
  flags; on `insufficient_detail` the model **flags rather than guesses** (NFR1).
  Added the **`operational`** request type for OR-logistics calls.
- **`confidence` drives an auto-route vs flag-for-review threshold**; `summary` and
  `suggested_action` are one-liners for the physician.
- **Two ingestion paths share one classify-and-store tail** (`_classify_and_store`)
  — `process_call_recording` (Twilio audio) and `process_call_transcript` (text /
  synthetic), so the live system and the corpus exercise the identical classifier.
- **Correction loop closes through prompt context (few-shot), not weights.**
  Physician corrections are stored, then **human-approved** promotion adds them to a
  runtime few-shot pool; a promoted example is permanently disqualified from the
  eval test set (leakage guard).
- **The classifier is NOT trained** — `gpt-5-mini` is frozen. "train/dev/test" is
  borrowed vocabulary: the `fewshot` split is **in-context examples pasted into the
  prompt** (a cheat-sheet, shredded after each call), `dev` is where we iterate, and
  `test` is the honest held-out score. Fine-tuning (real weight training) waits for
  real clinician-labelled data (synthetic + shared model family would bake in the
  generator's blind spots).
- **The rubric drives the classifier live** (`app/services/rubric.py`): §1 tier
  definitions + §2.1 boundary rules → the severity schema description, §3/§4/§5 → the
  flag/request-type descriptions, §6 → the system prompt, §2 anchors → few-shot
  examples. **Editing `data/rubric.md` changes classifications** — single source of
  truth, no hand-copied constant. Verified: flipping one boundary rule flips a label.
- **Cost-sensitivity as a prompt nudge was tried and rejected** (Exp 1): telling the
  model to "err toward higher acuity" over-escalated borderline calls to critical
  without catching any real ones. Removed. The cost matrix governs *evaluation* only;
  the right place for cost-sensitivity at runtime is a confidence-gated review, not
  a global prompt nudge.
- **Scope is electrophysiology only** (not broad cardiology) — consistent with the
  partner's anchors, specialty, and the measured metadata.

### Dataset & evaluation methodology
- **All data is synthetic — no real PHI** (C1 / NFR2).
- **Label-first generation:** the label is asserted in the prompt and a consistent
  message is requested. A model is **never** asked to label its own output.
- **Full provenance on every record** (`generation_cell`, `seed`) — so failures can
  be attributed to specific cells, not a single accuracy number.
- **Generation counts are deliberately distorted from true prevalence** (critical
  oversampled ~10× to ~20% so recall has a usable CI; boundary tiers heavy). All
  reported rates are **reweighted against estimated prevalence**.
- **Corpus scale: 400 records** (80/120/120/80); **full auto-generation, lean human
  rating** (40 records, 2 raters).
- **Generation grid** crosses caller_role × request_type × severity × channel ×
  time_of_day × clinical_topic, **pruning clinically impossible cells** (e.g. an
  ablation referral is never critical). Grid weights are **grounded in the measured
  call-load data** (16:00 peak, text-heavy channel mix, 49%-within-5-min bursts),
  not estimated.
- **~30% of records are degraded** to resemble real Whisper output — ASR homophone
  errors, truncation, SBAR-field removal, tone distractors. Degradation **never
  changes the assigned severity** except truncation, which sets `insufficient_detail`.
- **Arrival bursts (≥12)** model the real queue (three calls in four minutes where
  arrival order inverts priority); bursts are assigned **whole** to a split.
- **Leakage is checked before any eval is trusted:** a bag-of-words baseline must
  stay under ~85% (or the generator is leaking the label), plus a length-correlation
  check.
- **Splits are deterministic and stratified** (fewshot 5% / dev 25% / test 70%) by
  severity *and* degradation status; the seed is recorded; **the test split is never
  read by generation/prompt code** (load-time guard).
- **Multi-rater agreement** via Cohen's/Fleiss' κ; **κ < 0.6 means the rubric is
  underspecified** → revise and regenerate.
- **Evaluation is cost-sensitive:** an asymmetric cost matrix (a missed critical far
  outweighs an unnecessary interrupt); **recall on `critical` is the single headline
  metric**; a **threshold sweep** justifies the operating point. Cost values are
  **placeholders pending clinician elicitation (N4)**.
- **`data/rubric.md` is the single source of truth** for tier definitions; the
  classifier's schema descriptions mirror it. The rubric is a **provisional team
  draft pending partner-physician sign-off** (§1); §2 anchors are quoted verbatim
  from the partner scenarios.
- **Generator and classifier share a model family** (`gpt-5-mini`) → shared blind
  spots. Every eval output states this: synthetic results **validate the pipeline
  and tune the threshold; they do not establish real-world accuracy.**

### Privacy & security architecture
- **Trust-boundary framing (B1–B8):** a system is only as protected as its weakest
  crossing; controls are placed at the crossings.
- **B6 (physician console) is where PHI *should* flow** — the physician is inside the
  circle of care; PHIPA does not ask us to hide data from the treating clinician. The
  control there is **authenticate / authorise / audit, not concealment.**
- **De-identification via Microsoft Presidio** (open-source, **local** spaCy model —
  nothing leaves the machine). **Not an LLM pass** — an LLM redactor would transmit
  the identifiers off-machine to remove them, defeating the purpose.
- **Redaction sits between transcription and classification** (`transcribe → redact →
  classify`) so identifiers never cross to the classifier API. Adding it at storage
  time would be useless.
- **Identifiers are split into their own table** (`call_identifiers`); the `calls`
  row — and any export — is **identifier-free by construction**.
- **Re-identification is gated and logged** (P7): `GET /calls` is redacted by
  default; a separate authorised endpoint restores identity and writes an audit row
  (`call_views`) — the event a PHIPA audit asks about.
- **Intake = "Option B"**: one **keypad tap for the room number** (DTMF — never
  becomes audio, and it's exact) + a **single voicemail** + a **★ emergency bypass**.
  Chosen over a full 3-step structured flow (worse caller UX) and over a plain single
  voicemail (weaker recall, mangled room). Rationale: keep caller friction low so
  staff don't route around the tool.
- **Audio retention:** deleted after transcription (`RETAIN_AUDIO`, default off), and
  **Twilio's own retained copy is deleted** via REST — voice is biometric and can't
  be tokenised, so stored audio is the highest-risk artifact.
- **Auth:** single-user bearer token (P2); **CORS locked** to the frontend origin
  (P3); **Twilio webhook signature validation** (P1).
- **All privacy controls are gated behind config flags and default OFF**, so the
  synthetic-data workflow is unaffected.
- **Push payloads are minimized** (severity, patient name, room, one-line summary
  only — never transcripts, caller identity, or phone numbers).
- **PHIPA reasonableness standard** (Ontario, not HIPAA safe-harbour) — the token
  categories are HIPAA-informed but this is **not a compliance claim**; sufficiency
  is WRHN's privacy office and the REB's call.
- **Started with `en_core_web_sm`** (light); `en_core_web_lg`/transformer noted for
  production. **Local Whisper is the recommended production path** (closes the
  audio→OpenAI gap) — documented, deferred.
- **Physician's real name never enters generated data** — a placeholder is used and
  `generate_calls.py` asserts against a forbidden-name list (P10).

### Process & engineering
- **Task 13 (old de-identification) was removed** from the dataset spec and
  **superseded by the privacy architecture spec**.
- **Reconcile the iOS branch *before* the privacy spec** — the two branches touched
  the same backend files; doing privacy first would have forced reconciling the
  backend twice.
- **The merged backend requires Python 3.10+** (the iOS branch uses PEP 604 unions
  and `aioapns`).
- **Migration convention:** every new column/table goes in BOTH `app/models.py` AND
  `app/database.py::_migrate_sqlite_columns`.
- **Regenerated corpus data is gitignored** — committed only after a reviewed real
  generation run, so fake data never masquerades as real.

---

## What was built

### Dataset + evaluation (`scripts/`, `data/`)
`generate_calls.py` (label-first generation, full provenance, arrival bursts,
physician-name guard) → `degrade.py` (ASR noise / truncation / SBAR-removal / tone
distractors on ~30%) → `check_leakage.py` (bag-of-words baseline + length
correlation) → `make_splits.py` (stratified fewshot/dev/test, bursts + duplicates
kept whole) → `export_for_rating.py` + `compute_agreement.py` (Cohen's/Fleiss' κ) →
`evaluate.py` (confusion matrix, recall on critical, cost-weighted error, threshold
sweep, degradation slice). Plus `promote_corrections.py` for the correction loop.

Ground truth: `data/rubric.md` (tier definitions, boundary rules — team-written),
`data/grid.yaml` (generation grid), `data/costs.yaml` (placeholder costs),
`data/source/` (partner scenarios + measured call metadata).

### Backend (`app/`)
Two ingestion paths sharing one classify-and-store tail: `process_call_recording`
(Twilio audio) and `process_call_transcript` (text/synthetic). Correction loop
(`corrections` table, `PATCH /calls/{id}/correct`). Privacy: `deident.py` redaction,
`call_identifiers` + `call_views` tables, `GET /calls/{id}/identified`, keypad
intake in `voice.py`, audio-retention deletion.

### iOS app (`ios/ClinRoute/`)
SwiftUI app + APNs push backend + bearer auth + device registry, reconciled onto
the new severity enum. **Needs a Mac + Xcode to build.**

### Docs
`docs/evaluation_design_review.html` (one-page results dashboard),
`docs/specs/SPEC_privacy_architecture.md`, `docs/RECONCILIATION_PLAN.md`,
`SECURITY.md`, this file.

---

## Evaluation results (synthetic, `gpt-5-mini`, 280-record test set)

Current best config: rubric-driven prompt + labelled examples, no cost bias, severity
scored on the **triageable subset**.

- **Recall on `critical`: 98.1%** (51/52) on triageable calls — the headline safety
  metric. (91.1% across all 280 including un-triageable degraded fragments.)
- Overall accuracy 77.5% (triageable). `insufficient_detail` flag rate **100%**.
- Clean **79.1%** vs degraded **72.6%** (triageable) — realistic ASR noise still costs
  points, but far less than the 63% the un-triageable fragments made it look.
- Inter-rater **Cohen's κ = 0.966**; human-vs-generator agreement 77.5% (the ceiling —
  ~1 in 5 "correct" labels are debatable).

### How we got here — the experiment arc (`docs/EXPERIMENTS.md`)
The evaluation harness drove every decision, including catching a regression and a
scoring bug intuition would have missed. That progression is itself a deliverable:

0. **baseline** — plain prompt: 91.1% / 75.0%, main error routine→urgent over-triage (42).
1. **feed the assets in** (rubric rules, anchors, fewshot, cost bias): fixed the
   over-triage (42→26) but the **cost bias backfired** (over-escalated to critical) —
   *mixed*.
2. **drop the cost bias**: best config — beats baseline overall accuracy, over-triage
   fixed, critical recall held.
3. **error analysis**: the "missed criticals" were **truncated un-triageable fragments**
   the model correctly flagged — a *measurement* artifact, not a model weakness.
4. **fix the measurement** (score severity on triageable calls only): honest critical
   recall 91.1%→**98.1%**, cost-weighted ~680→**202**, degraded 62%→73%.

**Design-decision meta-lesson for the report:** targeted rules (rubric boundary rules)
helped; a global prompt nudge (cost bias) hurt; and the biggest "improvement" was a
*measurement* fix, not a model change. Next planned: **confidence-gated review** (wire
the flag-for-review the threshold sweep justifies) and **label adjudication** (raise the
77.5% ceiling).

Visual dashboards (open in a browser / see the artifact links): baseline design-review,
before/after (Exp 0 vs 1), Exp 2 best config, and Exp 4 measurement fix —
`docs/evaluation_*.html`.

> **Limitation (state this in the report):** the classifier is a frozen prompt (no
> training); the generator and classifier share a model family, so these numbers
> validate the pipeline and tune the prompt — they do **not** establish real-world
> accuracy.

---

## Repo state

`main` contains everything. Merged PRs: #1 (dataset harness), #2 (privacy spec doc),
#3 (correction loop + rubric + anchors), #4 (iOS reconciliation), #5 (privacy
implementation). Backend tests: **25 passing** on Python 3.11.

---

## How to run it

```bash
# Backend (Python 3.10+)
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt
python -m spacy download en_core_web_sm        # only needed for redaction (P6)
python -m pytest                                # 25 tests
uvicorn app.main:app --reload --port 8000

# Frontend console
cd frontend && npm install && npm run dev

# iOS app (needs a Mac + Xcode)
cd ios && xcodegen generate
# open ClinRoute.xcodeproj in Xcode and run

# Corpus pipeline (needs OPENAI_API_KEY in .env; Tier-1 billing for rate limits)
python scripts/generate_calls.py --dry-run                 # inspect the plan, no API
python scripts/generate_calls.py --forbid-name "<attending name>"
python scripts/degrade.py && python scripts/check_leakage.py && python scripts/make_splits.py
python scripts/evaluate.py                                 # or --mock (offline)
```

Config flags (all default off): `DEIDENTIFY_TRANSCRIPTS`, `RETAIN_AUDIO`.
Secrets live in `.env` (gitignored).

---

## What's left — team action items

1. **Clinician sign-off on `data/rubric.md` §1** (tier definitions). Currently a
   provisional draft. If definitions change, regenerate the corpus.
2. **Wire the clients to re-identification.** `GET /calls` is now identifier-free by
   design; the **frontend and iOS detail views must call
   `GET /calls/{id}/identified`** to show the patient name/room. (Backend is done;
   this is a client change.)
3. **iOS Xcode build** — build/run on a Mac to confirm the Swift compiles (the
   severity-enum port was code-verified but not Xcode-built).
4. **Live Twilio test** — exercise the keypad intake (P5) and Twilio-copy deletion
   (P8) against a real number.
5. **For the report:** carry the synthetic-data limitation, and note the cost matrix
   is placeholder pending clinician elicitation (N4).

### Documented as deferred (not required now)
Local Whisper transcription (the strongest privacy claim — closes the audio→OpenAI
gap), encryption at rest, multi-user roles, and the queue-ordering metric on arrival
bursts. See `SECURITY.md` and the dataset spec.
