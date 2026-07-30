# ClinRoute iOS — Manual Push Test Script

Two levels: (a) simulator payload tests that need no backend or Apple
account, and (b) the end-to-end locked-phone demo against a deployed
backend.

## Prerequisites

```bash
brew install xcodegen
cd ios && xcodegen generate
```

Set `Config.baseURL` / `Config.bearerToken` in `ios/ClinRoute/Config.swift`
to match the target backend, then build & run once so the app can request
notification permission (tap **Allow**).

## (a) Simulator payload test — `xcrun simctl push`

Works in the iOS Simulator; exercises payload rendering, sounds, badge, and
the tap→deep-link path without APNs.

1. Run the app in a simulator, note the booted device, then background the
   app (Cmd-Shift-H).
2. Create `push.json` (this mirrors exactly what `app/services/push.py`
   sends for a `severe` call — `call_id` must exist on the backend the app
   points at; use an id from `GET /calls`):

   ```json
   {
     "aps": {
       "alert": {
         "title": "CRITICAL: Jane D.",
         "body": "ICU 3 — Chest pain, hypotensive, needs immediate callback"
       },
       "sound": "default",
       "badge": 1,
       "thread-id": "severity-severe",
       "interruption-level": "time-sensitive"
     },
     "call_id": 1
   }
   ```

3. Push it:

   ```bash
   xcrun simctl push booted com.clinroute.console push.json
   ```

4. Verify: banner appears (even with the simulated device "locked" via
   Cmd-L), app badge shows 1, and tapping the banner opens the app directly
   on the Call Detail view for `call_id`.

Repeat with `"interruption-level"` removed and title `URGENT: ...` to spot-
check the emergent shape.

## (b) End-to-end: locked phone → deployed backend → time-sensitive push

Requires: backend deployed (Railway) with `APNS_*` env vars set
(`APNS_USE_SANDBOX=true` for a debug build), and the app installed on a
**physical iPhone** (simulators can't receive real APNs).

1. Build & run on the phone with `Config.baseURL` pointing at the deployed
   backend. On first launch accept the notification prompt — the app
   registers its token via `POST /devices` on every launch. Confirm a row
   exists:

   ```bash
   curl -s -H "Authorization: Bearer $TOKEN" $BASE/calls   # sanity: API up
   ```

2. Lock the phone.
3. Trigger a critical call. Deterministic path (no classifier involved):

   ```bash
   curl -s -X POST "$BASE/devices/test-push" \
     -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d '{"severity": "severe"}'
   ```

   Full-pipeline path (audio → Whisper → classifier → store → push), run
   against the deployed backend's database, with a recording that describes
   a life-threatening situation so it classifies as `severe`:

   ```bash
   DATABASE_URL=<deployed-db-or-railway-run> python scripts/seed_demo.py critical_sample.wav
   ```

   (On Railway, run it inside the service: `railway run python
   scripts/seed_demo.py ...` so it shares the `/data` volume and APNs env.)

4. Verify on the locked phone: the push arrives as **time-sensitive**
   (breaks through Focus, lights the screen), title `CRITICAL: <patient>`.
5. Tap the notification → app opens directly on the correct Call Detail
   view (deep link via the payload's `call_id`; the detail fetches the call
   even if the list hasn't loaded).
6. Tap **Resolve** → confirm the call flips to Resolved in the React web
   console (refresh `GET /calls` or watch the SSE-driven dashboard).
7. Negative check: `POST /devices/test-push` with `{"severity":
   "semi-urgent"}` and `{"severity": "non-urgent"}` must produce **no**
   push (response shows `"would_push": false`).

## Badge

The badge equals the unresolved severe+emergent count. It is set by the
server in each push payload and re-synced by the app on every list refresh
and resolve.
