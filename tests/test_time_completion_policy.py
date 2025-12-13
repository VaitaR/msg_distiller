"""Tests for TimeCompletionPolicy (P0.1)."""

from __future__ import annotations

from datetime import UTC, datetime

from src.domain.models import EventStatus, TimeSource
from src.services.time_completion import apply_time_completion_policy
from tests.conftest import create_test_event


def test_time_completion_fills_required_fields_and_caps_confidence() -> None:
    published_at = datetime(2025, 12, 1, 12, 0, tzinfo=UTC)
    fallback_ts = datetime(2025, 12, 1, 11, 0, tzinfo=UTC)

    planned = create_test_event(status="planned").model_copy(
        update={
            "planned_start": None,
            "actual_start": None,
            "actual_end": None,
            "message_published_at": published_at,
            "time_source": TimeSource.EXPLICIT,
            "time_confidence": 0.95,
        }
    )
    result = apply_time_completion_policy(
        planned,
        message_published_at=planned.message_published_at,
        fallback_ts=fallback_ts,
    )
    assert result.changed is True
    assert planned.status == EventStatus.PLANNED
    assert planned.planned_start == published_at
    assert planned.time_source == TimeSource.TS_FALLBACK
    assert planned.time_confidence <= 0.3

    started = create_test_event(status="started").model_copy(
        update={
            "actual_start": None,
            "actual_end": None,
            "message_published_at": published_at,
            "time_source": TimeSource.EXPLICIT,
            "time_confidence": 0.9,
        }
    )
    result = apply_time_completion_policy(
        started,
        message_published_at=started.message_published_at,
        fallback_ts=fallback_ts,
    )
    assert result.changed is True
    assert started.status == EventStatus.STARTED
    assert started.actual_start == published_at
    assert started.time_source == TimeSource.TS_FALLBACK
    assert started.time_confidence <= 0.3

    completed = create_test_event(status="completed").model_copy(
        update={
            "actual_end": None,
            "message_published_at": published_at,
            "time_source": TimeSource.EXPLICIT,
            "time_confidence": 0.8,
        }
    )
    result = apply_time_completion_policy(
        completed,
        message_published_at=completed.message_published_at,
        fallback_ts=fallback_ts,
    )
    assert result.changed is True
    assert completed.status == EventStatus.COMPLETED
    assert completed.actual_end == published_at
    assert completed.time_source == TimeSource.TS_FALLBACK
    assert completed.time_confidence <= 0.3


def test_time_completion_noop_for_non_required_status() -> None:
    published_at = datetime(2025, 12, 1, 12, 0, tzinfo=UTC)
    event = create_test_event(status="updated").model_copy(
        update={
            "planned_start": None,
            "actual_start": None,
            "actual_end": None,
            "message_published_at": published_at,
        }
    )
    result = apply_time_completion_policy(
        event,
        message_published_at=event.message_published_at,
        fallback_ts=published_at,
    )
    assert result.changed is False


def test_time_completion_uses_fallback_ts_when_message_ts_missing() -> None:
    fallback_ts = datetime(2025, 12, 1, 11, 0, tzinfo=UTC)
    planned = create_test_event(status="planned").model_copy(
        update={
            "planned_start": None,
            "actual_start": None,
            "actual_end": None,
            "message_published_at": None,
            "time_source": TimeSource.EXPLICIT,
            "time_confidence": 0.9,
        }
    )
    result = apply_time_completion_policy(
        planned,
        message_published_at=None,
        fallback_ts=fallback_ts,
    )
    assert result.changed is True
    assert planned.planned_start == fallback_ts
