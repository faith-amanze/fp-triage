old = """    for i, item in enumerate(annotated):
        if i > 0:
            time.sleep(1.5)  # stay comfortably under Groq's free-tier 30 requests/minute limit
        decision, reasoning, confidence = classify_event(api_key, template, item)
        write_log_row(item["user"], item["device_id"], item["device_name"], decision, reasoning, confidence)"""

new = """    for i, item in enumerate(annotated):
        if i > 0:
            time.sleep(1.5)  # stay comfortably under Groq's free-tier 30 requests/minute limit
        decision, reasoning, confidence = classify_event(api_key, template, item)

        # Confidence gate (Checkpoint 3): the LLM's own confidence field was returned but
        # never used to gate anything. If it says dismiss without high confidence, that's
        # not a trustworthy auto-dismiss -- escalate instead, but keep the original
        # reasoning visible rather than overwrite it.
        if decision == "dismiss" and confidence.lower() != "high":
            reasoning = (
                f"CONFIDENCE GATE: LLM confidence was \\'{confidence}\\', not high, so "
                f"overriding dismiss -> escalate. Original reasoning: {reasoning}"
            )
            decision = "escalate"

        write_log_row(item["user"], item["device_id"], item["device_name"], decision, reasoning, confidence)"""

with open("triage_agent.py", "r", encoding="utf-8") as f:
    content = f.read()

if old not in content:
    print("NO MATCH FOUND")
else:
    content = content.replace(old, new)
    with open("triage_agent.py", "w", encoding="utf-8") as f:
        f.write(content)
    print("SUCCESS")
