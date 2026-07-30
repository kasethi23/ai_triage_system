# ClinRoute (Conduit) — Clinical Call Triage

AI triage for after-hours clinical calls: Twilio records a voicemail, Whisper
transcribes it, an LLM classifies severity, and the system alerts the on-call
physician — SSE to the React web console, APNs push to the iOS app.

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
                                                 |- foreground: refresh on scenePhase/banner
```

## Severity + push policy

The canonical severity enum (classifier schema, `frontend/src/types.ts`,
`models.py`) is CTAS-style: `severe | emergent | semi-urgent | non-urgent`.
Product-facing labels map severe→Critical, emergent→Urgent, semi-urgent→
Routine, non-urgent→FYI (used in push titles and the iOS UI).

Push policy — implemented exactly once, in `app/services/push.py`:

| severity | APNs behavior |
| --- | --- |
| severe (Critical) | push, `interruption-level: time-sensitive`, distinct sound |
| emergent (Urgent) | push, `interruption-level: time-sensitive`, default sound |
| semi-urgent (Routine) | no push |
| fyi / non-urgent | no push |

`severe` is designed to upgrade to Apple's `critical` interruption level once
that entitlement is granted — isolated in `push.py::SEVERE_INTERRUPTION_LEVEL`.
Push payloads are minimized (severity, patient name, room, summary only) —
see `SECURITY.md`. Push dispatch is hooked into
`storage.process_call_recording` and can never break call ingestion.

## API

Bearer auth (`API_BEARER_TOKEN`) on everything except `/voice/*`, which uses
Twilio `X-Twilio-Signature` validation instead. Unset token = allowed in
local dev with a warning, refused in production (`RAILWAY_ENVIRONMENT` set).
SSE also accepts `?token=` (EventSource can't set headers).

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/voice/incoming`, `/voice/recording` | Twilio webhooks |
| GET | `/calls`, `/calls/{id}`, `/calls/{id}/audio` | Read calls |
| GET | `/calls/stream` | SSE feed of new calls |
| PATCH | `/calls/{id}/resolve` | Mark handled |
| POST | `/devices` | Register iOS push token (idempotent upsert) |
| DELETE | `/devices/{token}` | Unregister |
| POST | `/devices/test-push` | Dev/demo: force a push of a chosen severity |

## Conventions

- **Migrations:** any new column/table goes in BOTH `app/models.py` AND
  `app/database.py::_migrate_sqlite_columns`. This now covers `Device` as
  well as `Call`.
- **API contract:** `frontend/src/types.ts` is canonical. The Swift models
  in `ios/ClinRoute/Models/Call.swift` mirror it exactly (snake_case handled
  by `.convertFromSnakeCase`) — don't invent new shapes.
- **Logging:** never log transcripts or push payloads at INFO; DEBUG only.
- **Scope guards:** don't modify `scripts/` or the classifier prompt/schema
  (separate eval workstream). No settings screen, analytics, or Android in
  the iOS app; no third-party iOS dependencies.

## Backend dev

```bash
source venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
python -m pytest                     # run before declaring any change done
```

Every new backend behavior gets a pytest test (`tests/`).

## iOS build

```bash
brew install xcodegen                # once
cd ios
xcodegen generate                    # project.yml -> ClinRoute.xcodeproj (gitignored)
xcodebuild -project ClinRoute.xcodeproj -scheme ClinRoute \
  -destination 'generic/platform=iOS Simulator' build CODE_SIGNING_ALLOWED=NO
```

Backend URL + bearer token live in `ios/ClinRoute/Config.swift` (Settings
screen is intentionally out of scope). Bundle id `com.clinroute.console` is
set in one place in `ios/project.yml` and must match `APNS_BUNDLE_ID`.
Manual push test script: `ios/TESTING.md`.

## Deployment (Railway)

`Procfile` runs uvicorn; attach a volume at `/data` (SQLite + audio default
there when `RAILWAY_ENVIRONMENT` is present). Env vars — full table in
`README.md`:

- Required in prod: `API_BEARER_TOKEN`, `TWILIO_ACCOUNT_SID`,
  `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`, `OPENAI_API_KEY`
- Push: `APNS_KEY_BASE64` (base64 of the .p8), `APNS_KEY_ID`,
  `APNS_TEAM_ID`, `APNS_BUNDLE_ID`, `APNS_USE_SANDBOX`
- Optional: `DATABASE_URL`, `AUDIO_STORAGE_DIR`, `OPENAI_*_MODEL`

Security & data-handling reference: `SECURITY.md`.
