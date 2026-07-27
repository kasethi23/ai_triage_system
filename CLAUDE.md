# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

**Conduit** — a clinical call-triage prototype for MSE 401 Group 18 (electrophysiology
on-call triage, partner WRHN). A FastAPI backend answers a Twilio call, records an
SBAR voicemail, transcribes it (OpenAI Whisper), classifies it (OpenAI structured
output), stores it, and streams new calls to a React + TypeScript physician console
over SSE. The product decision is three-way: **interrupt now / hold / log**.

**Scope is electrophysiology (EP) only** — arrhythmia, devices, ablation,
cardioversion. Do not produce ACS, heart failure, valve, or cardiac-surgery content.

**All data is synthetic.** No real patient information (NFR2/C1). The prototype is
not approved for real patient data.

## Layout

```
app/
  main.py                    FastAPI app + CORS
  config.py                  env config (.env, gitignored)
  database.py                engine, init_db, sqlite column migration
  models.py                  Call ORM model
  routes/{voice,calls}.py    Twilio webhooks + console API + SSE
  services/
    transcription.py         Whisper
    classification.py        LLM structured-output classifier (JSON schema)
    storage.py               pipeline: classify + persist
frontend/                    React + TS console (Vite, Tailwind, shadcn-style ui)
scripts/                     synthetic corpus + eval pipeline (see below)
data/                        rubric, grid, costs + generated corpus (mostly gitignored)
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
- `process_call_recording(...)` — audio path (Twilio): save audio → transcribe → classify → store.
- `process_call_transcript(...)` — text path: classify → store, `audio_path=""`.

## Synthetic corpus + evaluation pipeline (`scripts/`)

Implements the SPEC_synthetic_call_dataset spec. `data/rubric.md` is **team-written
ground truth** and gates generation (must be filled + clinician-signed before
scaling past the first 30 records). `scripts/corpus_utils.py` holds shared helpers;
the severity enum is re-stated there and must match `classification.py`.

Order: `generate_calls.py` → `degrade.py` → `check_leakage.py` → `make_splits.py` →
`export_for_rating.py` → (human rating) → `compute_agreement.py` → `evaluate.py`.

- The `test` split must never be read by generation/prompt code — enforced by
  `corpus_utils.load_split()` (pass `allow_test=True` only in the evaluator).
- Every generated record carries full provenance (`generation_cell`, `seed`); a
  record missing those is a bug.
- Reweight reported rates against `prevalence` (grid.yaml / rubric §8); generation
  counts are deliberately distorted (critical oversampled, boundary tiers heavy).
- Cost values in `data/costs.yaml` are **placeholders** (N4) — evaluate.py prints a
  warning; do not report them as clinically grounded.
- Generator and classifier share a model family → shared blind spots. Synthetic
  results validate the pipeline and tune the threshold; they do not establish
  real-world accuracy. Keep that caveat in any output summary.

## Commands

```bash
# Backend
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm install && npm run dev

# Corpus pipeline (generate_calls/evaluate need OPENAI_API_KEY)
python scripts/generate_calls.py --dry-run           # inspect plan, no API calls
python scripts/generate_calls.py --limit 30 --forbid-name "<attending name>"
python scripts/degrade.py
python scripts/check_leakage.py
python scripts/make_splits.py
python scripts/evaluate.py --mock                    # offline metrics smoke test
```

## Conventions

- Env/secrets live in `.env` (gitignored). Never commit real credentials or the
  partner attending's real name; generation uses a placeholder and asserts against
  a `--forbid-name` list (Amendment G 13.5).
- Regenerated corpus data (`data/generated/*.jsonl`, `splits/*.jsonl`,
  `ratings/*.csv`, `results/*`) is gitignored; commit it only after a reviewed real run.
- sqlite schema changes: add the column to `models.py` AND to the `additions` dict
  in `database.py::_migrate_sqlite_columns` (the demo db is migrated in place).

## Not yet implemented (remaining spec work)

- **Task 12 / Amendment F** — correction feedback loop (`corrections` table,
  `promote_corrections.py`, few-shot injection). evaluate.py's leakage guard is
  already wired for it.
- **Task 13 / Amendment G** — de-identification. 13.1 (identifier-table split) and
  13.4 (`SECURITY.md`) are not deferred; 13.2 redaction / 13.3-local-Whisper may be
  designed-but-not-enabled.
