"""Tests for intra-message post-processing (P1.2)."""

from __future__ import annotations

from datetime import UTC, datetime

from src.domain.models import TimeSource
from src.services.intra_message_postprocess import (
    dedup_and_rank_events_for_message,
    enforce_primary_sub_event_policy,
)
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


def test_primary_sub_policy_keeps_second_when_tightly_bound_by_anchor() -> None:
    primary = create_test_event().model_copy(
        update={
            "anchor": "ABC-1",
            "anchors": ["ABC-1"],
            "object_name_raw": "Wallet Rewards",
        }
    )
    secondary = create_test_event().model_copy(
        update={
            "anchor": "ABC-1",
            "anchors": ["ABC-1"],
            "object_name_raw": "Wallet Rewards",
        }
    )

    result = enforce_primary_sub_event_policy([primary, secondary])
    assert len(result) == 2


def test_primary_sub_policy_drops_unbound_secondary() -> None:
    primary = create_test_event().model_copy(
        update={
            "anchor": "ABC-1",
            "anchors": ["ABC-1"],
            "object_name_raw": "Wallet Rewards",
        }
    )
    secondary = create_test_event().model_copy(
        update={
            "anchor": "XYZ-9",
            "anchors": ["XYZ-9"],
            "object_name_raw": "Perps",
        }
    )

    result = enforce_primary_sub_event_policy([primary, secondary])
    assert len(result) == 1
    assert result[0].anchor == "ABC-1"
