# Security & data handling

ClinRoute processes clinical voicemails for an on-call electrophysiology
attending. This document describes what data the prototype stores, where, and for
how long; what crosses to third parties; and which privacy controls are
**implemented**, **designed but not enabled**, or a **known gap**.

> **Not approved for real patient data.** The prototype runs on synthetic data
> only (constraint C1). NFR2 ("avoid patient-identifiable information") is
> satisfied *procedurally* by feeding it only synthetic data, and — with P4 and P6
> below — *technically* as well. This document is a boundary description for
> WRHN's privacy office and the university REB to assess; it is **not** a
> compliance claim. Ontario is governed by PHIPA, which applies a reasonableness
> standard rather than an enumerated safe-harbour list, so sufficiency is their
> judgment, not ours.

Control status legend: ✅ implemented · ◐ designed, not enabled by default · ✗ gap.

## Trust boundaries

Every point where data crosses from one control domain into another.

| # | Boundary | Data crossing | Control | Status |
|---|---|---|---|---|
| B1 | Caller → Twilio | Voice audio, spoken identifiers | Twilio's retained copy deleted via REST after download (P8) | ✅ |
| B2 | Twilio → app | Webhook POST, audio download | `X-Twilio-Signature` validation (P1) | ✅ |
| B3 | App → transcription API | Raw audio | None possible — audio can't be tokenised. Local Whisper would close it | ✗ (deferred) |
| B4 | App → classification API | Transcript text | Redaction before send (P6) | ◐ |
| B5 | App → disk | Transcript, identifiers, audio | Identifier-table split (P4); audio deleted after transcription (P8) | ✅ / ◐ |
| B6 | App → physician console | Full PHI, re-identified | Bearer auth (P2); gated, logged re-identification (P7) | ✅ |
| B7 | App → exported corpus | Transcripts, labels | Identifiers live in a separate table — export is clean by construction (P4) | ✅ |
| B8 | App → team in development | Everything | Synthetic data only (C1) | procedural |

**B6 is where PHI *should* flow.** The physician is inside the circle of care;
PHIPA does not ask us to hide patient data from the treating clinician. The
control there is authentication, authorisation, and audit — not concealment.

**B1 and B3 are the hardest** — voice is biometric and cannot be tokenised, so no
redaction protects the audio path. B1 is closed by deleting Twilio's copy; B3 is
only closed by local transcription (deferred; see Production path).

## What is stored, where, how long

| Data | Location | Retention |
|---|---|---|
| Raw call audio | disk (`AUDIO_STORAGE_DIR`; `/data/audio_recordings` on Railway) | **Deleted after successful transcription** unless `RETAIN_AUDIO=true` (P8) |
| Verbatim transcript | `calls.transcript` (SQLite) | Persisted. **Redacted** when `DEIDENTIFY_TRANSCRIPTS=true` (P6); otherwise still contains names |
| Labels / flags / summary | `calls` row | Persisted; **no identifiers** in this table by construction (P4) |
| Identifiers + token map | `call_identifiers` table (joined 1:1) | Persisted, separate from `calls` (P4) |
| Identity-access log | `call_views` table | Persisted — who re-identified which call, and when (P7) |
| Device push tokens | `devices` table | Opaque APNs ids; deleted on `DELETE /devices/{token}` and on `BadDeviceToken`/`Unregistered` |

## What leaves the machine, to whom

| Destination | Data | Region |
|---|---|---|
| Twilio | Call audio + caller phone number (then Twilio's copy is deleted, P8) | US by default |
| OpenAI (Whisper) | Full call **audio** — cannot be de-identified (B3) | provider default |
| OpenAI (classifier) | Transcript text — **redacted** when P6 is enabled (B4) | provider default |
| Apple (APNs) | Minimized push payload only (below) | Apple |

Twilio recordings default to a US region; Ontario health-data residency
expectations may apply. Twilio offers HIPAA-eligible configurations under a BAA;
for PHIPA what matters is a written agreement with WRHN as custodian. **Flag for
the privacy office — not resolved in code.**

## Push payload minimization

Push payloads travel through Apple's servers and can persist in a locked device's
notification center. A payload contains ONLY: severity (+ display label), patient
name as stored, room, the one-line summary (≤150 chars), badge count, and the
internal `call_id`. Never transcripts, caller identity, phone numbers, audio URLs,
or raw classification JSON. Enforced in one place — `app/services/push.py::build_message`
— and tested in `tests/test_push.py`.

## Auth (P2)

- **JSON API + SSE** (`/calls*`, `/devices*`, `/calls/stream`): static bearer
  token (`API_BEARER_TOKEN`), `Authorization: Bearer <token>`. SSE may use
  `?token=` (EventSource can't set headers). Unset token → unauthenticated allowed
  in local dev with a loud warning, **refused in production** (`RAILWAY_ENVIRONMENT`).
- **Twilio webhooks** (`/voice/*`): `X-Twilio-Signature` validation (P1).
- **CORS** (P3): locked to `FRONTEND_ORIGINS`, not a wildcard.

## De-identification (P6)

`app/services/deident.py` redacts the transcript **between transcription and
classification** (`transcribe → redact → classify`), so identifiers never cross to
the classifier (B4). It runs a **local** spaCy model (Presidio) — nothing leaves
the machine, and it is **not** an LLM pass. Two stages: deterministic (known
identifiers, e.g. the keypad room) + residual heuristic (person names, phones,
dates, MRN, ages > 89). Stable, reversible tokens; the map lives in
`call_identifiers` and is reversed only by the authorised, logged path (P7).

**Recall is imperfect by design** — it is a defence-in-depth layer for a
synthetic-data prototype, pinned to the small `en_core_web_sm` model. It is **not**
a certified de-identification pipeline. Gated behind `DEIDENTIFY_TRANSCRIPTS`
(default off); enable it, and swap in `en_core_web_lg` or a transformer model, for
any non-synthetic use.

## Structured intake (P5)

`voice.py` captures the bed/room by **keypad (DTMF)**, so the room never becomes
audio, never reaches Whisper, and is exact. The rest is a single voicemail; the
name in it is handled by redaction. An emergency bypass (press ★) skips straight to
recording — such calls carry no structured room and fall back to NER redaction.

## Logging

Full transcripts and push payloads are never logged at INFO — DEBUG only.
INFO carries ids and counts, not clinical content.

## Deferred / production path

- **Local transcription** (`whisper.cpp` / `faster-whisper`) — the single strongest
  claim available: audio would never leave the machine, closing B3. Recommended
  production path. Does *not* close B1 (Twilio still receives audio), so P8's
  deletion still matters.
- **Self-hosted telephony** (Asterisk / FreeSWITCH) — closes B1/B2 properly; real
  scope creep, documented as the production direction.
- **Encryption at rest** — SQLite is a plaintext file; SQLCipher or filesystem
  encryption, with key management as the real problem.
- **Multi-user identity, roles, coverage rotation** — single-user auth today; who
  sees which physician's queue during handoff is a production requirement.
