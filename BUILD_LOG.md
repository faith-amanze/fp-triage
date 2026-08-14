# Build Log — Checkpoint 1 (FP-Triage MVP)

## What I'm building

An agent that reads real Azure AD interactive sign-in events, decides dismiss (known false
positive) or escalate (needs human review) per event, with a stated reason — and writes that
decision as a real row to a log file, no manual editing mid-run.

Proof statement this serves: "I build LLM-powered tools that auto-dismiss known-false-positive
security alerts, so a cloud team lead who gets paged at 2am can trust their queue enough to
book a call with me."

## Scope decisions

* **Cut: queue UI.** The core job is decide + act, not present. A UI doesn't change whether the
decision or the write-action is trustworthy, so it was cut from this checkpoint entirely
rather than stubbed. Revisit only if a later checkpoint specifically needs a demo surface.
* **Data source: `InteractiveSignIns` only**, not `ApplicationSignIns` or `MSISignIns`. Interactive
is the only one with real device-fingerprint data (`deviceDetail`) — the others are
service-to-service auth with no user/device judgment call to make.
* **Format: JSON, not CSV.** Original plan assumed a CSV export; the real Azure AD export is JSON.
Script reads JSON directly — no functional change to the logic, just the parser.

## What broke, and what changed

### 1\. Local environment setup (not a build bug, but ate real time)

* Claude Code installed but not on PATH — `.local\\bin` wasn't in the user's PATH. Fixed via
Environment Variables editor; first attempt failed because a new variable was accidentally
created instead of editing the existing `Path` list, and a trailing period slipped into the
path value on a later attempt. Second full terminal restart was needed before PowerShell
picked up the change — one restart alone didn't do it.
* Python wasn't installed at all (Windows' fake "Python was not found" Store stub). Installed
Python 3.14.6 from python.org directly instead.

### 2\. LLM provider: Gemini free tier blocked

* Original plan used Gemini (`gemini-2.0-flash`) since it's well-known and free. First run:
every one of 22 events failed with HTTP 429.
* Diagnosed with a single direct API call (bypassing the script) to see the real error body
instead of guessing: Gemini's free tier quota for this model is hard-capped at 0 requests
without billing linked — not a temporary rate limit, a permanent wall for this model/tier.
* **Deviation: switched to Groq** (`llama-3.3-70b-versatile`) — genuinely free tier, no billing
requirement, 30 req/min / 14,400 req/day. Logic and prompt unchanged, only the API call and
response parsing were swapped.

### 3\. Groq integration bugs (three separate issues, same symptom: HTTP 4xx)

* **Stale file syncing**: after rewriting the script for Groq, the file in the working folder
kept reverting to the old Gemini version. Root cause: downloads were landing in `Downloads` as
`triage\_agent (1).py`, `(2).py`, etc. rather than overwriting, and I was copying the wrong one.
Fixed by always picking the most-recently-modified `triage\_agent\*.py` in Downloads
programmatically instead of typing the filename by hand.
* **Invalid API key (HTTP 403 → "Invalid API Key")**: the Groq key pasted into Notepad silently
didn't save (same class of issue as the PATH edit). Root cause confirmed by printing the key's
actual length and prefix directly — it was still the old Gemini key. Fixed by writing the key
to the file directly from PowerShell instead of through Notepad.
* **Cloudflare block (HTTP 403 → "error code: 1010")**: even with a valid key, Python's `urllib`
was blocked by Groq's Cloudflare layer because of its default `Python-urllib/x.x` User-Agent
header — `curl` worked with the same key, which is what pointed at the header as the cause.
Fixed by adding an explicit `User-Agent` header to the request.

### First full successful end-to-end run

* Input: 22 real interactive sign-in events, 3 distinct (user, device) pairs.
* Output: 19 dismissed, 3 escalated. Every decision has a specific stated reason tied to the
actual event data (device seen before / first-seen + no strong reissue signal), not a generic
justification.
* Verified the write-action is real, not printed-only: confirmed via `Get-Content triage\_log.csv`
that the header row and 22 real rows exist, with real timestamps from the run.
* No mid-run hand-editing — reran the script clean (deleted and recreated `triage\_log.csv`) for
the version being recorded.

## What's still a known limitation (not fixed, noted honestly)

* Fail-safe behavior (escalate on any LLM call failure) was accidentally exercised for real, at
length, during the Gemini quota issue — so it's proven under real failure conditions, not just
designed in theory.
* Confidence field is returned but not yet used to gate anything (e.g. "only auto-dismiss on
high confidence") — flagged as a natural next-checkpoint idea, not built here.

### 4\. Logic bug found on re-verification: missing device\_id treated as a repeat device

* After Checkpoint 1 shipped, re-checked the CSV against Knowledge.txt's own rule ("unnamed
device -> always escalate") and found it was being violated: the *first* event with no
device\_id escalated correctly, but every later no-device-id event for the same user was
being dismissed, because the code cached `"(no-device-id)"` as if it were a real device ID
and matched later events against it.
* Fixed by treating a missing device\_id as always first-seen, and excluding it from the
seen-device cache entirely.
* On fixing and re-verifying, found a second edge case the first fix missed: some events have
`deviceId` present as an empty string `""` rather than a missing key, which slipped past the
`is None` check and re-triggered the same bug. Fixed by treating empty string the same as
missing.
* Re-ran clean: result changed from 19 dismissed / 3 escalated to 7 dismissed / 15 escalated.
Confirmed via direct CSV grep that every no-device-id row now escalates, with zero exceptions.
* Confidence field is still uniformly "high" on every row, including ambiguous first-seen
cases — flagging this as unreliable/unused rather than trustworthy, same known-limitation
bucket as before.

### 6. Confidence re-verified on clean run, 2026-08-14

- Re-ran the 22-event set clean (deleted `triage_log.csv`, fresh run) to check whether the
  confidence field discriminates on real data, not just the hand-built edge cases used to
  validate the confidence gate itself.
- Result unchanged: 7 dismissed / 15 escalated, confirming the section-4 fix still holds on
  a genuinely clean run.
- Confidence field: uniformly "high" across all 22 rows, including first-seen/unnamed-device
  escalations that would reasonably be considered lower-confidence cases.
- Conclusion: the confidence gate is real, live code, and has been proven to fire correctly
  on hand-built edge cases (see the probe in `src/dev-notes/`). It has not yet been observed
  discriminating on real sign-in data — every real row so far has returned "high." Site copy
  updated to state this precisely rather than imply it's been demonstrated on live data.

