"""Audit: compare raw messages vs extracted events to find FP/FN."""

import sqlite3

conn = sqlite3.connect("data/slack_events.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("""
SELECT m.message_id, m.ts_dt, m.channel, m.text,
       COUNT(DISTINCT c.message_id) as is_candidate,
       COUNT(DISTINCT e.event_id) as event_count,
       GROUP_CONCAT(e.object_name_raw, ' || ') as objects
FROM raw_slack_messages m
LEFT JOIN event_candidates c ON c.message_id = m.message_id
LEFT JOIN events e ON e.message_id = m.message_id
GROUP BY m.message_id
ORDER BY m.ts_dt
""")
rows = cur.fetchall()

print(f"Total messages: {len(rows)}")
print()

scored_no_event = []
not_scored = []
has_events = []

for r in rows:
    if r["event_count"] > 0:
        has_events.append(r)
    elif r["is_candidate"] > 0:
        scored_no_event.append(r)
    else:
        not_scored.append(r)

print(f"=== Messages with events extracted: {len(has_events)} ===")
for r in has_events:
    print(
        f"  {r['ts_dt'][:16]} {r['channel'][-10:]} | {r['event_count']} events | {r['text'][:80]}"
    )
print()

print(f"=== Messages scored but LLM returned non-event: {len(scored_no_event)} ===")
for r in scored_no_event:
    print(f"  {r['ts_dt'][:16]} {r['channel'][-10:]} | {r['text'][:120]}")
print()

print(f"=== Messages NOT scored (below threshold): {len(not_scored)} ===")
for r in not_scored:
    print(f"  {r['ts_dt'][:16]} {r['channel'][-10:]} | {r['text'][:120]}")

conn.close()
