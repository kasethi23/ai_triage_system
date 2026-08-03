# ClinRoute - Clinical Call Triage

FastAPI backend that answers a phone call via Twilio, records an SBAR-format
voicemail, transcribes it (OpenAI Whisper), classifies it (OpenAI structured
output), stores it, streams new calls to the React Physician Console over
SSE, and pushes critical/urgent calls to the on-call physician's iPhone via
APNs (see `ios/`).

## Setup (local dev)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

Run the tests with `python -m pytest`.

## Environment variables

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `TWILIO_ACCOUNT_SID` | yes | — | Twilio API auth (recording download) |
| `TWILIO_AUTH_TOKEN` | yes | — | Twilio API auth + webhook signature validation |
| `TWILIO_PHONE_NUMBER` | yes | — | The inbound number |
| `OPENAI_API_KEY` | yes | — | Whisper + classification |
| `OPENAI_TRANSCRIPTION_MODEL` | no | `whisper-1` | Transcription model |
| `OPENAI_CLASSIFICATION_MODEL` | no | `gpt-5-mini` | Classification model |
| `API_BEARER_TOKEN` | prod: yes | unset (dev-allow) | Bearer token for `/calls*`, `/devices*`, SSE. Unset = open access in local dev only; production refuses to serve without it |
| `DATABASE_URL` | no | `sqlite:///./app.db` (dev), `sqlite:////data/app.db` (Railway) | SQLAlchemy URL |
| `AUDIO_STORAGE_DIR` | no | `./audio_recordings` (dev), `/data/audio_recordings` (Railway) | Audio file storage |
| `APNS_KEY_BASE64` | for push | — | Base64 of the APNs `.p8` auth key (`base64 -i AuthKey_XXX.p8`) |
| `APNS_KEY_ID` | for push | — | APNs key id (10 chars) |
| `APNS_TEAM_ID` | for push | — | Apple developer team id |
| `APNS_BUNDLE_ID` | no | `com.clinroute.console` | APNs topic / iOS bundle id |
| `APNS_USE_SANDBOX` | no | `true` | `true` for dev/TestFlight-dev builds, `false` for production APNs |

Push policy (single source of truth in `app/services/push.py`): `severe` →
time-sensitive push with distinct sound, `emergent` → time-sensitive push
with default sound, `semi-urgent` / `non-urgent` → no push. See `SECURITY.md`
for what data is allowed in a push payload.

## Deploy to Railway

1. Create a Railway service from this repo. The `Procfile` runs
   `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
2. Attach a **volume mounted at `/data`** — SQLite and audio default there in
   production (`RAILWAY_ENVIRONMENT` is set by Railway automatically).
3. Set the env vars above. `API_BEARER_TOKEN` and `TWILIO_AUTH_TOKEN` are
   mandatory in production; the server hard-fails requests if they're unset.
4. In the [Twilio Console](https://console.twilio.com/) → Phone Numbers →
   Active Numbers → your number → Voice Configuration, set **A call comes
   in** to `https://<your-app>.up.railway.app/voice/incoming` (HTTP POST).
   The `/voice/recording` action resolves against the same host automatically.
5. Call the number, leave a message, hang up — the call appears in
   `GET /calls`, on the SSE stream, and (if severe/emergent) as a push on
   registered iPhones.

## iOS app quickstart

The native app lives in `ios/`. It is notification-first: critical/urgent
calls reach the locked phone via APNs time-sensitive push.

**First time?** Follow the step-by-step guide in **`ios/README.md`** — it
covers prerequisites, starting the backend, generating the project, running
in the simulator (including how to scroll and test pushes), and
troubleshooting.

Short version:

```bash
brew install xcodegen        # once
cd ios
xcodegen generate            # produces ClinRoute.xcodeproj (gitignored)
open ClinRoute.xcodeproj     # pick an iPhone simulator, Cmd-R
```

Set the backend URL and bearer token in `ios/ClinRoute/Config.swift` when
targeting a deployed backend (local dev works with the defaults). Real APNs
push requires physical hardware; the simulator tests payload handling via
`xcrun simctl push` — see `ios/TESTING.md`.

## Endpoints

All routes except `/voice/*` require `Authorization: Bearer $API_BEARER_TOKEN`
(the SSE stream also accepts `?token=`). Twilio webhooks are authenticated by
`X-Twilio-Signature` validation instead.

| Method | Path | Purpose |
| ------ | --------------------- | ----------------------------------------------------- |
| POST | `/voice/incoming` | Twilio webhook — greeting + record |
| POST | `/voice/recording` | Twilio webhook — transcribe, classify, store, broadcast, push |
| GET | `/calls` | Recent calls, newest first |
| GET | `/calls/stream` | SSE stream of new `Call` events |
| GET | `/calls/{id}` | Single call |
| GET | `/calls/{id}/audio` | Stream the stored audio file |
| PATCH | `/calls/{id}/resolve` | Mark a call as handled |
| POST | `/devices` | Register an iOS push token (idempotent upsert) |
| DELETE | `/devices/{token}` | Unregister a push token |
| POST | `/devices/test-push` | Dev/demo: send a push of a chosen severity to all devices |

## Frontend - ClinRoute Physician Console

A single-page React + TypeScript dashboard lives in `frontend/`. It expects
the API at `http://localhost:8000` (CORS is enabled on the backend for this).

```bash
cd frontend
npm install
npm run dev
```

Open the printed local URL (e.g. `http://localhost:5173`). It loads recent
calls via `GET /calls`, then subscribes to `GET /calls/stream` for live
updates. Severity badges (Severe / Emergent / Semi-Urgent / Non-Urgent) and
patient/room/caller fields come from the classification step.

## Testing without dialing the number

Use `scripts/seed_demo.py` to run the full transcription + classification +
storage pipeline against a local audio file:

```bash
python scripts/seed_demo.py path/to/sample_message.wav --from-number "+15551234567"
```

This writes a new `Call` row to the same sqlite database the server uses, so
it shows up immediately in `GET /calls`, and dispatches a push if the call
classifies as severe/emergent. (It won't appear on the live `/calls/stream`
SSE feed, since that's an in-memory pub/sub local to the running server
process.)

To send a deterministic demo push without relying on the classifier:

```bash
curl -s -X POST "$BASE/devices/test-push" \
  -H "Authorization: Bearer $API_BEARER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"severity": "severe"}'
```

## curl cheat sheet

Start the server first (`uvicorn app.main:app --reload --port 8000`), then
(`export TOKEN=...` to match your `API_BEARER_TOKEN`, or omit the header in
tokenless local dev):

```bash
# 1. See the TwiML returned for an incoming call
curl -s -X POST http://localhost:8000/voice/incoming

# 2. List recent calls
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/calls | jq

# 3. Tail the SSE stream (leave running in another terminal)
curl -N "http://localhost:8000/calls/stream?token=$TOKEN"

# 4. Fetch audio for call id 1
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/calls/1/audio -o call_1.wav

# 5. Register a device token
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"token": "abc123"}' http://localhost:8000/devices

# 6. Seed a demo call from a local audio file
python scripts/seed_demo.py sample.wav --from-number "+15555550123"
```

> Note: `/voice/recording` is only useful when called by Twilio (it expects
> a real `RecordingUrl` it can download with your Twilio credentials). Use
> `scripts/seed_demo.py` to exercise the transcription/classification
> pipeline directly with a local file.
