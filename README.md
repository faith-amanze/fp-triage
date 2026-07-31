# FP-Triage — LLM-Powered False-Positive Alert Triage

**Proof statement:** I build LLM-powered tools that auto-dismiss known-false-positive security alerts, so a cloud team lead who gets paged at 2am can trust their queue enough to book a call with me.

**Live demo (no setup required):** https://faith-amanze.netlify.app/ — click any scenario button under "Try It" to run the real agent live, including a deliberately ambiguous case that shows the confidence gate overriding a dismiss decision on camera.

---

## What it does, and who it's for

Security teams get a constant stream of sign-in alerts — "someone logged in from an unmanaged device." Most are noise: the same person, the same laptop they always use. A few are real. Triaging that queue by hand is what pages someone at 2am for nothing.

FP-Triage reads real Azure AD interactive sign-in events, and for each one:

1. Checks whether this device has been seen for this specific user before.
2. Sends that context to an LLM, which returns a decision (`dismiss` or `escalate`), a plain-English reason, and a confidence level.
3. Gates the decision — if the model says `dismiss` without high confidence, it's overridden to `escalate` rather than auto-dismissed on a hunch.
4. Writes every decision to a real log file. Nothing is silently thrown away, including `dismiss`.

Built for a security/cloud team lead evaluating whether an LLM-based triage layer could be trusted in front of a real on-call queue — and for anyone reviewing this as a portfolio piece who wants to see the reasoning, not just a demo.

---

## Architecture

```
Azure AD sign-in export (JSON)
        │
        ▼
Group events into physical sessions
by (user, IP, 10-minute rolling window)
        │
        ▼
For each session: check device history
for this (user, device) pair
        │
        ▼
LLM call — Groq, llama-3.3-70b-versatile
  → decision (dismiss / escalate)
  → reasoning (plain English, tied to the event)
  → confidence (high / medium / low)
        │
        ▼
Confidence gate
  dismiss + confidence != high  →  override to escalate
  (original reasoning kept, override noted, not hidden)
        │
        ▼
triage_log.csv — every decision written, every time
```

The live site (`faith-amanze.netlify.app`) runs the same prompt and gate logic through a Netlify serverless function (`netlify/functions/triage.js`), against a small set of fixed illustrative scenarios, so a visitor can see the real mechanism without needing their own Azure AD export or API key.

---

## Setup — reproduce this yourself

**Requirements:** Python 3.10+. The core agent (`src/triage_agent.py`) has **zero third-party dependencies** — only the standard library (`json`, `csv`, `os`, `time`, `urllib`). The Week 5 analysis notebook additionally needs `pandas` and `scikit-learn`.

1. **Clone the repo**
   ```bash
   git clone https://github.com/faith-amanze/fp-triage.git
   cd fp-triage/src
   ```

2. **Get a free Groq API key** at https://console.groq.com — no billing required, generous free tier (30 requests/min, 14,400/day), which is what this project actually runs on.

3. **Save your key** to a file named `api_key.txt` in the same folder as `triage_agent.py`, containing only the key itself, no quotes, no extra whitespace.

4. **Create `triage_prompt.md`** in the same folder — the template sent to the LLM. It must contain the literal placeholders `{event}` and `{history}`, which the script fills in per event:
   ```
   You are triaging a single Azure AD sign-in event to decide: dismiss (known false positive) or escalate (needs human review).

   Context you have:
   - This sign-in event: {event}
   - Device history for this user (previously seen device IDs, or "none" if this is their first sign-in on record): {history}

   Rules that must hold:
   - If the device_id in this event has been seen before for this user, default to DISMISS, unless something in the event itself (unusual timestamp, compliance status, trust type) contradicts that.
   - If the device_id is first-seen for this user, default to ESCALATE, unless you have a strong, specific reason to believe it's still benign. State that reason explicitly if you use it.
   - You may disagree with the seen-before/not-seen-before default, but only with a specific reason tied to this event's actual data. "Seems fine" or "probably okay" is not a valid reason.

   Return strictly as JSON, with no other text before or after:
   {"decision": "dismiss" or "escalate", "reasoning": "one or two sentences, specific to this event", "confidence": "high", "medium", or "low"}
   ```

5. **Supply a sign-in export as `signins.json`** — a JSON array of Azure AD `InteractiveSignIns`-shaped events. Real tenant exports and API keys are intentionally **not** committed to this repo (see `.gitignore`) since they're sensitive. Minimum shape the script expects per event:
   ```json
   {
     "createdDateTime": "2026-07-14T08:07:11Z",
     "userPrincipalName": "user@example.com",
     "ipAddress": "203.0.113.10",
     "riskLevelDuringSignIn": "none",
     "deviceDetail": {
       "deviceId": "b2e91120-9c4d-4a11-8e7a-2f61b6d0a933",
       "displayName": "SOME-DEVICE",
       "operatingSystem": "Windows10",
       "isCompliant": true,
       "isManaged": true,
       "trustType": "AzureAD"
     }
   }
   ```

6. **Run it:**
   ```bash
   python triage_agent.py
   ```

7. **Output:** `triage_log.csv`, one row per event — timestamp, user, device, decision, reasoning, confidence. Reruns append; delete the file first for a clean run.

---

## Usage example

A real row from an actual run, redacted:

```
timestamp,user,device_id,device_name,decision,reasoning,confidence
2026-07-30T07:16:40Z,user2@[redacted-tenant],ae7d8793-...,WinSpire,ESCALATE,"First-seen device for the user — no strong indication that it's a reissued or renamed corporate device.",high
2026-07-30T07:16:42Z,user2@[redacted-tenant],ae7d8793-...,WinSpire,DISMISS,"The device_id has been seen before for this user, and there's nothing unusual in the event itself that would contradict this.",high
```

Same device, three minutes apart. The tool escalated it the first time it ever saw it, then dismissed it the moment it had history to check against — that's the actual mechanism, not a canned response.

---

## Eval results — Week 5 (`work/notebooks/w05_model.ipynb`)

**Data:** one real, unmodified Azure AD export (22 raw events, 2 users, 2 known devices, one day). Collapsing resource-app pings into real physical sessions (by user + IP + 10-minute window) brings this down to **5 real sign-in sessions** — 3 escalate, 2 dismiss under the documented rule.

The notebook asks two separate questions rather than one, because they aren't the same claim:

| Method | Accuracy | Precision (escalate) | Recall (escalate) |
|---|---|---|---|
| Baseline rule (Knowledge.txt) | 1.00 | 1.00 | 1.00 |
| Model A — rule-equivalent features (LOOCV) | 0.80 | 1.00 | 0.667 |
| Model B — history-independent features (LOOCV) | 0.40 | 0.50 | 0.667 |

- **Model A** (Q1 — pipeline sanity check): given the *same* history features the rule itself uses, a Logistic Regression model should just recover the rule. It didn't cleanly — 80%, not ~100% — which at N=5 is a caution about sample size, not a rule failure.
- **Model B** (Q2 — the real question): using only signals independent of device history (auth success, hour of day, session burst size, risk level), can a model do any better than "always escalate" on a cold-start device? **No — it scored worse (40%) than the trivial always-escalate baseline (60%).** Azure's own risk engine flagged `none` on every session in this file; there's currently no cheap signal in this data that substitutes for checking device history.
- **The most consequential finding wasn't a model score at all:** applying the rule at the raw-event level (22 rows) instead of the real physical-session level (5 logins) would have over-escalated by roughly 4x in production, purely from one login pinging multiple Microsoft resource apps. Caught before any model was trained.

**Read honestly:** N=5 is a method demonstration on real data, not a performance claim. Nothing here validates the tool at tenant scale — that requires the full 1,096-event tenant export referenced in `Knowledge.txt` (baseline: 97.6% flagged, 99.6% of those auto-dismissed correctly, 4 correctly escalated), and re-running this same pipeline against it.

---

## Limitations — stated honestly, not hidden

1. **No memory across alerts.** The pipeline judges one sign-in event at a time. It structurally cannot catch the same user signing in from two distant locations minutes apart — only visible across alerts, not within one. Named in `Knowledge.txt`, `BUILD_LOG.md`, and scheduled as the next piece of work (stateful/session-aware check).
2. **Confidence gate is built but rarely exercised.** The model returns `high` confidence on nearly every real event so far, including genuinely ambiguous ones. The gate has been proven to fire correctly, but only on a deliberately constructed edge case (see live demo), not yet on organic production-shaped data.
3. **Eval scale is small (N=5 real sessions).** See above — a method check, not a performance claim, until re-run against the full tenant export.
4. **No cheap substitute found (yet) for device-history checking.** History-independent signals (risk level, auth success, time of day) performed worse than a trivial guess in the one real test available. IP reputation, geovelocity, or a real ML-based risk score would be needed before that check could be safely loosened.
5. **Accessibility score 89/100** on both mobile and desktop (PageSpeed Insights) for the live site — consistent, real, not yet fixed.
6. **LinkedIn link and full mobile/cross-browser rendering** on the live site have not been independently, manually verified.

---

## Status

- **Checkpoint 1 (agent MVP):** complete. Real Azure AD events in, LLM decision + reasoning out, real CSV log.
- **Checkpoint 2 (hardening):** complete. Broken badge link/image found and fixed, unescaped LLM output in the live demo fixed, SEO/meta added, site verified and indexed with Google.
- **Checkpoint 3 (confidence gating):** complete. Gate built, verified in code, proven to fire on a constructed adversarial case; not yet proven on organic data (see Limitations).
- **Week 5 (model vs. baseline):** complete — `work/notebooks/w05_model.ipynb`.
- **Next:** impossible-travel / stateful check — scheduled.

---

## Links

- Live site: https://faith-amanze.netlify.app/
- Repo: https://github.com/faith-amanze/fp-triage
- Book a call: https://calendly.com/faith-amanze/new-meeting
