# Project handoff — Conduit / ClinRoute (MSE 401 Group 18)

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

Headline evaluation result: **91.1% recall on `critical`** calls, inter-rater
**Cohen's κ = 0.966**. (Synthetic data — validates the pipeline, not real-world
accuracy; see caveats.)

---

## Key decisions made

**Classification / labels**
- **Severity enum renamed** to `critical | urgent | routine | fyi` (was
  `severe | emergent | semi-urgent | non-urgent`) — matches the partner's vocabulary.
- **`urgency` is derived in Python** from `severity` (single `SEVERITY_TO_URGENCY`
  map), not asked of the model — the two can never disagree.
- **`channel`** (text/voicemail/phone) is set from the ingestion path, **not**
  LLM-inferred. **`no_callback`** and **`insufficient_detail`** are LLM-inferred
  flags. Added **`operational`** request type (OR-logistics calls).
- **Scope is electrophysiology only** (not broad cardiology) — consistent with the
  partner's anchors and specialty.

**Dataset**
- **Corpus scale: 400 records** (80 critical / 120 urgent / 120 routine / 80 fyi) —
  critical oversampled ~10× vs its ~2% real prevalence so recall has a usable CI.
- **Full auto-generation, lean human rating** (40 records, 2 raters).
- **Grid grounded in the measured call-load data** (285 CCU-week calls, 16:00 peak,
  49%-within-5-min bursts) rather than estimated.
- **Rubric is a provisional team draft** (§1 tier definitions) **pending partner-
  physician sign-off**; §2 anchors are quoted verbatim from the partner scenarios.
- **Cost matrix values are placeholders** — to be elicited from the clinician (N4).
- **Generator and classifier are the same model family** (`gpt-5-mini`) → shared
  blind spots. Stated as a limitation in every eval output.

**Correction loop (Task 12)**
- The classifier is a frozen LLM prompt, so physician corrections close the loop
  through **prompt context (few-shot), not model weights**. Promotion into the
  runtime pool is **human-approved**, never automatic.

**Privacy**
- **Task 13 (old de-identification) was removed** from the dataset spec and
  **superseded by the privacy architecture spec**.
- **Reconcile the iOS branch first, then do privacy** — avoids reconciling the
  backend twice.
- **Microsoft Presidio** for de-identification (open-source, runs locally — nothing
  leaves the machine; not an LLM pass).
- **Intake = "Option B"**: one **keypad tap for the room number** + a **single
  voicemail** + a **★ emergency bypass** (rather than a full 3-step structured
  flow, or a single voicemail with no structure). Keeps the caller experience close
  to a normal voicemail while getting the room out of the audio and exact.
- **All privacy controls are gated behind config flags and default OFF** so the
  synthetic-data workflow is unaffected.
- Started with the light spaCy model `en_core_web_sm`; `en_core_web_lg` noted for
  production.

**Ops**
- The merged backend now **requires Python 3.10+** (from the iOS branch).

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

- **Recall on `critical`: 91.1%** (51/56) — the headline safety metric.
- Overall accuracy 75.0%. Main error = **routine → urgent over-triage** (the model
  escalates when unsure — the "safe" direction for a triage tool).
- `insufficient_detail` flag rate **95.5%** (flags rather than guesses — NFR1).
- Clean transcripts **80.1%** vs degraded **63.1%** — realistic ASR noise costs 17
  points; the most informative slice.
- Cost-weighted error dominated by the 5 missed criticals (asymmetric by design).
- Inter-rater **Cohen's κ = 0.966**; human-vs-generator agreement 77.5%.

A visual version is in `docs/evaluation_design_review.html` (open in a browser).

> **Limitation (state this in the report):** the generator and classifier share a
> model family, so these numbers validate the pipeline and tune the threshold —
> they do **not** establish real-world accuracy.

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
