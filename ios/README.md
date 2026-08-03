# ClinRoute iOS — First-Time Setup & Running in the Simulator

Zero-to-running guide. Total time on a fresh Mac: ~10 minutes (plus Xcode
download if you don't have it).

## 1. Prerequisites (one-time)

| Tool | Install | Check |
| --- | --- | --- |
| Xcode 15+ | Mac App Store, then open it once to finish setup | `xcodebuild -version` |
| XcodeGen | `brew install xcodegen` | `xcodegen --version` |
| Python venv | see repo root `README.md` Setup section | `./venv/bin/python -m pytest` |

If `xcodebuild` complains about a developer directory, run:

```bash
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
```

## 2. Start the backend (the app needs it)

From the repo root:

```bash
./venv/bin/uvicorn app.main:app --port 8000
```

Leave this running. Sanity check in another terminal: `curl
http://localhost:8000/calls` should return JSON (the repo's `app.db` ships
with demo calls and voicemail recordings, so there's data out of the box).

With `API_BEARER_TOKEN` unset, the backend runs in open local-dev mode and
the app's default empty token in `ClinRoute/Config.swift` just works — no
config needed for a first run.

## 3. Generate the Xcode project

The `.xcodeproj` is generated, never committed. From `ios/`:

```bash
xcodegen generate
```

Re-run this any time you add/remove files or edit `project.yml`.

## 4. Build, install, and launch in the simulator

**Option A — Xcode (easiest):**

```bash
open ClinRoute.xcodeproj
```

Pick an iPhone simulator in the toolbar's device menu, press **Cmd-R**.
Done — skip to step 5.

**Option B — command line only:**

```bash
# List available iPhone simulators and pick one (copy its UDID):
xcrun simctl list devices available | grep iPhone

# Boot it and open the Simulator app:
xcrun simctl boot <UDID>
open -a Simulator

# Build:
xcodebuild -project ClinRoute.xcodeproj -scheme ClinRoute \
  -destination "id=<UDID>" build CODE_SIGNING_ALLOWED=NO

# Install + launch (path comes from Xcode's DerivedData):
APP=$(find ~/Library/Developer/Xcode/DerivedData \
  -path "*ClinRoute*/Build/Products/Debug-iphonesimulator/ClinRoute.app" | head -1)
xcrun simctl install <UDID> "$APP"
xcrun simctl launch <UDID> com.clinroute.console
```

Tap **Allow** on the notification-permission prompt at first launch.

## 5. Using the simulator (read this if it's your first time)

- **Your mouse is the finger.** To scroll, **click, hold, and drag** the
  content up or down, then release. Two-finger trackpad scrolling over the
  Simulator window is unreliable — if the app "won't scroll", this is almost
  always why.
- **Home**: Cmd-Shift-H. **Lock screen**: Cmd-L. **Rotate**: Cmd-←/→.
- **Sound** comes out of your Mac speakers. If Play voicemail is silent,
  check your Mac volume and the Simulator menu **I/O → Audio Output**.
- The simulator keeps the app installed between reboots; re-run step 4 only
  after code changes.

## 6. What to try

1. The inbox groups unresolved calls by urgency (critical / urgent /
   routine & FYI), oldest first. Tap a row for the detail view.
2. **Play voicemail** streams the real recording from the backend.
3. **Resolve** syncs to the backend (verify with `curl
   http://localhost:8000/calls | jq '.[].resolved'`) and recounts the badge.
4. Simulate a critical push (deep-links to call 3 when tapped):

   ```bash
   cat > /tmp/push.json <<'EOF'
   {
     "aps": {
       "alert": {"title": "CRITICAL: Mr. Reeves", "body": "412 — Chest pain, needs callback now"},
       "sound": "default", "badge": 1,
       "thread-id": "severity-critical", "interruption-level": "time-sensitive"
     },
     "call_id": 3
   }
   EOF
   xcrun simctl push booted com.clinroute.console /tmp/push.json
   ```

   Try it with the app foregrounded (banner over the app), backgrounded
   (Cmd-Shift-H first), and on the lock screen (Cmd-L first). Tapping the
   notification opens the matching call. Full push-testing script, including
   real-device APNs: `TESTING.md`.

## 7. Run the tests

```bash
# Backend (repo root):
./venv/bin/python -m pytest

# iOS UI tests (ios/, backend must be running, simulator booted):
xcodebuild test -project ClinRoute.xcodeproj -scheme ClinRoute \
  -destination "id=<UDID>" CODE_SIGNING_ALLOWED=NO
```

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| App shows "Could not connect" / empty inbox | Backend not running, or `Config.swift` baseURL isn't `http://localhost:8000` |
| 401 errors in the app | Backend has `API_BEARER_TOKEN` set but `Config.swift` `bearerToken` doesn't match |
| Won't scroll | Click-drag, don't trackpad-scroll (see step 5) |
| No push banner from `simctl push` | Notification permission was denied — delete the app in the simulator, relaunch, tap Allow |
| `xcodegen: command not found` | `brew install xcodegen`, or `/opt/homebrew/bin/xcodegen` directly |
| Build fails after pulling new files | Re-run `xcodegen generate` |
