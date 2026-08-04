# ClinRoute — 10-Minute Demo Run-of-Show

Built for THIS machine's setup (backend in `~/ai_chief_of_staff`, `./venv`,
iPhone 17 Pro simulator, redaction ON, audio retention ON). Uses the call
sheet's scenarios with corrections where the sheet is stale.

**Timing reality baked in below:** each live call costs ~60–75 s end-to-end
(≈35 s speaking + 10–20 s transcribe/classify + up to 10 s until the app's
auto-poll). You never wait on stage — every processing gap has a feature beat
scheduled inside it.

**Corrections to the call sheet (it predates this build):**
- Skip key is **`#`**, not `*` (press `#` alone → skips instantly).
- Names/rooms appear REDACTED (`Mr. [PERSON_1]`) in the inbox — that's the
  feature, not a bug. Real names are behind **Reveal identifiers** (audited).
- The simulator cannot receive real APNs pushes — "push + distinct sound"
  beats don't happen live. Optional fake below (§Push beat).
- `insufficient_detail` calls now land in their own **NEEDS REVIEW** group,
  not Routine.
- Backend here: `cd ~/ai_chief_of_staff && ./venv/bin/uvicorn app.main:app
  --port 8000` (there is no `venv311` and no `demo_calls.py` in this repo).

---

## T-minus 20 min — setup checklist

```
1. Backend:   cd ~/ai_chief_of_staff && ./venv/bin/uvicorn app.main:app --port 8000
2. Tunnel:    ngrok http 8000       (URL CHANGES on every restart!)
3. Webhook:   point the Twilio number at the CURRENT ngrok URL:
              set -a; source ~/ai_chief_of_staff/.env; set +a
              curl -s -X POST "https://api.twilio.com/2010-04-01/Accounts/$TWILIO_ACCOUNT_SID/IncomingPhoneNumbers/PN5540ba17d2a50b6f23d72899bc5da4b3.json" \
                -u "$TWILIO_ACCOUNT_SID:$TWILIO_AUTH_TOKEN" \
                --data-urlencode "VoiceUrl=https://<NEW-NGROK-ID>.ngrok-free.app/voice/incoming"
4. Sanity:    curl localhost:8000/calls   → JSON, no error
5. App:       launch ClinRoute in the simulator; inbox loads
6. First call after backend restart is ~5 s slower (spaCy model loads) —
   burn that on a seed call, never on a live one.
```

## T-minus 15 min — seed the queue (3 phone calls, ~4 min)

Make these BEFORE the demo so the inbox isn't empty and you have
audio-backed calls to play. From the sheet: **[B]**, **[E]**, **[F]**.

- **[B] CRITICAL seed** — keypad `512` `#`:
  > "CCU about Ms. Farrow in room 512. Her ICD has fired five times in the
  > last twenty minutes, awake but very distressed, keeps going back into a
  > fast VT between shocks. EP to call back immediately — looks like
  > electrical storm."
- **[E] ROUTINE seed** — keypad `415` `#`:
  > "Nurse on 4 West about Mr. Bianchi in room 415. Known chronic AF, rate
  > well controlled in the 70s, feeling fine. His metoprolol dose was held
  > this morning by mistake — does EP want us to resume the usual dose
  > tonight? No rush."
- **[F] FYI seed** — keypad `228` `#`:
  > "Device clinic. Ms. Alvarez came in for her scheduled pacemaker check —
  > stable, about six years of battery left, no arrhythmias recorded. Just
  > for the record, no callback needed, thanks."

Verify all three landed in the right groups. If one misclassified, either
re-call it or plan to use it as your Reclassify beat (see 3:45).

Also confirm one old **routine-labelled AF call** exists for the Reclassify
beat (there's one in app.db: "new AF ~145" marked routine). If it's been
resolved/corrected already, seed sheet call **[D]** as the reclassify target
instead.

---

## THE 10 MINUTES

### 0:00 — Inbox tour (no calls yet) — 45 s
Point at the seeded queue:
- Groups: **Critical** (red, "call back now") / **Urgent** / **Routine & FYI**
  — sorted by required response time, oldest first within a group.
- **Names are tokens** (`Ms. [PERSON_1]`): identifiers never reach OpenAI and
  aren't even in the default API payload — redaction is structural, not
  cosmetic.
- Tab badge = unresolved critical + urgent only.

### 0:45 — 📞 LIVE CALL 1: [C] URGENT — new AF, stable — keypad `623` `#`
> "Nurse on 6 East about Mr. Kwan in room 623. New atrial fibrillation, rate
> around 145, palpitations and mildly short of breath, but blood pressure
> stable at 128 over 80 and not in distress. How would EP like to
> rate-control him this shift?"

Hang up. **Say: "that'll take the system about half a minute — meanwhile…"**

### 1:30 — (lag cover) Detail view on seeded [B] — 60 s
Open the critical Farrow call:
- **Play voicemail** — the actual recording, streamed from the backend.
- Redacted transcript on screen.
- Tap **Reveal identifiers** → real name/room snap in; button flips to
  "access logged". Say: *"that reveal just wrote an audit row — PHIPA's
  'who accessed this record and when'."*

### 2:30 — [C] has appeared on its own (auto-poll, no touching)
Point out: correct group (**Urgent**), room 623 captured by keypad — the
room never became audio, never hit Whisper. Open it briefly: summary,
suggested action, confidence.

### 3:15 — 📞 LIVE CALL 2: [G] vague callback — press `#` alone (instant skip)
> "Yeah, hi, can you give me a call back about the patient in bed seven when
> you get a chance? Thanks."

(Shortest call — 10 s. Note the `#` skip goes straight to the beep.)

### 3:45 — (lag cover) Reclassify beat — 60 s
Open the old routine-labelled AF call (or any call you disagree with):
- Tap the **severity chip** (it has a chevron) → pick **Urgent**.
- Say: *"physician override — applied instantly, AND recorded server-side as
  a candidate worked example for the classifier's few-shot pool. The system
  learns from corrections, with a human-approved promotion step."*
- On the next poll it re-sorts into Urgent live.

### 4:45 — [G] lands in **NEEDS REVIEW** — not Routine
The safety story: *"nothing to triage on, so it refuses to guess — flags for
a human instead of inventing an urgency. And it doesn't dilute the routine
queue."* Badge on the row: NEEDS REVIEW.

### 5:30 — 📞 LIVE CALL 3: [I] *money case* — panicked voice, routine facts — keypad `210` `#`
> "Oh my gosh, please, you have to call me back right away, this is SO
> urgent! It's about Mr. Reyes in room 210 — his heart rate is 68 and he's
> totally fine and comfortable, but he asked me a question about his blood
> thinner and I really need someone to call me back as soon as possible,
> please, it's really important!"

### 6:15 — (lag cover) Resolve + FYI flag — 45 s
- Open seeded [F] (device clinic): context line shows **"caller says no
  callback needed"** — the no_callback flag.
- Tap **Resolve** → it moves to the Resolved tab, badge recounts.

### 7:00 — [I] appears as **ROUTINE** despite maximum drama
The line examiners remember: *"you can't game the queue with your voice —
it ranks the facts, not the tone."*

### 7:30 — 📞 LIVE CALL 4 (finale): [J] *mirror case* — casual voice, dangerous facts — keypad `305` `#`
> "Hey, sorry to bug you, it's probably nothing. Mr. Tan in 305 just kind of
> passed out for a bit — he's a little more awake now. His monitor's showing
> his heart rate dropping into the 30s with some long pauses, looks like
> complete heart block. Anyway, no big deal, just call whenever."

### 8:15 — (lag cover) Privacy architecture in 45 s
While it processes, the boundary story over the app:
*"Audio transits Twilio and Whisper — those boundaries are real, so: webhook
signatures validated, Twilio's copy of every recording deleted via their
API, transcripts redacted locally by Presidio BEFORE OpenAI classification,
identifiers in a separate table the export can't leak by construction, and
re-identification is a logged, audited action you saw earlier."*

### 9:00 — [J] lands **CRITICAL at the top** — casual tone, critical facts
Mirror closed: it won't under-triage a downplayed emergency either.

### 9:30 — Wrap — 30 s
One sentence: *"Four tiers ranked on facts; refuses to guess when there's
nothing to go on; physician corrections feed back into the model; and PHI
is protected by construction end to end."*

---

## Contingencies

- **Live call misclassifies** → don't apologize; open it, tap the severity
  chip, reclassify. *"And this is the correction loop working."* A miss
  becomes a feature beat.
- **Call doesn't appear in ~90 s** → `tail -5 /tmp/clinroute_backend.log`.
  Most likely: ngrok restarted → webhook points at a dead URL (step 3 of the
  checklist). Fall back to the seeded queue and keep narrating.
- **Play voicemail errors on an old call** → only calls made after Aug 3
  retain audio; use a seeded call from today.
- **App shows an error banner** → backend down; restart uvicorn (checklist
  step 1). The app self-heals on the next poll.

## Optional push beat (simulator can't receive real APNs)

Fake the critical push banner between beats (background the app first,
Cmd-Shift-H):

```
cat > /tmp/push.json <<'EOF'
{"aps": {"alert": {"title": "CRITICAL: New call",
 "body": "Sustained VT, BP falling — callback now"},
 "sound": "default", "badge": 1,
 "interruption-level": "time-sensitive"}, "call_id": 3}
EOF
xcrun simctl push booted com.clinroute.console /tmp/push.json
```

Say plainly it's simulated on the simulator; on a real iPhone the backend
sends it via APNs (severity-dependent sound/interruption in `push.py`).

---

*Fabricated data only — the audio really does transit Twilio + Whisper.
Labels in the sheet were verified Aug 3 against gpt-5-mini; re-verify after
any prompt/rubric change by re-calling the borderline cases (C, I, J).*
