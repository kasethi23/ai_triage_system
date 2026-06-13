# Conduit - Clinical Call Triage Demo

FastAPI backend that answers a phone call via Twilio, records an SBAR-format
voicemail, transcribes it (OpenAI Whisper), classifies it (OpenAI structured
output), stores it, and streams new calls to the Conduit Physician Console
dashboard over SSE.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Environment variables live in `.env` (already populated):

- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`
- `OPENAI_API_KEY`
- `OPENAI_TRANSCRIPTION_MODEL` (default `whisper-1`)
- `OPENAI_CLASSIFICATION_MODEL` (default `gpt-5-mini`)
- `DATABASE_URL` (default `sqlite:///./app.db`)
- `AUDIO_STORAGE_DIR` (default `./audio_recordings`)

## Run the server

```bash
uvicorn app.main:app --reload --port 8000
```

## Expose it to Twilio with ngrok

Twilio needs a public URL to reach your local server.

```bash
ngrok http 8000
```

ngrok will print a forwarding URL like `https://abc123.ngrok-free.app`.

In the [Twilio Console](https://console.twilio.com/) -> Phone Numbers ->
Manage -> Active Numbers -> select `+14374250323` -> under "Voice
Configuration", set:

- **A call comes in**: Webhook, `https://abc123.ngrok-free.app/voice/incoming`, HTTP POST

That's the only webhook you need to configure manually. Twilio's `<Record>`
verb's `action` is set to the relative path `/voice/recording`, which Twilio
resolves against the same ngrok host automatically.

Call the Twilio number, leave a message, hang up — within a few seconds a
new row appears via `GET /calls` and on the `GET /calls/stream` SSE feed.

## Endpoints

| Method | Path                  | Purpose                                              |
| ------ | --------------------- | ----------------------------------------------------- |
| POST   | `/voice/incoming`      | Twilio webhook — greeting + record                    |
| POST   | `/voice/recording`     | Twilio webhook — transcribe, classify, store, broadcast |
| GET    | `/calls`               | Recent calls, newest first                            |
| GET    | `/calls/stream`        | SSE stream of new `Call` events                       |
| GET    | `/calls/{id}/audio`    | Stream the stored audio file                          |
| PATCH  | `/calls/{id}/resolve`  | Mark a call as handled                                |

## Frontend - Conduit Physician Console

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

The frontend calls the API at whatever hostname the page was loaded from,
on port 8000 (see `frontend/src/lib/api.ts`). This makes the LAN setup below
work without any config changes.

## Viewing the dashboard on your phone (same WiFi)

To open the console in Safari on your phone, both servers need to be
reachable on your local network, not just `localhost`.

1. Find your Mac's LAN IP:

   ```bash
   ipconfig getifaddr en0
   ```

   This prints something like `192.168.2.76`. It can change if you
   reconnect to WiFi, so re-run this if the phone can't connect.

2. Start the backend bound to all interfaces:

   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

3. Start the frontend with `--host` so Vite also binds to all interfaces:

   ```bash
   cd frontend
   npm run dev -- --host --port 5173
   ```

4. On your phone (connected to the same WiFi as your Mac), open Safari to:

   ```
   http://<your-mac-lan-ip>:5173
   ```

   e.g. `http://192.168.2.76:5173`.

If macOS prompts to allow incoming network connections for `node` or
`Python` the first time, click **Allow**.

> Note: the ngrok tunnel used for Twilio webhooks (port 8000) is independent
> of this and keeps working the same way whether or not the backend is bound
> to `0.0.0.0`.

## Testing without dialing the number

Use `scripts/seed_demo.py` to run the full transcription + classification +
storage pipeline against a local audio file:

```bash
python scripts/seed_demo.py path/to/sample_message.wav --from-number "+15551234567"
```

This writes a new `Call` row to the same sqlite database the server uses, so
it shows up immediately in `GET /calls`. (It won't appear on the live
`/calls/stream` SSE feed, since that's an in-memory pub/sub local to the
running server process.)

## curl cheat sheet

Start the server first (`uvicorn app.main:app --reload --port 8000`), then:

```bash
# 1. See the TwiML returned for an incoming call
curl -s -X POST http://localhost:8000/voice/incoming

# 2. List recent calls
curl -s http://localhost:8000/calls | jq

# 3. Tail the SSE stream (leave running in another terminal)
curl -N http://localhost:8000/calls/stream

# 4. Fetch audio for call id 1
curl -s http://localhost:8000/calls/1/audio -o call_1.wav

# 5. Seed a demo call from a local audio file
python scripts/seed_demo.py sample.wav --from-number "+15555550123"
```

> Note: `/voice/recording` is only useful when called by Twilio (it expects
> a real `RecordingUrl` it can download with your Twilio credentials). Use
> `scripts/seed_demo.py` to exercise the transcription/classification
> pipeline directly with a local file.
