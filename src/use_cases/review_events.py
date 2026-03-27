"""Use case: Review, approve, reject, and edit extracted events.

Implements the human review workflow with audit trail.
"""

from datetime import UTC, datetime
from typing import Any

from src.config.logging_config import get_logger
from src.domain.models import (
    Event,
    EventAuditEntry,
    EventOrigin,
    EventVersion,
    ReviewLifecycleStatus,
)
from src.domain.protocols import RepositoryProtocol

logger = get_logger(__name__)

# Confidence threshold: events above this are auto-published
AUTO_PUBLISH_CONFIDENCE_THRESHOLD = 0.95


class ReviewEventsUseCase:
    """Orchestrates event review, editing, and publication workflow."""

    def __init__(self, repo: RepositoryProtocol) -> None:
        self._repo = repo

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_review_queue(
        self,
        status: ReviewLifecycleStatus | None = ReviewLifecycleStatus.NEEDS_REVIEW,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Event]:
        """Return events for the review queue."""
        return self._repo.get_events_for_review(
            status=status, limit=limit, offset=offset
        )

    def get_event_detail(self, event_id: str) -> Event | None:
        """Get a single event by ID."""
        return self._repo.get_event_by_id(event_id)

    def get_audit_trail(self, event_id: str) -> list[EventAuditEntry]:
        """Get the full audit log for an event."""
        return self._repo.get_audit_log(event_id)

    def get_versions(self, event_id: str) -> list[EventVersion]:
        """Get all historical snapshots of an event."""
        return self._repo.get_event_versions(event_id)

    def get_stats(self) -> dict[str, int]:
        """Get count of events by review status."""
        return self._repo.count_events_by_review_status()

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def approve_event(self, event_id: str, actor: str) -> bool:
        """Approve an event → review_status = approved.

        Args:
            event_id: UUID string
            actor: User performing the action

        Returns:
            True if successful
        """
        event = self._repo.get_event_by_id(event_id)
        if event is None:
            logger.warning("review_approve_not_found", event_id=event_id)
            return False

        now = datetime.now(tz=UTC)
        ok = self._repo.update_event_review(
            event_id=event_id,
            review_status=ReviewLifecycleStatus.APPROVED,
            reviewed_by=actor,
        )
        if ok:
            self._write_audit(
                event=event,
                action="approved",
                origin=EventOrigin.HUMAN_REVIEW,
                actor=actor,
                changes={
                    "review_status": {
                        "old": event.review_status.value,
                        "new": "approved",
                    }
                },
                timestamp=now,
            )
            logger.info("review_approved", event_id=event_id, actor=actor)
        return ok

    def reject_event(self, event_id: str, actor: str, note: str | None = None) -> bool:
        """Reject an event → review_status = rejected."""
        event = self._repo.get_event_by_id(event_id)
        if event is None:
            logger.warning("review_reject_not_found", event_id=event_id)
            return False

        now = datetime.now(tz=UTC)
        ok = self._repo.update_event_review(
            event_id=event_id,
            review_status=ReviewLifecycleStatus.REJECTED,
            reviewed_by=actor,
        )
        if ok:
            self._write_audit(
                event=event,
                action="rejected",
                origin=EventOrigin.HUMAN_REVIEW,
                actor=actor,
                changes={
                    "review_status": {
                        "old": event.review_status.value,
                        "new": "rejected",
                    }
                },
                timestamp=now,
                note=note,
            )
            logger.info("review_rejected", event_id=event_id, actor=actor)
        return ok

    def publish_event(self, event_id: str, actor: str) -> bool:
        """Publish an approved event → review_status = published."""
        event = self._repo.get_event_by_id(event_id)
        if event is None:
            return False

        now = datetime.now(tz=UTC)
        ok = self._repo.update_event_review(
            event_id=event_id,
            review_status=ReviewLifecycleStatus.PUBLISHED,
            reviewed_by=actor,
        )
        if ok:
            self._write_audit(
                event=event,
                action="published",
                origin=EventOrigin.HUMAN_REVIEW,
                actor=actor,
                changes={
                    "review_status": {
                        "old": event.review_status.value,
                        "new": "published",
                    }
                },
                timestamp=now,
            )
            logger.info("review_published", event_id=event_id, actor=actor)
        return ok

    def edit_event(self, event_id: str, actor: str, updates: dict[str, Any]) -> bool:
        """Edit event fields. Creates a new version snapshot + audit entry.

        Args:
            event_id: UUID string
            actor: User performing the edit
            updates: Field-value pairs to patch

        Returns:
            True if successful
        """
        event = self._repo.get_event_by_id(event_id)
        if event is None:
            logger.warning("review_edit_not_found", event_id=event_id)
            return False

        # Compute changes diff
        changes: dict[str, Any] = {}
        event_dict = event.model_dump(mode="json")
        for field, new_val in updates.items():
            old_val = event_dict.get(field)
            if old_val != new_val:
                changes[field] = {"old": old_val, "new": new_val}

        if not changes:
            logger.info("review_edit_no_changes", event_id=event_id)
            return True  # No-op is success

        now = datetime.now(tz=UTC)

        # Save current state as version snapshot (before applying changes)
        self._repo.save_event_version(
            EventVersion(
                event_id=event.event_id,
                version=event.version,
                origin=event.origin,
                snapshot=event_dict,
                created_at=now,
            )
        )

        # Apply updates
        ok = self._repo.update_event_fields(event_id=event_id, updates=updates)
        if ok:
            self._write_audit(
                event=event,
                action="edited",
                origin=EventOrigin.HUMAN_EDIT,
                actor=actor,
                changes=changes,
                timestamp=now,
            )
            logger.info(
                "review_edited",
                event_id=event_id,
                actor=actor,
                changed_fields=list(changes.keys()),
            )
        return ok

    def auto_publish_high_confidence(self) -> int:
        """Auto-publish events with confidence >= threshold.

        Returns:
            Number of events auto-published
        """
        events = self._repo.get_events_for_review(
            status=ReviewLifecycleStatus.NEEDS_REVIEW, limit=500
        )
        count = 0
        for event in events:
            if event.confidence >= AUTO_PUBLISH_CONFIDENCE_THRESHOLD:
                self._repo.update_event_review(
                    event_id=str(event.event_id),
                    review_status=ReviewLifecycleStatus.PUBLISHED,
                    reviewed_by="auto_publish",
                )
                self._write_audit(
                    event=event,
                    action="published",
                    origin=EventOrigin.AI_EXTRACTION,
                    actor="auto_publish",
                    changes={
                        "review_status": {
                            "old": "needs_review",
                            "new": "published",
                        }
                    },
                )
                count += 1

        if count:
            logger.info("auto_publish_completed", count=count)
        return count

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write_audit(
        self,
        event: Event,
        action: str,
        origin: EventOrigin,
        actor: str,
        changes: dict[str, Any],
        timestamp: datetime | None = None,
        note: str | None = None,
    ) -> None:
        """Write an audit entry and swallow errors (non-critical)."""
        try:
            self._repo.save_audit_entry(
                EventAuditEntry(
                    event_id=event.event_id,
                    version=event.version,
                    action=action,
                    origin=origin,
                    changes=changes,
                    actor=actor,
                    timestamp=timestamp or datetime.now(tz=UTC),
                    note=note,
                )
            )
        except Exception:
            logger.exception(
                "audit_write_failed",
                event_id=str(event.event_id),
                action=action,
            )
