path = "triage_agent.py"

old = '''def device_id(e):
        return (e.get("deviceDetail") or {}).get("deviceId")  # None if missing'''

new = '''def device_id(e):
        raw = (e.get("deviceDetail") or {}).get("deviceId")
        return raw if raw else None  # treat empty string the same as missing'''

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

if old not in content:
    print("NO MATCH FOUND")
else:
    content = content.replace(old, new)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("SUCCESS")
