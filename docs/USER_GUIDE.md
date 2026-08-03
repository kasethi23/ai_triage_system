# Conduit — User guide

A one-page guide for the people who **use** the tool: the staff who leave messages,
and the on-call physician who reads the queue. (Developer docs live in `CLAUDE.md`.)

## What this tool is — and isn't

Conduit listens to on-call messages, transcribes them, and **ranks them by urgency**
so the on-call EP physician answers the most urgent call first instead of in arrival
order.

- ✅ It is a **decision aid** that orders the queue and flags what needs attention.
- ❌ It is **not** a replacement for clinical judgment, and **not** an emergency
  response system. A code or an immediate life threat needs the emergency line, not a
  triaged voicemail.

---

## The one rule: don't game the queue

The tool triages on **clinical facts** — the patient's condition, the vital signs,
what's changing, and what you actually need — **not** on tone, urgency words, or how
dramatically you phrase it. In fact it is deliberately built to **ignore** emotional
register and "urgency" language.

**So gaming it doesn't reliably work, and it hurts everyone:**
- Dressing up a routine call as an emergency to jump the queue **buries a real
  emergency** behind it.
- If callers exaggerate, the ranking becomes noise, the physician stops trusting it,
  and the tool becomes **worse than no tool** — a false sense of order.
- Every override and access is **logged**. This isn't a leaderboard; there's nothing
  to win by inflating.

**Say what's true. Let the facts set the priority.**

---

## If you're leaving a message (nurse, referring physician, staff, family)

**Do**
- State the **situation plainly** — who/where, what's happening, the vitals, and what
  you need (an SBAR-style message works best).
- Enter the **bed/room number on the keypad** when prompted (it's more accurate than
  saying it).
- Say **"no callback needed"** if you're just closing the loop — it keeps the queue
  clean.

**Don't**
- Don't **inflate** urgency to be seen sooner — say the clinical facts and the tool
  will rank it correctly.
- Don't **downplay** a genuine emergency either — if minutes matter, say so with the
  facts, or use the emergency bypass / emergency line.
- Don't leave a message with **no clinical content** ("call me about bed 7") — it
  can't be triaged and will be flagged for a human, which is slower for you.

## If you're the on-call physician

**Do**
- Treat the label as a **suggestion** — read the transcript and use your judgment.
  You are responsible for the call, not the AI.
- Look at anything **flagged for review** (insufficient detail / low confidence)
  promptly — those are the ones the AI is *unsure* about.
- **Correct** a wrong classification when you see one — it feeds back (after human
  review) to improve the tool. Correct thoughtfully; a bad correction can propagate.

**Don't**
- Don't assume a **"routine" label means it's safe** — if something reads worse than
  its tag, act on your read.
- Don't view or export patient identity you don't need — **re-identification is
  audited** (PHIPA), and the queue contains PHI. No screenshots or sharing.

---

## Things every user should know (this is a prototype)

- The AI is a **frozen model** validated on **synthetic** data — it has a small but
  real error rate (it will occasionally mis-rank), which is exactly why the physician
  stays in the loop.
- It is **not approved for real patient data yet.** During testing/demos, use
  **fabricated** names and details only.
- Audio still passes through third-party services (the phone provider and
  transcription) before it's de-identified, so **don't speak real patient identifiers
  into a demo call**.
- If the tool does something wrong, **flag/override it and tell the team** — that's
  how it gets better, and it's the honest thing to do rather than working around it.
