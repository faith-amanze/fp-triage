import json, urllib.request

with open("api_key.txt", "r", encoding="utf-8") as f:
    api_key = f.read().strip()

prompt = """You are triaging a single Azure AD sign-in event to decide: dismiss (known false positive) or escalate (needs human review).

Context you have:
- This sign-in event: {"user": "paul.fakunle@example.com", "timestamp": "2026-07-29T02:14:02Z", "device_id": "1aa6b986-f806-4047-8ad8-fd33f4eeaf3f", "device_name": "PAUL-DESKTOP", "operating_system": "Windows10", "is_compliant": true, "is_managed": true, "trust_type": "AzureAD", "ip_address": "185.220.101.47", "risk_level": "high"}
- Device history for this user (previously seen device IDs, or "none" if this is their first sign-in on record): seen before: [\'1aa6b986-f806-4047-8ad8-fd33f4eeaf3f\'] -- but always previously from IP 102.88.55.131, Lagos, Nigeria. This sign-in is from a different IP and location.

Rules that must hold:
- If the device_id in this event has been seen before for this user, default to DISMISS, unless something in the event itself (unusual timestamp, compliance status, trust type) contradicts that.
- If the device_id is first-seen for this user, default to ESCALATE, unless you have a strong, specific reason to believe it is still benign.
- You may disagree with the seen-before/not-seen-before default, but only with a specific reason tied to this event's actual data. "Seems fine" or "probably okay" is not a valid reason.

Return strictly as JSON, with no other text before or after:
{"decision": "dismiss" or "escalate", "reasoning": "one or two sentences, specific to this event", "confidence": "high", "medium", or "low"}"""

payload = {
    "model": "llama-3.3-70b-versatile",
    "messages": [{"role": "user", "content": prompt}],
    "temperature": 0,
    "response_format": {"type": "json_object"},
}
req = urllib.request.Request(
    "https://api.groq.com/openai/v1/chat/completions",
    data=json.dumps(payload).encode("utf-8"),
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "fp-triage-test/1.0",
    },
    method="POST",
)
with urllib.request.urlopen(req, timeout=30) as resp:
    body = json.loads(resp.read().decode("utf-8"))

result = json.loads(body["choices"][0]["message"]["content"])
print(json.dumps(result, indent=2))
