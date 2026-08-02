# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

**Conduit / ClinRoute** — a clinical call-triage prototype for MSE 401 Group 18
(electrophysiology on-call triage, partner WRHN). A FastAPI backend answers a
Twilio call, records an SBAR voicemail, transcribes it (OpenAI Whisper), classifies
it (OpenAI structured output), stores it, and alerts the on-call physician — **SSE
to the React web console, APNs push to the iOS app**. The product decision is
three-way: **interrupt now / hold / log**.

**Scope is electrophysiology (EP) only** — arrhythmia, devices, ablation,
cardioversion. Do not produce ACS, heart failure, valve, or cardiac-surgery content.

**All data is synthetic.** No real patient information (NFR2/C1). The prototype is
not approved for real patient data.

## Architecture

```
Caller -> Twilio -> FastAPI (Railway)
                      |-- Whisper transcription (app/services/transcription.py)
                      |-- LLM classification    (app/services/classification.py)
                      |-- SQLite (/data volume in prod)
                      |-- SSE ---------------> React console (frontend/, foreground web)
                      |-- APNs dispatch -----> iOS app (ios/, background/locked)
                                                 |- token registered via POST /devices
                                                 |- deep link on tap -> Call Detail
```

## Layout

```
app/
  main.py                    FastAPI app + CORS
  config.py                  env config (.env, gitignored) + APNs + auth token
  auth.py                    bearer-token dependency
  database.py                engine, init_db, sqlite column migration (Call + Device)
  models.py                  Call, Correction, Device ORM models
  routes/{voice,calls,devices}.py   Twilio webhooks + console API + SSE + push registry
  services/
    transcription.py         Whisper
    classification.py        LLM structured-output classifier (JSON schema)
    storage.py               pipeline: classify + persist (+ push dispatch)
    push.py                  APNs dispatch + severity->push policy
frontend/                    React + TS console (Vite, Tailwind, shadcn-style ui)
ios/ClinRoute/               native SwiftUI app (XcodeGen project.yml)
scripts/                     synthetic corpus + eval pipeline (see below)
data/                        rubric, grid, costs, source anchors + generated corpus
tests/                       pytest (auth, devices, push)
```

## Classification label model (important)

Severity enum is **`critical | urgent | routine | fyi`** (judged on required response
time/action, not vocabulary). The legacy `urgency` field (`urgent | routine |
informational`, FR2 traceability) is **derived in Python** from `severity` via
`SEVERITY_TO_URGENCY` in `app/services/classification.py` — the model is not asked
for it. That map is the single source of truth; keep it there.

LLM-inferred flags: `no_callback` (caller explicitly needs no reply) and
`insufficient_detail` (transcript can't be triaged; flag, don't guess — NFR1).
`channel` (`text | voicemail | phone`) is set from the ingestion path, not inferred.

The severity tier descriptions in the classifier JSON schema mirror `data/rubric.md`
§1 — **`rubric.md` is the authority; keep the schema text in sync with it.**

Two ingestion entry points in `storage.py`, sharing `_classify_and_store`:
- `process_call_recording(...)` — audio path (Twilio): save audio → transcribe → classify → store → push.
- `process_call_transcript(...)` — text path: classify → store, `audio_path=""` (no push).

## Severity + push policy

Push policy lives in exactly one place, `app/services/push.py`:

| severity | APNs behavior |
| --- | --- |
| `critical` | push, `interruption-level: time-sensitive`, distinct sound |
| `urgent`   | push, `interruption-level: time-sensitive`, default sound |
| `routine`  | no push |
| `fyi`      | no push |

`critical` is designed to upgrade to Apple's dedicated `critical` interruption level
once that entitlement is granted — isolated in one constant in `push.py`. Push
payloads are minimized (severity, patient name, room, summary only) — see
`SECURITY.md`. Dispatch is hooked into `process_call_recording` and can never break
call ingestion (it never raises).

## API

Bearer auth (`API_BEARER_TOKEN`) on everything except `/voice/*`, which uses Twilio
`X-Twilio-Signature` validation instead. Unset token = allowed in local dev with a
warning, refused in production (`RAILWAY_ENVIRONMENT` set). SSE also accepts `?token=`
(EventSource can't set headers).

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/voice/incoming`, `/voice/recording` | Twilio webhooks |
| GET | `/calls`, `/calls/{id}`, `/calls/{id}/audio` | Read calls |
| GET | `/calls/stream` | SSE feed of new calls |
| PATCH | `/calls/{id}/resolve` | Mark handled |
| PATCH | `/calls/{id}/correct` | Physician override → `corrections` (Task 12) |
| POST | `/devices` | Register iOS push token (idempotent upsert) |
| DELETE | `/devices/{token}` | Unregister |

## Synthetic corpus + evaluation pipeline (`scripts/`)

Implements the SPEC_synthetic_call_dataset spec. `data/rubric.md` is **team-written
ground truth** and gates generation (must be filled + clinician-signed before scaling
past the first 30 records). `scripts/corpus_utils.py` holds shared helpers; the
severity enum is re-stated there and must match `classification.py`.

Order: `generate_calls.py` → `degrade.py` → `check_leakage.py` → `make_splits.py` →
`export_for_rating.py` → (human rating) → `compute_agreement.py` → `evaluate.py`.

- The `test` split must never be read by generation/prompt code — enforced by
  `corpus_utils.load_split()` (pass `allow_test=True` only in the evaluator).
- Every generated record carries full provenance (`generation_cell`, `seed`).
- Reweight reported rates against `prevalence` (grid.yaml / rubric §8).
- Cost values in `data/costs.yaml` are **placeholders** (N4) — evaluate.py prints a
  warning; do not report them as clinically grounded.
- Generator and classifier share a model family → shared blind spots. Synthetic
  results validate the pipeline and tune the threshold; they do not establish
  real-world accuracy. Keep that caveat in any output summary.

## Correction feedback loop (Task 12)

The classifier is a frozen LLM prompt — no weights to retrain — so physician
corrections close the loop through **prompt context**. `PATCH /calls/{id}/correct`
writes a `corrections` row (and applies the override). `scripts/promote_corrections.py`
promotes selected corrections into `data/runtime_fewshot.jsonl` — a deliberate,
human-approved step. `classify_transcript` prepends up to `FEWSHOT_MAX_EXAMPLES` of
those as worked examples, unless `RUNTIME_FEWSHOT_ENABLED=false`. Any promoted
transcript is disqualified from the eval test set (evaluate.py hash guard);
`evaluate.py --no-runtime-fewshot` measures the effect.

## Commands

```bash
# Backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt        # + requirements-dev.txt for tests
uvicorn app.main:app --reload --port 8000
python -m pytest                        # run before declaring a backend change done

# Frontend
cd frontend && npm install && npm run dev

# iOS (needs a Mac + Xcode)
brew install xcodegen                   # once
cd ios && xcodegen generate             # project.yml -> ClinRoute.xcodeproj (gitignored)
xcodebuild -project ClinRoute.xcodeproj -scheme ClinRoute \
  -destination 'generic/platform=iOS Simulator' build CODE_SIGNING_ALLOWED=NO

# Corpus pipeline (generate_calls/evaluate need OPENAI_API_KEY)
python scripts/generate_calls.py --dry-run
python scripts/generate_calls.py --limit 30 --forbid-name "<attending name>"
python scripts/degrade.py && python scripts/check_leakage.py && python scripts/make_splits.py
python scripts/evaluate.py               # or --mock for an offline metrics smoke test
```

## Conventions

- **Migrations:** any new column/table goes in BOTH `app/models.py` AND
  `app/database.py::_migrate_sqlite_columns` — now covers `Call`, `Correction`, `Device`.
- **API contract:** `frontend/src/types.ts` is canonical; the Swift models in
  `ios/ClinRoute/Models/Call.swift` mirror it exactly (snake_case via
  `.convertFromSnakeCase`). The severity wire values are `critical|urgent|routine|fyi`.
- **Env/secrets** live in `.env` (gitignored). Never commit real credentials or the
  partner attending's real name; generation uses a placeholder and asserts against a
  `--forbid-name` list (privacy spec P10).
- Regenerated corpus data (`data/generated/*.jsonl`, `splits/*.jsonl`, `ratings/*.csv`,
  `results/*`) is gitignored; commit only after a reviewed real run.
- **Logging:** never log transcripts or push payloads at INFO; DEBUG only.

## Deployment (Railway)

`Procfile` runs uvicorn; attach a volume at `/data` (SQLite + audio default there when
`RAILWAY_ENVIRONMENT` is present). Required in prod: `API_BEARER_TOKEN`,
`TWILIO_*`, `OPENAI_API_KEY`. Push: `APNS_KEY_BASE64` (base64 of the .p8),
`APNS_KEY_ID`, `APNS_TEAM_ID`, `APNS_BUNDLE_ID`, `APNS_USE_SANDBOX`. Full env table in
`README.md`; security & data-handling in `SECURITY.md`.

## Not yet implemented (remaining spec work)

- **Privacy architecture** — de-identification (Presidio), CORS lockdown, audio
  retention, re-identification + view logging, and structured intake. Note: bearer
  auth (`app/auth.py`) and Twilio-signature validation are already present from the
  iOS workstream and partially satisfy privacy-spec P2/P1. See
  `docs/specs/SPEC_privacy_architecture.md` (tasks P1–P10) and
  `docs/RECONCILIATION_PLAN.md`.
