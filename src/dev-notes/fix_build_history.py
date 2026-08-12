import re

path = r"C:\Users\faith\Downloads\repo_build\src\triage_agent.py"

old = '''def build_history_groups(events):
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

    return annotated'''

new = '''def build_history_groups(events):
    """
    Sort events by time, then for each (user, device_id) pair, mark the first
    occurrence as 'first-seen' and everything after as 'known'. Events with no
    device_id can never be confirmed as a repeat of a prior device, so they are
    ALWAYS treated as first-seen, not just the first time they occur.
    """
    def device_id(e):
        return (e.get("deviceDetail") or {}).get("deviceId")  # None if missing

    events_sorted = sorted(events, key=lambda e: e.get("createdDateTime", ""))

    seen_pairs = {}  # (user, device_id) -> first_seen_timestamp
    user_devices = {}  # user -> set of device_ids seen so far

    annotated = []
    for e in events_sorted:
        user = e.get("userPrincipalName", "(unknown-user)")
        dev = device_id(e)
        key = (user, dev)

        prior_devices = sorted(user_devices.get(user, set()))
        is_first_seen = (dev is None) or (key not in seen_pairs)

        annotated.append({
            "event": e,
            "user": user,
            "device_id": dev if dev is not None else "(no-device-id)",
            "device_name": (e.get("deviceDetail") or {}).get("displayName", ""),
            "timestamp": e.get("createdDateTime", ""),
            "is_first_seen": is_first_seen,
            "prior_devices_for_user": prior_devices,
        })

        if dev is not None:
            seen_pairs[key] = e.get("createdDateTime")
            user_devices.setdefault(user, set()).add(dev)

    return annotated'''

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

if old not in content:
    print("NO MATCH FOUND — file may already be edited, or differs from expected. Nothing changed.")
else:
    content = content.replace(old, new)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("SUCCESS — function replaced.")
