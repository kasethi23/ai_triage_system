# Reconciliation plan: `main` + `ios-app`

Status: proposal for review. **No code changes until approved.**

## Goal

`main` and `origin/ios-app` diverged at the MVP root (`4b40266`) and developed in
parallel. We want a single line that keeps **everything on `main`** (the collapsed
`critical | urgent | routine | fyi` label model, the synthetic-corpus + evaluation
pipeline, and the privacy spec) **and** gains **the iOS app** (`ClinRoute`) plus its
push-notification backend, bearer auth, tests, and deploy tooling. For the
privacy/de-identification work we use an existing OSS library rather than
hand-rolling a redactor.

## Guiding principles

1. **`main` is the source of truth for the backend contract.** The classifier now
   emits `critical | urgent | routine | fyi` and derives `urgency` in Python
   (`SEVERITY_TO_URGENCY`). `ios-app` was written against the pre-rename backend, so
   the iOS client and the push policy get ported *to* `main`, never the reverse.
2. **`ios-app` is an additive client + delivery layer.** Almost everything it adds
   (the `ios/` app, `push.py`, `devices.py`, `auth.py`, tests, deploy files) does not
   touch the files `main` changed.
3. **Don't reinvent de-identification.** Use Microsoft Presidio (local, MIT) for the
   privacy-spec P6 redactor; see §5.

## Branch & merge strategy

```
git checkout main
git checkout -b reconcile/ios-plus-main
git merge origin/ios-app        # expect conflicts only in the 5 files in §4b
```

Resolve the 5 conflicts (§4b), do the enum port (§4c), then wire Presidio (§5) as a
follow-up commit. Land via PR into `main`. Do the merge on this branch so `main`
stays clean until it builds and tests pass.

## 4a. Additive files — take from `ios-app` as-is

No overlap with `main`; they merge cleanly:

- `ios/` — the entire ClinRoute SwiftUI app (**requires Xcode / XcodeGen to build**;
  see §6).
- `app/services/push.py`, `app/routes/devices.py` — APNs push + device registry.
- `app/auth.py` — bearer-token auth (partial down-payment on privacy-spec P2).
- `app/config.py`, `app/main.py`, `app/routes/calls.py`, `app/routes/voice.py` —
  only `ios-app` changed these, so they arrive additively. **Review** `main.py`
  (CORS) and `voice.py` against privacy-spec P1/P3 intent, but they are not conflicts.
- `tests/`, `pytest.ini`, `requirements-dev.txt`, `Makefile`, `Procfile`,
  `docs/SYSTEM_DESIGN.md`.

## 4b. Conflicting files — exactly 5, all shallow

| File | `main` changed | `ios-app` changed | Resolution |
|---|---|---|---|
| `app/models.py` | appended `channel`, `no_callback`, `insufficient_detail` to `Call`; severity default → `fyi` | appended a new `Device` class | **Union** — keep both blocks; they touch different classes. |
| `app/database.py` | new columns in the `calls` additions dict (+`fyi` default) | restructured `_migrate_sqlite_columns` to also migrate a `devices` table | Take `ios-app`'s restructured function, then replace its `calls` additions dict with `main`'s (new columns, `fyi` default). Keep the `devices` block. |
| `app/services/storage.py` | refactored into `_classify_and_store`; added `process_call_transcript`; new fields | added `dispatch_push_for_call(...)` after persist in `process_call_recording` | Base = `main`'s refactor. Add the push import and call `dispatch_push_for_call(db, call_to_dict(call))` inside `process_call_recording` (real-call path) **only** — not `process_call_transcript`, so synthetic corpus ingestion never pushes. |
| `requirements.txt` | `+PyYAML==6.0.2` | `+aioapns==4.0` | Union both, then add the Presidio deps (§5). |
| `CLAUDE.md` | project guide (backend + corpus + privacy) | project guide (iOS + push + deploy) | Merge into one guide covering both; see §7. |

None of these are logic collisions — each is an append or an independent block.

## 4c. The real work — port the label enum

`main` renamed the enum and removed `urgency` from the schema. `classify_transcript`
is **not** a conflict (only `main` changed it), so the merged backend automatically
emits `critical | urgent | routine | fyi`. What must move to match it:

**Backend — `app/services/push.py`.** The push-policy table is keyed on the old enum
(`severe/emergent/semi-urgent/non-urgent`) and has a `display_severity()` that maps
`severe→critical`, `emergent→urgent`. Re-key the policy table to
`critical/urgent/routine/fyi` and collapse `display_severity()` to identity (the enum
*is* the product vocabulary now). Policy intent is unchanged:
`critical`/`urgent` push, `routine`/`fyi` do not.

**iOS — port the `Severity` enum and everything keyed on it:**

- `ios/ClinRoute/Models/Call.swift` (~24 refs) — the `enum Severity` cases and raw
  values, the sort order, and the display mapping.
- `ios/ClinRoute/Theme/OrganicTheme.swift` (~5 refs) — per-severity colors.
- `ios/ClinRoute/Views/CallDetailView.swift` (~5 refs) — badge/label rendering.
- `CallListView.swift` has 0 direct refs (drives off the model), so it follows for free.

New wire values must be exactly `critical | urgent | routine | fyi` to match the
backend JSON. The web console (`frontend/`) already uses the new enum — no change.

## 5. De-identification — Microsoft Presidio (privacy-spec P6)

**Library:** [`presidio-analyzer`](https://github.com/microsoft/presidio) +
`presidio-anonymizer` (MIT, Python, runs 100% locally on a bundled spaCy model — no
data leaves the machine, which is the constraint the spec cares about). Chosen over
Philter / scrubadub because it is the only option that covers **detect → anonymize →
re-identify** locally, matching P6 *and* P7.

**New file `app/services/deident.py`:**

```
redact(transcript: str, known: dict) -> tuple[str, dict]
    # returns (redacted_text, token_map)
```

- **Stage 1 (deterministic, primary).** A Presidio deny-list / `PatternRecognizer`
  seeded with `known` identifiers (patient name from structured intake, once P5
  lands) → near-perfect recall on the known target. `[PATIENT_1]`, etc.
- **Stage 2 (residual heuristic, backstop).** Presidio's default recognizers
  (`PERSON`, `PHONE_NUMBER`, `DATE_TIME`) plus custom pattern recognizers for
  MRN/room and ages > 89 → `[PERSON_n]`, `[DATE_n]`, `[ID_n]`, `[AGE_90+]`.
- **Anonymizer** emits stable, per-entity, coreferent tokens within a call; the
  `token_map` it returns is what P7 stores in `call_identifiers` and reverses in
  `reidentify()`.

**Pipeline position** (the whole point): `transcribe → redact → classify` —
`classify_transcript` receives redacted text only. Gate behind a
`DEIDENTIFY_TRANSCRIPTS` config flag.

**Dependencies to add:** `presidio-analyzer`, `presidio-anonymizer`, `spacy`, and a
spaCy model (`en_core_web_lg`, downloaded at setup — document in README/Makefile).

**Not fully closed here.** Presidio only handles text. Its output feeds the P4
identifier-table split and P7 re-identification, which remain separate privacy-spec
tasks; `deident.py` is the piece they depend on. Note in `SECURITY.md` that Stage 2
recall is imperfect (spaCy NER), not a guarantee.

## 6. Documentation de-dup

- **`CLAUDE.md`** — merge the two into one guide: backend contract + corpus/eval
  pipeline + privacy (from `main`) and iOS app + push + auth + deploy (from `ios-app`).
- **`SECURITY.md`** — `ios-app` already ships one. Keep it, but rewrite around the
  privacy-spec P9 trust-boundary table and reconcile with the P1–P8 status.
- **`README.md`** — only `ios-app` changed it; take its version, add a pointer to the
  corpus pipeline and `docs/specs/SPEC_privacy_architecture.md`.

## 7. Verification

- **Backend:** `pytest` (the `ios-app` suite: auth, devices, push) plus a smoke of
  `process_call_transcript` and the migration on an old-schema db. Confirm push
  fires for `critical`/`urgent` only after the enum port.
- **iOS:** build in **Xcode** via `ios/project.yml` (XcodeGen). Decode a sample
  `critical`/`urgent`/`routine`/`fyi` payload to confirm the ported `Severity` enum
  round-trips. This step needs a Mac with Xcode — cannot be verified from CI-less env.
- **De-id:** unit-test `redact()` on transcripts with known + residual identifiers;
  assert the token map re-identifies exactly.

## 8. Sequenced work

1. `reconcile/ios-plus-main` branch; `git merge origin/ios-app`.
2. Resolve the 5 conflicts (§4b).
3. Port the enum: `push.py`, `Call.swift`, `OrganicTheme.swift`, `CallDetailView.swift` (§4c).
4. `pytest` green; iOS builds in Xcode.
5. Add Presidio + `deident.py`; wire into the pipeline behind `DEIDENTIFY_TRANSCRIPTS` (§5).
6. Merge `CLAUDE.md` / `SECURITY.md` / `README.md` (§6).
7. PR into `main`.

## 9. Open decisions / risks

- **iOS build verification** needs Xcode on a Mac; the enum port can't be fully
  validated from this environment.
- **Auth overlap:** `ios-app`'s `app/auth.py` vs privacy-spec P2. Decide whether to
  keep it as-is now and align to P2 later, or rework during this reconciliation.
- **spaCy model size / setup:** `en_core_web_lg` is a ~500 MB download; add it to
  setup docs and CI, or start with `en_core_web_sm` and note the recall trade-off.
- **Presidio vs "rule-based":** the spec says "not an LLM"; Presidio is local ML, not
  an LLM API — satisfies the intent, but state this explicitly in `SECURITY.md`.
