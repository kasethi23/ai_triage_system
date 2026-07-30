# Security & Data Handling

ClinRoute (internally "Conduit") processes clinical voicemails. This document
records what data leaves the server, what is stored where, how the API is
authenticated, and the payload-minimization rule for push notifications.

## What leaves the server

| Destination | Data sent | Why |
| --- | --- | --- |
| Twilio | Call audio (recorded and downloaded via Twilio's API); caller phone number | Telephony provider — records the voicemail |
| OpenAI | Full call audio (Whisper transcription); full transcript (classification) | Transcription + severity classification |
| Apple (APNs) | **Minimized push payload only**: severity, patient name as stored, room, one-line summary (max 150 chars), badge count, internal `call_id` | Alerting the on-call physician's iPhone |

## Push payload minimization rule

Push payloads travel through Apple's servers and can persist on a locked
device's notification center. A payload must contain ONLY:

- severity (and its display label)
- patient name **as already stored** (first name / initials per upstream policy)
- room
- the one-line summary, truncated to 150 characters
- badge count and the internal numeric `call_id`

Never include: transcripts, caller name/role, phone numbers, audio URLs, or
raw classification JSON. This rule is implemented in one place —
`app/services/push.py::build_message` — and enforced by tests in
`tests/test_push.py`.

## What is stored where

| Location | Data |
| --- | --- |
| SQLite (`DATABASE_URL`; `/data/app.db` on Railway) | Call rows: transcript, classification, patient/caller fields, resolved flag; device push tokens |
| Disk (`AUDIO_STORAGE_DIR`; `/data/audio_recordings` on Railway) | Raw call audio (WAV) |
| iOS device | Nothing persisted by the app beyond the notification center entries; call data is fetched live over TLS |

Device push tokens are opaque APNs identifiers, not personal data; rows are
deleted on `DELETE /devices/{token}` and pruned automatically when APNs
reports `BadDeviceToken` / `Unregistered`.

## Auth model

- **JSON API + SSE** (`/calls*`, `/devices*`, `/calls/stream`): static bearer
  token (`API_BEARER_TOKEN` env var), sent as `Authorization: Bearer <token>`.
  SSE clients may use the `?token=` query parameter (EventSource cannot set
  headers). If the token is unset, the server allows unauthenticated access
  for local dev with a loud warning — but refuses to serve unauthenticated in
  production (`RAILWAY_ENVIRONMENT` present).
- **Twilio webhooks** (`/voice/*`): validated via `X-Twilio-Signature`
  request-signature verification using `TWILIO_AUTH_TOKEN`. Same dev/prod
  policy as above.
- **APNs**: token-based (`.p8`) auth; the key is provided base64-encoded via
  `APNS_KEY_BASE64` and materialized to a temp file at runtime.

## Logging policy

Full transcripts and full push payloads are never logged at INFO level —
DEBUG only. INFO-level logs carry ids and counts, not clinical content.
