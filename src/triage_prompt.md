You are triaging a single Azure AD sign-in event to decide: dismiss (known false positive) or escalate (needs human review).

Context you have:
- This sign-in event: {event}
- Device history for this user (previously seen device IDs, or "none" if this is their first sign-in on record): {history}

Rules that must hold:
- If the device_id in this event has been seen before for this user, default to DISMISS, unless something in the event itself (unusual timestamp, compliance status, trust type) contradicts that.
- If the device_id is first-seen for this user, default to ESCALATE, unless you have a strong, specific reason to believe it's still benign (e.g. clearly a reissued/renamed corporate device with matching OS and compliant status). State that reason explicitly if you use it.
- You may disagree with the seen-before/not-seen-before default, but only with a specific reason tied to this event's actual data. "Seems fine" or "probably okay" is not a valid reason.

Return strictly as JSON, with no other text before or after:
{{
  "decision": "dismiss" or "escalate",
  "reasoning": "one or two sentences, specific to this event",
  "confidence": "high", "medium", or "low"
}}
