"""Post-processing for events extracted from a single message.

Implements P1.2 from docs/TECHNICAL_SPEC_EXTRACTION_QUALITY.md:
- Deduplicate events within a single message after chunking
- Rank events before applying per-message limits
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.domain.models import Event, TimeSource


@dataclass(frozen=True, slots=True)
class RankedEvent:
    event: Event
    rank_key: tuple[int, int, float, float]
    original_index: int


def _primary_time(event: Event) -> datetime | None:
    return (
        event.actual_start
        or event.actual_end
        or event.planned_start
        or event.planned_end
        or event.message_published_at
    )


def _time_source_weight(source: TimeSource) -> int:
    if source == TimeSource.EXPLICIT:
        return 2
    if source == TimeSource.RELATIVE:
        return 1
    return 0


def _rank_key(event: Event) -> tuple[int, int, float, float]:
    has_anchor = 1 if (event.anchor or event.anchors) else 0
    return (
        has_anchor,
        _time_source_weight(event.time_source),
        float(event.confidence),
        float(event.time_confidence),
    )


def _dedup_key(event: Event) -> tuple[str, str, str, str]:
    anchor_key = (event.anchor or (event.anchors[0] if event.anchors else "")).strip()
    if anchor_key:
        return ("anchor", anchor_key.lower(), "", "")

    object_key = (event.object_id or event.object_name_raw).lower().strip()
    primary = _primary_time(event)
    bucket = primary.date().isoformat() if primary else "no-time"
    return ("attrs", event.action.value.lower(), object_key, bucket)


def dedup_and_rank_events_for_message(
    events: list[Event],
    *,
    max_events: int | None,
) -> list[Event]:
    """Deduplicate and rank events extracted from a single message."""

    if not events:
        return []

    ranked: list[RankedEvent] = [
        RankedEvent(event=event, rank_key=_rank_key(event), original_index=index)
        for index, event in enumerate(events)
    ]

    ranked.sort(key=lambda item: (item.rank_key, -item.original_index), reverse=True)

    kept: list[RankedEvent] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in ranked:
        key = _dedup_key(item.event)
        if key in seen:
            continue
        seen.add(key)
        kept.append(item)

    kept.sort(key=lambda item: (item.rank_key, -item.original_index), reverse=True)
    selected = [item.event for item in kept]

    if max_events is None:
        return selected
    if max_events <= 0:
        return []
    return selected[:max_events]


def enforce_primary_sub_event_policy(events: list[Event]) -> list[Event]:
    """Allow one primary event and at most one tightly-bound sub-event.

    Primary event is the first event (already ranked by importance/confidence in caller).
    A sub-event is allowed only when tightly bound to the same release/change unit.
    """

    if not events:
        return []

    primary = events[0]
    if len(events) == 1:
        return [primary]

    secondary = events[1]

    # Tight binding via shared anchor or same object+action pair.
    primary_anchor = (
        (primary.anchor or (primary.anchors[0] if primary.anchors else ""))
        .strip()
        .lower()
    )
    secondary_anchor = (
        (secondary.anchor or (secondary.anchors[0] if secondary.anchors else ""))
        .strip()
        .lower()
    )
    shared_anchor = bool(
        primary_anchor and secondary_anchor and primary_anchor == secondary_anchor
    )

    shared_object = (primary.object_id or primary.object_name_raw).strip().lower() == (
        secondary.object_id or secondary.object_name_raw
    ).strip().lower()
    shared_action = primary.action == secondary.action

    if shared_anchor or (shared_object and shared_action):
        return [primary, secondary]

    return [primary]
