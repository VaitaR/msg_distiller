#!/usr/bin/env python3
"""Compute extraction quality metrics from persisted events/messages.

Metrics:
- % multi-event messages
- % future-like
- % action=Other
- % low utility summaries
- % low coverage summaries
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path

from src.adapters.sqlite_repository import SQLiteRepository
from src.services.extraction_policy import (
    is_future_like_without_evidence,
    is_low_coverage_summary,
    is_low_utility_summary,
)


def compute_metrics(
    db_path: str,
) -> dict[str, float | int | dict[str, dict[str, float | int]]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT e.*, m.text AS raw_text
        FROM events e
        LEFT JOIN raw_slack_messages m ON m.message_id = e.message_id
        """
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    total_events = len(rows)
    if total_events == 0:
        return {
            "events_total": 0,
            "event_messages_total": 0,
            "pct_multi_event_messages": 0.0,
            "pct_future_like": 0.0,
            "pct_action_other": 0.0,
            "pct_low_utility_summaries": 0.0,
            "pct_low_coverage_summaries": 0.0,
            "channel_event_recall": {},
        }

    repo = SQLiteRepository(db_path)

    per_message = Counter(r["message_id"] for r in rows if r["message_id"])
    event_messages_total = len(per_message)
    multi_event_messages = sum(1 for _, c in per_message.items() if c >= 2)

    future_like = 0
    action_other = 0
    low_utility = 0
    low_coverage = 0

    for row in rows:
        event = repo._row_to_event(row)
        raw_text = row.get("raw_text") or ""
        if is_future_like_without_evidence(event, raw_text):
            future_like += 1
        if event.action.value == "Other":
            action_other += 1
        if is_low_utility_summary(event):
            low_utility += 1
        if is_low_coverage_summary(event, raw_text):
            low_coverage += 1

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT channel, COUNT(*) AS c
        FROM event_candidates
        WHERE source_id = 'slack'
        GROUP BY channel
        """
    )
    candidates_by_channel = {str(r["channel"]): int(r["c"]) for r in cur.fetchall()}

    cur.execute(
        """
        SELECT m.channel AS channel, COUNT(*) AS c
        FROM events e
        JOIN raw_slack_messages m ON m.message_id = e.message_id
        WHERE e.source_id = 'slack'
        GROUP BY m.channel
        """
    )
    events_by_channel = {str(r["channel"]): int(r["c"]) for r in cur.fetchall()}
    conn.close()

    channel_recall: dict[str, dict[str, float | int]] = {}
    all_channels = sorted(set(candidates_by_channel) | set(events_by_channel))
    for channel in all_channels:
        candidates = candidates_by_channel.get(channel, 0)
        events = events_by_channel.get(channel, 0)
        recall_pct = round((events / candidates) * 100, 2) if candidates else 0.0
        channel_recall[channel] = {
            "candidates": candidates,
            "events": events,
            "event_per_candidate_pct": recall_pct,
        }

    return {
        "events_total": total_events,
        "event_messages_total": event_messages_total,
        "pct_multi_event_messages": round(
            (multi_event_messages / max(1, event_messages_total)) * 100, 2
        ),
        "pct_future_like": round((future_like / total_events) * 100, 2),
        "pct_action_other": round((action_other / total_events) * 100, 2),
        "pct_low_utility_summaries": round((low_utility / total_events) * 100, 2),
        "pct_low_coverage_summaries": round((low_coverage / total_events) * 100, 2),
        "channel_event_recall": channel_recall,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Extraction quality metrics report")
    parser.add_argument(
        "--db-path",
        type=str,
        default="data/slack_events.db",
        help="Path to SQLite DB (default: data/slack_events.db)",
    )
    args = parser.parse_args()

    db_path = Path(args.db_path)
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    report = compute_metrics(str(db_path))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
