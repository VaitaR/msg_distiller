"""Tests for the review_events use case."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.domain.models import (
    ActionType,
    ChangeType,
    Event,
    EventCategory,
    EventOrigin,
    EventStatus,
    MessageSource,
    ReviewLifecycleStatus,
    TimeSource,
)
from src.use_cases.review_events import ReviewEventsUseCase


def _make_event(**overrides: Any) -> Event:
    """Create a test Event with sensible defaults."""
    defaults: dict[str, Any] = {
        "event_id": uuid4(),
        "message_id": "test-msg-001",
        "action": ActionType.LAUNCH,
        "object_name_raw": "Test Feature",
        "category": EventCategory.PRODUCT,
        "status": EventStatus.PLANNED,
        "change_type": ChangeType.LAUNCH,
        "time_source": TimeSource.TS_FALLBACK,
        "time_confidence": 0.5,
        "summary": "Test event summary",
        "confidence": 0.8,
        "importance": 60,
        "cluster_key": "test-cluster",
        "dedup_key": "test-dedup",
        "source_id": MessageSource.SLACK,
        "review_status": ReviewLifecycleStatus.NEEDS_REVIEW,
        "version": 1,
        "origin": EventOrigin.AI_EXTRACTION,
    }
    defaults.update(overrides)
    return Event(**defaults)


@pytest.fixture
def mock_repo() -> MagicMock:
    """Create a mock repository."""
    return MagicMock()


@pytest.fixture
def use_case(mock_repo: MagicMock) -> ReviewEventsUseCase:
    """Create ReviewEventsUseCase with mock repo."""
    return ReviewEventsUseCase(repo=mock_repo)


class TestApproveEvent:
    def test_approve_existing_event(
        self, use_case: ReviewEventsUseCase, mock_repo: MagicMock
    ) -> None:
        event = _make_event()
        mock_repo.get_event_by_id.return_value = event
        mock_repo.update_event_review.return_value = True

        result = use_case.approve_event(str(event.event_id), "user1")

        assert result is True
        mock_repo.update_event_review.assert_called_once_with(
            event_id=str(event.event_id),
            review_status=ReviewLifecycleStatus.APPROVED,
            reviewed_by="user1",
        )
        mock_repo.save_audit_entry.assert_called_once()

    def test_approve_nonexistent_event(
        self, use_case: ReviewEventsUseCase, mock_repo: MagicMock
    ) -> None:
        mock_repo.get_event_by_id.return_value = None

        result = use_case.approve_event("nonexistent-id", "user1")

        assert result is False
        mock_repo.update_event_review.assert_not_called()


class TestRejectEvent:
    def test_reject_with_note(
        self, use_case: ReviewEventsUseCase, mock_repo: MagicMock
    ) -> None:
        event = _make_event()
        mock_repo.get_event_by_id.return_value = event
        mock_repo.update_event_review.return_value = True

        result = use_case.reject_event(str(event.event_id), "user1", note="Duplicate")

        assert result is True
        mock_repo.update_event_review.assert_called_once_with(
            event_id=str(event.event_id),
            review_status=ReviewLifecycleStatus.REJECTED,
            reviewed_by="user1",
        )
        audit_call = mock_repo.save_audit_entry.call_args[0][0]
        assert audit_call.note == "Duplicate"


class TestEditEvent:
    def test_edit_creates_version_and_audit(
        self, use_case: ReviewEventsUseCase, mock_repo: MagicMock
    ) -> None:
        event = _make_event(summary="Old summary")
        mock_repo.get_event_by_id.return_value = event
        mock_repo.update_event_fields.return_value = True

        result = use_case.edit_event(
            str(event.event_id), "editor1", {"summary": "New summary"}
        )

        assert result is True
        mock_repo.save_event_version.assert_called_once()
        mock_repo.update_event_fields.assert_called_once()
        mock_repo.save_audit_entry.assert_called_once()

    def test_edit_noop_when_no_changes(
        self, use_case: ReviewEventsUseCase, mock_repo: MagicMock
    ) -> None:
        event = _make_event(summary="Same summary")
        mock_repo.get_event_by_id.return_value = event

        result = use_case.edit_event(
            str(event.event_id), "editor1", {"summary": "Same summary"}
        )

        assert result is True
        mock_repo.save_event_version.assert_not_called()
        mock_repo.update_event_fields.assert_not_called()


class TestAutoPublish:
    def test_auto_publish_high_confidence(
        self, use_case: ReviewEventsUseCase, mock_repo: MagicMock
    ) -> None:
        high_conf = _make_event(confidence=0.98)
        low_conf = _make_event(confidence=0.5)
        mock_repo.get_events_for_review.return_value = [high_conf, low_conf]
        mock_repo.update_event_review.return_value = True

        count = use_case.auto_publish_high_confidence()

        assert count == 1
        mock_repo.update_event_review.assert_called_once()


class TestGetReviewQueue:
    def test_returns_events(
        self, use_case: ReviewEventsUseCase, mock_repo: MagicMock
    ) -> None:
        events = [_make_event(), _make_event()]
        mock_repo.get_events_for_review.return_value = events

        result = use_case.get_review_queue()

        assert len(result) == 2
        mock_repo.get_events_for_review.assert_called_once_with(
            status=ReviewLifecycleStatus.NEEDS_REVIEW,
            limit=100,
            offset=0,
        )
