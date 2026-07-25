"""
FP-triage agent — Checkpoint 1 MVP.

Reads real Azure AD interactive sign-in events from signins.json, groups them by
(user, device), classifies each event as dismiss/escalate using an LLM (Gemini,
free tier) with reasoning, and writes every decision as a real row to triage_log.csv.

Run with: python triage_agent.py
"""

import json
import csv
import os
import time
import urllib.request
import urllib.error

DATA_FILE = "signins.json"
PROMPT_FILE = "triage_prompt.md"
KEY_FILE = "api_key.txt"
LOG_FILE = "triage_log.csv"

GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def load_api_key():
    with open(KEY_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()


def load_prompt_template():
    with open(PROMPT_FILE, "r", encoding="utf-8") as f:
        return f.read()


def load_events():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def build_history_groups(events):
    """
    Sort events by time, then for each (user, device_id) pair, mark the first
    occurrence as 'first-seen' and everything after as 'known'. Returns the
    events in chronological order, each annotated with its history context.
    """
    def device_id(e):
        return (e.get("deviceDetail") or {}).get("deviceId") or "(no-device-id)"

    events_sorted = sorted(events, key=lambda e: e.get("createdDateTime", ""))

    seen_pairs = {}  # (user, device_id) -> first_seen_timestamp
    user_devices = {}  # user -> set of device_ids seen so far

    annotated = []
    for e in events_sorted:
        user = e.get("userPrincipalName", "(unknown-user)")
        dev = device_id(e)
        key = (user, dev)

        prior_devices = sorted(user_devices.get(user, set()))
        is_first_seen = key not in seen_pairs

        annotated.append({
            "event": e,
            "user": user,
            "device_id": dev,
            "device_name": (e.get("deviceDetail") or {}).get("displayName", ""),
            "timestamp": e.get("createdDateTime", ""),
            "is_first_seen": is_first_seen,
            "prior_devices_for_user": prior_devices,
        })

        seen_pairs[key] = e.get("createdDateTime")
        user_devices.setdefault(user, set()).add(dev)

    return annotated


def summarize_event_for_prompt(item):
    e = item["event"]
    dd = e.get("deviceDetail") or {}
    return {
        "user": item["user"],
        "timestamp": item["timestamp"],
        "device_id": item["device_id"],
        "device_name": dd.get("displayName", ""),
        "operating_system": dd.get("operatingSystem", ""),
        "is_compliant": dd.get("isCompliant"),
        "is_managed": dd.get("isManaged"),
        "trust_type": dd.get("trustType", ""),
        "ip_address": e.get("ipAddress", ""),
        "risk_level": e.get("riskLevelDuringSignIn", ""),
    }


def call_groq(api_key, prompt_text):
    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt_text}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        GROQ_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "fp-triage-agent/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode("utf-8"))

    text = body["choices"][0]["message"]["content"]
    return json.loads(text)


def classify_event(api_key, template, item):
    history_desc = (
        "none — this is a first-seen device for this user"
        if item["is_first_seen"]
        else f"seen before: {item['prior_devices_for_user']}"
    )
    prompt_text = template.format(
        event=json.dumps(summarize_event_for_prompt(item)),
        history=history_desc,
    )

    # Retry once on rate-limit errors (HTTP 429) after a longer pause, before giving up.
    for attempt in range(2):
        try:
            result = call_groq(api_key, prompt_text)
            return result.get("decision", "escalate"), result.get("reasoning", ""), result.get("confidence", "low")
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt == 0:
                time.sleep(15)
                continue
            return "escalate", f"LLM call failed, escalating for safety: HTTP {exc.code}", "low"
        except (urllib.error.URLError, KeyError, json.JSONDecodeError, IndexError) as exc:
            return "escalate", f"LLM call failed, escalating for safety: {exc}", "low"


def write_log_row(user, device_id, device_name, decision, reasoning, confidence):
    file_exists = os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 0
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "user", "device_id", "device_name", "decision", "reasoning", "confidence"])
        writer.writerow([time.strftime("%Y-%m-%dT%H:%M:%SZ"), user, device_id, device_name, decision, reasoning, confidence])


def main():
    api_key = load_api_key()
    template = load_prompt_template()
    events = load_events()
    annotated = build_history_groups(events)

    print(f"Total sign-in events: {len(events)}")

    dismissed = 0
    escalated = 0

    for i, item in enumerate(annotated):
        if i > 0:
            time.sleep(1.5)  # stay comfortably under Groq's free-tier 30 requests/minute limit
        decision, reasoning, confidence = classify_event(api_key, template, item)
        write_log_row(item["user"], item["device_id"], item["device_name"], decision, reasoning, confidence)

        if decision == "dismiss":
            dismissed += 1
        else:
            escalated += 1

        print(f"[{item['timestamp']}] {item['user']} | {item['device_name'] or '(unnamed)'} "
              f"-> {decision.upper()} ({confidence}) — {reasoning}")

    print()
    print(f"Done. {dismissed} dismissed, {escalated} escalated, out of {len(annotated)} events.")
    print(f"Full log written to {LOG_FILE}")


if __name__ == "__main__":
    main()
