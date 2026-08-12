import csv

with open("triage_log.csv", "r", encoding="utf-8", newline="") as f:
    rows = list(csv.reader(f))

# map real usernames to placeholders
name_map = {}
counter = 1

for row in rows[1:]:  # skip header
    user = row[1]
    if user not in name_map:
        name_map[user] = f"user{counter}@[redacted-tenant]"
        counter += 1
    row[1] = name_map[user]

with open("triage_log_redacted.csv", "w", encoding="utf-8", newline="") as f:
    csv.writer(f).writerows(rows)

print("SUCCESS - wrote triage_log_redacted.csv")
print("Name mapping:", name_map)
