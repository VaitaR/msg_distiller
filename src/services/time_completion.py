"""Time completion policy for extracted events.

This module implements P0.1 from docs/TECHNICAL_SPEC_EXTRACTION_QUALITY.md:
if the LLM response is missing a required time field for a given status, fill it
from the source message timestamp and mark it as a low-confidence fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pytz

from src.domain.models import Event, EventStatus, TimeSource


@dataclass(frozen=True, slots=True)
class TimeCompletionResult:
    """Result of applying time completion to an event."""

    changed: bool
    completed_field: str | None
    used_fallback_ts: datetime | None


def _normalize_to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=pytz.UTC)
    return dt.astimezone(pytz.UTC)


def apply_time_completion_policy(
    event: Event,
    *,
    message_published_at: datetime | None,
    fallback_ts: datetime,
    confidence_cap: float = 0.3,
) -> TimeCompletionResult:
    """Fill missing required time fields based on event status.

    Rules (only if the target field is empty):
    - planned|confirmed -> planned_start = message_published_at
    - started -> actual_start = message_published_at
    - completed -> actual_end = message_published_at

    If a fallback is applied, set ``time_source=ts_fallback`` and cap
    ``time_confidence`` to ``confidence_cap``.
    """

    effective_ts = (
        _normalize_to_utc(message_published_at)
        if message_published_at is not None
        else _normalize_to_utc(fallback_ts)
    )

    completed_field: str | None = None

    if event.status in (EventStatus.PLANNED, EventStatus.CONFIRMED):
        if event.planned_start is None:
            event.planned_start = effective_ts
            completed_field = "planned_start"
    elif event.status == EventStatus.STARTED:
        if event.actual_start is None:
            event.actual_start = effective_ts
            completed_field = "actual_start"
    elif event.status == EventStatus.COMPLETED:
        if event.actual_end is None:
            event.actual_end = effective_ts
            completed_field = "actual_end"

    if completed_field is None:
        return TimeCompletionResult(
            changed=False,
            completed_field=None,
            used_fallback_ts=None,
        )

    event.time_source = TimeSource.TS_FALLBACK
    event.time_confidence = min(event.time_confidence, confidence_cap)

    return TimeCompletionResult(
        changed=True,
        completed_field=completed_field,
        used_fallback_ts=effective_ts,
    )
