# FP-Triage Agent

An agent that reads real Azure AD (Entra ID) interactive sign-in events and decides, per event,
whether to **dismiss** (known false positive) or **escalate** (needs human review) — with a
stated, evidence-based reason — and writes that decision as a real row to an audit log. No
manual editing mid-run.

**Who this is for:** a cloud team lead whose on-call queue is mostly noise. This exists so that
when your queue pages you at 2am, you can trust that what's left in it is worth waking up for.

---

## What it actually does

Most "suspicious sign-in" alerts fire on a single naive signal — usually "unmanaged device." On
a real 1,096-event Azure AD tenant, that naive rule alone flagged **1,070 of 1,096** sign-ins
(97.6%). The actual signal isn't "is this device unmanaged" — it's **"has this (user, device)
pair been seen before."** Once that check is applied, only 4 of the 1,070 (0.4%) turn out to be
genuinely first-seen and worth a human's attention.

This agent encodes that rule as an LLM-judged decision (not a hardcoded if-statement) so it can
also reason about edge cases — an unnamed device, a device known but for a *different* user —
where a flat rule would be too blunt to trust unattended.

## How it works

```
signins.json (Azure AD interactive sign-in export)
        │
        ▼
build_history_groups()
   sorts events chronologically, tags each (user, device) pair as
   "first-seen" or "seen before." A missing or empty device_id is
   ALWAYS treated as first-seen — it can never be cached as a
   known device, even across repeat events for the same user.
        │
        ▼
classify_event()
   builds a prompt from the event summary + history context
        │
        ▼
Groq API (llama-3.3-70b-versatile)
   returns { decision, reasoning, confidence }
        │
        ├── confidence gate: if decision = "dismiss" but confidence
        │   isn't "high," override to "escalate," keeping the
        │   original reasoning visible with a note explaining why
        │   it was overridden
        │
        ├── HTTP/parse failure → fail-safe: decision = "escalate",
        │   reasoning = "LLM call failed, escalating for safety"
        ▼
write_log_row()
   appends one real row per event to triage_log.csv (audit trail)
```

**Design decision worth calling out:** the fail-safe path (escalate on any LLM call failure,
never silently dismiss) isn't just a design intention — it was exercised for real, at length,
during a provider quota outage while building this. It's proven under an actual failure, not
just theoretical.

## Setup (from a clean machine)

1. **Python 3.10+** installed and on your PATH.
2. **A free Groq API key** — [console.groq.com](https://console.groq.com), no billing required
   for `llama-3.3-70b-versatile` on the free tier (30 req/min, 14,400 req/day).
3. Clone this repo.
4. Create `api_key.txt` inside `src/`, containing only your Groq key (no quotes, no newline
   padding). This file is gitignored on purpose — never commit a real key.
5. `signins.json` and `triage_prompt.md` are already included in `src/` — no setup needed for
   those, they're real inputs the agent was built and tested against.
6. From inside `src/`, run:
   ```
   cd src
   python triage_agent.py
   ```

**No hosted/deployed version exists yet** — this runs locally against the file already in the
repo. Saying otherwise would be the kind of unverifiable claim this whole project exists to
avoid.

`src/dev-notes/` holds the one-off scripts used to find and fix bugs and to probe the confidence
gate (see Eval Results below) — kept for transparency, not needed to run the agent itself.

## Usage example

```
$ cd src
$ python triage_agent.py
Total sign-in events: 22
[2026-07-14T05:48:48Z] faith@[redacted-tenant] | (unnamed) -> ESCALATE (high) — This is a first-seen device for the user, and there's no specific indication that it's a reissued or renamed corporate device...
[2026-07-14T08:07:42Z] user2@[redacted-tenant] | WinSpire -> DISMISS (high) — The device_id has been seen before for this user, and there's nothing unusual in the event itself...
...
Done. 7 dismissed, 15 escalated, out of 22 events.
Full log written to triage_log.csv
```

Every row in `triage_log.csv` has a timestamp, user, device, decision, a specific stated reason
tied to that event's actual data, and a confidence level. A username-redacted copy is included
as `triage_log_redacted.csv` for anyone who wants to see the pattern without real tenant
identifiers.

## Eval results — three separate tests, don't conflate them

**1. Rule validation (offline, 1,096 real sign-ins, one test tenant)**
Tests whether the *dismiss/escalate rule itself* is sound, independent of the agent:
- 1,070 of 1,096 flagged by a naive "unmanaged device" rule
- 1,066 (99.6% of flagged) auto-dismissed once device-history is checked
- 4 (0.4%) correctly held back as genuinely first-seen — none of the true first-seen cases were
  missed

**2. Live agent run (actual `triage_agent.py` execution, 22 real sign-ins, current code)**
This is what you'll reproduce by running the setup above:
- **7 dismissed, 15 escalated**
- This number changed from an earlier run (19 dismissed / 3 escalated) after a real bug was
  found and fixed — see below. The earlier number was wrong; this one is verified.
- Verified the log is a real write, not printed-only, by confirming header + 22 data rows in
  `triage_log.csv` with real run timestamps
- No mid-run hand-editing — log file was deleted and the script rerun clean for this result

**3. Confidence-gate probe (2 hand-crafted adversarial events, not part of the 22-event set)**
On the 22 real events, every single confidence value came back "high" — which raised a real
question: does the model ever express lower confidence, or is the gate dead code against this
dataset? Two edge cases were built specifically to test it (a known device signing in from an
unfamiliar IP/location; a known device signing in at an unusual hour from a nearby-but-different
IP) — both returned **"medium"** confidence, with reasoning tied to the specific anomaly in each
event. This confirms the gate isn't decorative: the model can and does express uncertainty when
an event actually warrants it; it just never encountered that situation in the original 22-event
set.

The 1,096 number says the rule is right. The 22-event run says the agent implements it
correctly. The 2-event probe says the confidence gate actually functions, tested against cases
designed to trigger it. None of the three substitutes for the others.

## Bug found and fixed after initial shipping

The first working version cached a missing device ID as if it were a real device (as the string
`"(no-device-id)"`), so a *second* sign-in with no device ID from the same user was wrongly
matched against that placeholder and treated as "seen before" — directly violating this
project's own rule that an unnamed/unidentified device should always be escalated. Fixed in two
passes: first for a missing `deviceId` key, then for a second edge case where `deviceId` was
present but an empty string, which slipped past the first fix's `is None` check. Re-running
clean after the fix changed the result from 19 dismissed / 3 escalated to the current, correct
7 dismissed / 15 escalated. This is disclosed here rather than quietly folded into the numbers
above, because a triage tool's credibility depends on its dismiss/escalate boundary being
exactly right, not approximately right.

## Limitations (named honestly, not hidden)

- **Confidence gate is real and tested, but only against 2 adversarial probes, not the full
  22-event set.** It's proven to function; it hasn't been proven to catch every case it should.
- **Cross-user device reuse is a known edge case, not a solved one.** A device ID known for
  *one* user isn't the same as known for the user currently signing in. The rule routes this to
  escalate/low-confidence rather than auto-dismissing on device recognition alone — flagged here
  as a case worth a human's judgment.
- **This pipeline evaluates one alert at a time and has no memory across alerts.** It cannot
  catch a pattern like the same user signing in from two locations ~380km apart within minutes —
  each sign-in looks unremarkable in isolation; only the pair is suspicious. Catching that needs
  a stateful, session-aware check this design doesn't attempt.
- **No hosted/deployed version.** This runs locally against a provided file, not against a live
  Azure AD tenant on a schedule.

## Why the false-positive numbers matter more than the LLM

The interesting part of this project isn't "an LLM classifies sign-ins." It's that the decision
rule was derived from real data first (what does 97.6%-flagged-but-99.6%-safe-to-dismiss
actually mean for a queue), the LLM's job is narrowly to apply that rule with a legible,
per-event reason, and every bug found along the way was found by checking the code's actual
output against that rule — not assumed away.

> **Repo scope:** this repo holds the agent, the real data, and the honest build log —
> the evidence trail behind the claims on the live site. The deployed site itself
> (HTML, styling, and the `/Try It` Netlify function) lives in a separate repo:
> [fp-triage-site](https://github.com/faith-amanze/fp-triage-site).
