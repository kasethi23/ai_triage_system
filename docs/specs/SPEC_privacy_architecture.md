# Spec: Privacy Architecture & Access Control

**Repo:** `kasethi23/ai_triage_system`
**Project:** MSE 401 Group 18 — EP call triage, partner WRHN
**Companion document:** `SPEC_synthetic_call_dataset.md` (Tasks 1–12).

---

> ## ⚠ This document supersedes Task 13 of the dataset spec
>
> Task 13 (de-identification) has been **removed** from `SPEC_synthetic_call_dataset.md`. If you are working from an older copy of that document, ignore its Amendment G entirely. It was written before three facts were established and following it produces the wrong system:
>
> - The build is **Concept B** (single-segment voicemail), not Concept A, so redaction cannot rely on structured intake unless intake is restructured first (Task P5).
> - **Twilio retains its own copy of every recording indefinitely.** Deleting local audio does not close that boundary (Task P8).
> - The API and console have **no authentication of any kind**, which is a prerequisite for audited re-identification (Tasks P2, P7).
>
> Mapping from the removed task to this document:
>
> | Removed | Here | Change |
> |---|---|---|
> | 13.1 Field-level separation | **P4** | Same, plus migration detail |
> | 13.2 Rule-based redaction | **P6** | Now two-stage, deterministic primary; flag defaults `true`; identifier extraction removed from the LLM schema |
> | 13.3 Audio retention | **P8** | Adds deletion of Twilio's retained copy |
> | 13.4 `SECURITY.md` | **P9** | Now structured around the trust-boundary table |
> | 13.5 Generated-data hygiene | **P10** | Unchanged |
> | — | **P1, P2, P3, P5, P7** | No prior equivalent |

**Relationship to the dataset spec.** These are independent workstreams. Task 3 of the dataset spec added `process_call_transcript`, so all 400 corpus records enter as text with no telephony involved. Nothing here blocks corpus generation or evaluation, and nothing there blocks this. They can proceed in parallel.

---

## 0. Current state, verified

Confirmed against commit `7af4f98` (PR #1 merged).

**Landed from the dataset spec:** severity enum renamed to `critical | urgent | routine | fyi`; `urgency` removed from the LLM schema and derived via `SEVERITY_TO_URGENCY`; `channel`, `no_callback`, `insufficient_detail` added; `_classify_and_store` refactored with `process_call_recording` and `process_call_transcript` sharing one path.

**Not addressed, and the subject of this spec:**

- `classification.py` still asks the LLM to extract `patient_name`, `room`, `caller_name`, `caller_role`. All four are in the schema's `required` list.
- `storage.py` writes all four into the same `calls` row as the verbatim transcript.
- No de-identification exists anywhere in the codebase.
- `main.py` sets `allow_origins=["*"]` with all methods and all headers.
- No route in `routes/calls.py` or `routes/voice.py` has any authentication dependency.
- Twilio webhooks are unauthenticated — no `X-Twilio-Signature` validation.
- Audio is written to `AUDIO_STORAGE_DIR` permanently, with no deletion path.
- Twilio retains its own copy of every recording indefinitely.
- No view-access logging. FR7 logs classifications and actions, not who read what.

**What is already correct:** `.gitignore` excludes `.env`, `*.db`, and `audio_recordings/`, so the repository is not currently leaking data.

---

## 1. Trust boundaries

Every point where data crosses from one control domain into another. A system is only as protected as its weakest crossing.

| # | Boundary | Data crossing | Far side controlled by | Control | Status |
|---|---|---|---|---|---|
| B1 | Caller → Twilio | Voice audio, spoken identifiers | Twilio (US region by default) | Deletion after download; residency review | **Gap — P8** |
| B2 | Twilio → app | Audio download, webhook POST | Shared | Signature validation | **Gap — P1** |
| B3 | App → transcription API | Raw audio | OpenAI | None possible; audio cannot be tokenised | **Gap — deferred** |
| B4 | App → classification API | Transcript text | OpenAI | Redaction before send | **Gap — P6** |
| B5 | App → disk | Transcript, identifiers, audio | Team | Identifier table split; audio deletion | **Gap — P4, P8** |
| B6 | App → physician console | Full PHI, re-identified | Physician (circle of care) | Auth; gated re-identification; view logging | **Gap — P2, P7** |
| B7 | App → exported corpus | Transcripts, labels | Team, public repo | Export excludes identifier table by construction | **Gap — P4** |
| B8 | App → team during development | Everything | Team | Synthetic data only (C1) | Procedural, acceptable |

**B6 is the boundary where PHI *should* flow freely.** The physician is an agent of the custodian acting within the circle of care; PHIPA does not ask you to hide patient data from the treating clinician. The control at B6 is not concealment — it is authentication, authorisation, and audit.

**B1 and B3 are the hardest.** Voice is biometric and cannot be tokenised, so no redaction protects the audio path. B1 is closable by deleting Twilio's copy; B3 is only closable by local transcription, which is deferred.

---

## 2. Decision required before P5 and P6

**The implementation is Concept B; the MOT report selects Concept A.** `routes/voice.py` plays a single SBAR greeting, records one continuous file, and hangs up. There is no conversational agent and no structured intake.

This is not only a documentation mismatch — it determines how hard redaction is:

- **With structured intake**, the patient name is a known string. Redaction becomes deterministic replacement of a known target: near-perfect recall, no model, a few dozen lines.
- **Without it**, every identifier must be discovered in free text. That is named-entity recognition — imperfect recall, and every miss is PHI reaching OpenAI at B4.

**Recommended resolution: multi-segment recording (P5).** It recovers most of Concept A's privacy property for a small change to `voice.py`, without building a conversational agent.

**Report honestly.** Multi-segment prompting erodes the "normal voicemail experience" argument the MOT report uses to motivate Concept B. Describe the change as a design evolution driven by the privacy analysis — a defensible position, and better than either leaving the mismatch or silently retconning it.

---

## Task P1 — Twilio webhook signature validation

`/voice/incoming` and `/voice/recording` accept any POST. Anyone who knows the URL can inject a fabricated `CallSid`, `From`, and `RecordingUrl` into the physician's queue.

Twilio signs every webhook with `X-Twilio-Signature`. The `twilio` package already in `requirements.txt` ships `RequestValidator`.

Implement as a FastAPI dependency applied to both routes: reconstruct the full public URL, read the raw form body, validate against the header using `TWILIO_AUTH_TOKEN`, return 403 on mismatch. Gate behind a `VALIDATE_TWILIO_SIGNATURE` config flag defaulting to `true`, with a documented local-development override — `seed_demo.py` and local testing must still work.

**Cheapest real security fix available. Do this first.**

## Task P2 — Console authentication

No route has any auth. `GET /calls` returns every call with full transcripts and patient names; `GET /calls/{id}/audio` serves any recording by integer ID, trivially enumerable; `GET /calls/stream` is a live PHI feed; `PATCH /calls/{id}/resolve` mutates state.

Implement single-user authentication:

- A login route issuing a signed session token (HTTP-only cookie or bearer token). Credentials from config, not hard-coded.
- A FastAPI dependency applied to **every** route in `routes/calls.py`.
- The SSE stream must authenticate at connection time — it is a continuous PHI feed and is easy to overlook.
- Frontend: a login view, token storage, and a 401 handler that returns to login.

Single-user is sufficient for the capstone. Multi-user identity, roles, and coverage-based access are documented in §Deferred, not built.

**Passkey / WebAuthn is optional and demos well.** If implemented, it is *authentication only*. It must not be the sole key to any encrypted data — key loss would mean unrecoverable health records, which conflicts with a custodian's retention obligations, and any escrow that fixes that also defeats the "only the physician can decrypt" property.

## Task P3 — CORS

Replace `allow_origins=["*"]` with the frontend origin from config. Restrict methods to those actually used (`GET`, `PATCH`, `POST`) and drop the wildcard on headers. Enable credentials if session cookies are used.

Trivial, and required for P2 to be meaningful.

## Task P4 — Identifier table split

**Highest value per unit of effort in this spec. Structural rather than defensive.**

Create `CallIdentifiers`, joined one-to-one on call ID, holding `patient_name`, `room`, `caller_name`, `caller_role`, and the redaction token map (JSON). Remove those four columns from `Call`.

Consequences:

- `calls` holds redacted transcript, labels, flags, timestamps. Safe to export, safe to commit.
- The labelled corpus exports with no identifiers **by construction**, not by remembering to strip them.
- `call_to_dict` no longer returns identifiers. A separate, authorised path does (P7).
- Add the new table to `init_db`; `_migrate_sqlite_columns` handles column additions only, so a table creation plus a data-migration step for existing rows is needed.

## Task P5 — Structured intake

Restructure `routes/voice.py` into a prompted sequence. Each `<Record>` carries its own `action` callback; the callback returns the next TwiML.

```
/voice/incoming  → <Gather numDigits=…>  "enter the bed or room number"
/voice/bed       → <Record action=/voice/name>  "state the patient's name"
/voice/name      → <Record action=/voice/narrative>  "describe the situation and what you need"
/voice/narrative → hang up; process all segments
```

**Bed and room by keypad, not speech.** `<Gather>` returns DTMF digits directly in the webhook — the number never becomes audio, never reaches Whisper, and never appears in a transcript. This also removes a genuine accuracy failure: Whisper mangles spoken digits, and "bed 512" versus "bed five twelve" is exactly the transcription error the corpus degradation script otherwise has to simulate.

**Only the narrative segment goes to the classifier.** The name segment is transcribed separately, stored in `CallIdentifiers`, and used as the redaction target for the narrative.

Set `channel` from the ingestion path as already designed. Keep segment audio files individually tracked so P8 can delete them.

**Caller experience is a real cost.** Keep prompts short. A nurse in a crisis is now navigating a three-step flow. Consider a documented bypass — a keypad option that skips straight to narrative recording for emergencies — and note that such a call yields no structured identifiers and must fall back to NER-based redaction.

## Task P6 — Redaction

`app/services/deident.py` exposing `redact(transcript: str, known: dict) -> tuple[str, dict]`, returning redacted text and the token map.

**Two-stage.**

*Stage 1 — deterministic (primary).* Given known identifiers from P5, replace exact and partial matches with stable tokens. For a patient named John Smith: `John Smith`, `Mr. Smith`, `Smith`, `John` → `[PATIENT_1]`. Case-insensitive, word-boundary aware. Near-perfect recall because the target is known.

*Stage 2 — residual heuristic (backstop).* Pattern-based detection of identifiers never captured as fields — a family doctor, a colleague, a relative — plus phone numbers, MRNs, dates and resolvable relative dates ("Tuesday", "yesterday"), and ages above 89. Stable tokens: `[PERSON_n]`, `[DATE_n]`, `[ID_n]`, `[AGE_90+]`.

**Rule-based only.** An LLM redactor would transmit the identifiers off-machine in order to remove them, defeating the purpose. Stage 2 has imperfect recall by nature; say so in the module docstring rather than implying a guarantee.

**Pipeline position is the whole point.** Redaction sits between transcription and classification:

```
audio → transcribe → REDACT → classify (redacted text only) → store
```

Anything added at storage time is useless; identifiers have already crossed B4.

`classify_transcript` receives redacted text. Classification quality is unaffected — every boundary test in `data/rubric.md` §2 turns on vital signs, trajectory, failed therapy, and whether a request was made. None involves a name.

**Remove `patient_name`, `room`, `caller_name`, `caller_role` from the classification JSON schema and its `required` list.** Under P5 these come from structured intake; asking the model to extract a name from text the name was just removed from is incoherent. This is a change to `classification.py` that P5 makes possible.

Gate behind `DEIDENTIFY_TRANSCRIPTS`, default `true` once P5 lands.

## Task P7 — Re-identification and view logging

The physician's experience must not change: they see "John Smith, bed 512", as today. What changes is that this becomes an explicit, authorised, logged join rather than an implicit consequence of one wide table.

**`reidentify(call_id, user)`** — fetches the call and its `CallIdentifiers` row, substitutes tokens back into the transcript, returns the full record. Requires an authenticated user (P2). Every invocation writes to `call_views`.

**`call_views` table:** call ID, user, timestamp, whether identifiers were revealed, and the route that triggered it.

**Route design:** `GET /calls` returns redacted records by default. A separate authorised endpoint returns the re-identified record for a single call. This makes the audit log meaningful — a physician opening one patient's detail is a different event from listing the queue.

PHIPA expects a custodian to answer *who accessed this record, and when.* FR7 currently logs classifications and physician actions, not views. This closes that.

## Task P8 — Audio retention

**Local disk.** `RETAIN_AUDIO` config flag, default `false`. Delete audio after successful transcription; clear `audio_path`. Provide a cleanup script for existing files.

**Twilio's copy — the gap that is easy to miss.** Twilio records to its own infrastructure and retains indefinitely. Downloading a copy does not remove theirs. After a successful download, delete the recording through the Twilio REST API. This is a single call and closes B1, which is more exposed than B3 because the recording sits at rest on a third party's storage rather than transiting an inference endpoint.

Note in `SECURITY.md`: Twilio recordings default to a US region, and Ontario health data residency expectations may apply. Twilio offers HIPAA-eligible configurations under a BAA; for PHIPA what matters is a written agreement with WRHN as custodian, not HIPAA specifically. Flag for the privacy office rather than resolving in code.

## Task P9 — `SECURITY.md`

Structured around the §1 boundary table, one section per boundary. Must state:

- What is stored, where, and for how long — audio (and its retention setting), verbatim transcript, redacted transcript, identifiers, token map, view log
- What leaves the machine and to whom — audio to Twilio and OpenAI, redacted transcript to OpenAI; both third-party processors; default regions
- Which controls are **implemented**, which are **designed but not built**, and which are **known gaps**
- That the prototype is not approved for real patient data (C1), and that NFR2 is currently satisfied procedurally as well as technically once P4 and P6 land
- Recommended production path: on-premise PBX integration with local transcription, so audio never leaves the hospital network

**Do not make a compliance claim.** PHIPA applies a reasonableness standard rather than an enumerated safe-harbour list, so sufficiency is a judgment for WRHN's privacy office and the university REB. The deliverable is a boundary description precise enough for them to assess. This document is a capstone deliverable in its own right and is the first thing a privacy office asks for.

## Task P10 — Generated-data hygiene

The partner scenario set names the attending physician throughout. Generated calls conditioned on those anchors will inherit the name, and generated data is committed to the repository.

Use a placeholder in all generation prompts, and assert in `scripts/generate_calls.py` that no output record contains the real name. One check, prevents a leak across 400 records.

Confirm `data/generated/` and `data/ratings/` contain no identifiers once P4 lands — after the table split this should hold by construction.

---

## Deferred — design and document, do not build

Record each in `SECURITY.md` with its rationale.

- **Local transcription** (`whisper.cpp` / `faster-whisper`). Closes B3. Does *not* close B1 — Twilio still receives the audio — so P8's deletion call matters more.
- **Self-hosted telephony** (Asterisk / FreeSWITCH). Closes B1 and B2 properly. Real scope creep, and not where this project's engineering contribution lies. Document as the production path.
- **Local classification.** Closes B4 entirely, but a local model applying the rubric's ordered boundary tests would be materially worse than `gpt-5-mini`. Redaction-before-classification is the better trade: keep the strong model, send it text with no identifiers.
- **Encryption at rest.** SQLite is a plaintext file. SQLCipher or filesystem encryption; note key management as the real problem.
- **Multi-user identity, roles, coverage rotation.** Who sees which physician's queue during handoff. The measured metadata shows service weeks handing off, so this is a genuine production requirement.
- **Key escrow.** Required if encryption is added, and the reason a passkey cannot be a sole decryption key.

## Order of work

**Immediate, independent, cheap:** P1 (Twilio signature), P3 (CORS), P10 (generation hygiene). Hours, not days.

**Structural:** P4 (identifier split). Everything downstream assumes it. P2 (auth) is a prerequisite for P7.

**Sequenced:** P5 (intake) → P6 (redaction), since deterministic redaction depends on structured capture. If the team declines P5, P6 still ships as stage 2 only, with imperfect recall stated plainly in `SECURITY.md`.

**Then:** P7 (re-identification and view logging), P8 (retention).

**Last:** P9 (`SECURITY.md`), written once the implemented/designed/gap split is settled.

## Constraints

- All data remains synthetic (C1). None of this binds legally today; the claim is *designed for PHIPA, validated on synthetic data* — not compliance.
- The physician is inside the circle of care. Do not design controls that withhold clinical data from the treating clinician; design controls that authenticate, authorise, and audit their access.
- No control in this spec may degrade classification quality. If redaction changes a label, the redaction is wrong, not the rubric.
