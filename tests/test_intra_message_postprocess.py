"""Tests for intra-message post-processing (P1.2)."""

from __future__ import annotations

from datetime import UTC, datetime

from src.domain.models import TimeSource
from src.services.intra_message_postprocess import dedup_and_rank_events_for_message
from tests.conftest import create_test_event


def test_dedup_and_rank_prefers_late_anchor_over_early_noise() -> None:
    ts = datetime(2025, 12, 1, 12, 0, tzinfo=UTC)

    early = create_test_event(status="updated").model_copy(
        update={
            "anchor": None,
            "anchors": [],
            "time_source": TimeSource.TS_FALLBACK,
            "time_confidence": 0.1,
            "confidence": 0.4,
            "message_published_at": ts,
        }
    )

    late = create_test_event(status="updated").model_copy(
        update={
            "anchor": "ABC-123",
            "anchors": ["ABC-123"],
            "time_source": TimeSource.EXPLICIT,
            "time_confidence": 0.9,
            "confidence": 0.7,
            "message_published_at": ts,
        }
    )

    selected = dedup_and_rank_events_for_message([early, late], max_events=1)
    assert len(selected) == 1
    assert selected[0].anchor == "ABC-123"


def test_dedup_and_rank_deduplicates_by_anchor_and_keeps_best() -> None:
    ts = datetime(2025, 12, 1, 12, 0, tzinfo=UTC)

    worse = create_test_event(status="updated").model_copy(
        update={
            "anchor": "PROJ-1",
            "anchors": ["PROJ-1"],
            "time_source": TimeSource.RELATIVE,
            "time_confidence": 0.6,
            "confidence": 0.6,
            "message_published_at": ts,
        }
    )
    better = create_test_event(status="updated").model_copy(
        update={
            "anchor": "PROJ-1",
            "anchors": ["PROJ-1"],
            "time_source": TimeSource.EXPLICIT,
            "time_confidence": 0.7,
            "confidence": 0.9,
            "message_published_at": ts,
        }
    )

    selected = dedup_and_rank_events_for_message([worse, better], max_events=None)
    assert len(selected) == 1
    assert selected[0].confidence == 0.9
