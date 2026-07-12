"""Tests for semantic dedup merge and unmerge workflow.

Coverage:
- should_merge_events: semantic path (no anchors, similar titles)
- should_merge_events: anchor path (standard)
- should_merge_events: dissimilar titles blocked
- merge_events: returns (survivor, archived_absorbed) tuple
- merge_events: survivor gains ABSORBED_FROM relation
- deduplicate_event_list: returns (survivors, absorbed) tuple
- Full unmerge integration via ReviewEventsUseCase + SQLiteRepository
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from src.adapters.sqlite_repository import SQLiteRepository
from src.domain.models import (
    ActionType,
    ChangeType,
    Environment,
    Event,
    EventCategory,
    EventOrigin,
    EventStatus,
    MessageSource,
    RelationType,
    ReviewLifecycleStatus,
    TimeSource,
)
from src.services.deduplicator import (
    deduplicate_event_list,
    merge_events,
    should_merge_events,
)
from src.use_cases.review_events import ReviewEventsUseCase

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 3, 15, 12, 0, 0, tzinfo=UTC)


def _make_event(
    *,
    n: int,
    object_name: str,
    anchors: list[str] | None = None,
    links: list[str] | None = None,
    actual_start: datetime | None = None,
    source_id: MessageSource = MessageSource.SLACK,
    review_status: ReviewLifecycleStatus = ReviewLifecycleStatus.NEEDS_REVIEW,
) -> Event:
    """Create a minimal but valid Event for dedup tests."""
    return Event(
        event_id=UUID(f"00000000-0000-0000-0000-{n:012d}"),
        message_id=f"msg-dedup-{n:03d}",
        source_channels=["#releases"],
        action=ActionType.LAUNCH,
        object_name_raw=object_name,
        category=EventCategory.PRODUCT,
        status=EventStatus.COMPLETED,
        change_type=ChangeType.LAUNCH,
        environment=Environment.PROD,
        planned_start=_NOW,
        planned_end=_NOW + timedelta(hours=2),
        actual_start=actual_start or _NOW,
        actual_end=_NOW + timedelta(hours=2),
        time_source=TimeSource.EXPLICIT,
        time_confidence=0.9,
        summary=f"Summary for event {n}.",
        confidence=0.85,
        importance=70,
        cluster_key=f"cluster-{n}",
        dedup_key=f"dedup-{n}",
        anchors=anchors or [],
        links=links or [],
        source_id=source_id,
        review_status=review_status,
        origin=EventOrigin.AI_EXTRACTION,
        version=1,
        extracted_at=_NOW,
    )


# ---------------------------------------------------------------------------
# should_merge_events — semantic path
# ---------------------------------------------------------------------------


class TestShouldMergeEventsSemantic:
    """Semantic (anchor-free) merge path tests."""

    def test_semantic_merge_fires_for_similar_titles(self) -> None:
        """High-similarity object names merge even without anchor overlap."""
        evt1 = _make_event(n=1, object_name="loyalty program in Wallet")
        evt2 = _make_event(n=2, object_name="wallet loyalty program v1.0")
        # Both have no anchors → should fall through to semantic path
        assert should_merge_events(evt1, evt2) is True

    def test_semantic_merge_case_insensitive(self) -> None:
        """Semantic comparison is case-insensitive."""
        evt1 = _make_event(n=1, object_name="Telegram Stars Integration")
        evt2 = _make_event(n=2, object_name="telegram stars integration launch")
        assert should_merge_events(evt1, evt2) is True

    def test_semantic_merge_blocked_for_dissimilar_names(self) -> None:
        """Very different topics do NOT merge on semantic path."""
        evt1 = _make_event(n=1, object_name="loyalty program in Wallet")
        evt2 = _make_event(n=2, object_name="database migration PostgreSQL")
        assert should_merge_events(evt1, evt2) is False

    def test_semantic_merge_blocked_for_different_sources(self) -> None:
        """Cross-source events never merge, even with identical names."""
        evt1 = _make_event(
            n=1, object_name="Wallet loyalty program", source_id=MessageSource.SLACK
        )
        evt2 = _make_event(
            n=2, object_name="Wallet loyalty program", source_id=MessageSource.TELEGRAM
        )
        assert should_merge_events(evt1, evt2) is False

    def test_semantic_merge_blocked_outside_date_window(self) -> None:
        """Semantic path still respects date window."""
        evt1 = _make_event(n=1, object_name="Wallet loyalty program", actual_start=_NOW)
        evt2 = _make_event(
            n=2,
            object_name="Wallet loyalty program v2",
            actual_start=_NOW + timedelta(hours=200),  # 200h > 48h default
        )
        assert should_merge_events(evt1, evt2) is False

    def test_semantic_merge_same_message_id_blocked(self) -> None:
        """Same message_id is always blocked (Rule 1), even with matching names."""
        evt1 = _make_event(n=1, object_name="Wallet loyalty program")
        evt2 = evt1.model_copy(
            update={"event_id": UUID("00000000-0000-0000-0000-000000000099")}
        )
        assert should_merge_events(evt1, evt2) is False


# ---------------------------------------------------------------------------
# should_merge_events — anchor path (standard, regression)
# ---------------------------------------------------------------------------


class TestShouldMergeEventsAnchorPath:
    """Anchor path works as before after the semantic fallback refactor."""

    def test_anchor_path_fires_with_overlap_and_similar_title(self) -> None:
        evt1 = _make_event(n=1, object_name="Payments v2 rollout", anchors=["PROJ-123"])
        evt2 = _make_event(n=2, object_name="Payments v2 rollout", anchors=["PROJ-123"])
        assert should_merge_events(evt1, evt2) is True

    def test_anchor_path_blocked_for_low_title_similarity(self) -> None:
        """Anchor overlap alone is not enough — titles must also be similar."""
        evt1 = _make_event(n=1, object_name="Auth service down", anchors=["PROJ-999"])
        evt2 = _make_event(
            n=2, object_name="Payment rollback completed", anchors=["PROJ-999"]
        )
        assert should_merge_events(evt1, evt2) is False


# ---------------------------------------------------------------------------
# merge_events
# ---------------------------------------------------------------------------


class TestMergeEvents:
    """merge_events returns (survivor, archived_absorbed) tuple."""

    def test_returns_tuple(self) -> None:
        evt1 = _make_event(n=1, object_name="Loyalty program launch")
        evt2 = _make_event(n=2, object_name="Wallet loyalty program v1.0")
        result = merge_events(evt1, evt2)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_survivor_keeps_primary_event_id(self) -> None:
        evt1 = _make_event(n=1, object_name="Loyalty program launch")
        evt2 = _make_event(n=2, object_name="Wallet loyalty program v1.0")
        survivor, _absorbed = merge_events(evt1, evt2)
        assert survivor.event_id == evt1.event_id

    def test_absorbed_is_archived(self) -> None:
        evt1 = _make_event(n=1, object_name="Loyalty program launch")
        evt2 = _make_event(n=2, object_name="Wallet loyalty program v1.0")
        _survivor, absorbed = merge_events(evt1, evt2)
        assert absorbed.event_id == evt2.event_id
        assert absorbed.review_status == ReviewLifecycleStatus.ARCHIVED
        assert absorbed.origin == EventOrigin.SYSTEM_MERGE

    def test_survivor_has_absorbed_from_relation(self) -> None:
        evt1 = _make_event(n=1, object_name="Loyalty program launch")
        evt2 = _make_event(n=2, object_name="Wallet loyalty program v1.0")
        survivor, _absorbed = merge_events(evt1, evt2)
        absorbed_relations = [
            r
            for r in survivor.relations
            if r.relation_type == RelationType.ABSORBED_FROM
        ]
        assert len(absorbed_relations) == 1
        assert absorbed_relations[0].target_event_id == evt2.event_id

    def test_survivor_bumps_version(self) -> None:
        evt1 = _make_event(n=1, object_name="Loyalty program launch")
        evt2 = _make_event(n=2, object_name="Wallet loyalty program v1.0")
        survivor, _absorbed = merge_events(evt1, evt2)
        assert survivor.version == evt1.version + 1

    def test_survivor_merges_channels(self) -> None:
        evt1 = _make_event(n=1, object_name="Service X")
        evt2 = _make_event(n=2, object_name="Service X launch")
        evt1 = evt1.model_copy(update={"source_channels": ["#releases"]})
        evt2 = evt2.model_copy(update={"source_channels": ["#engineering"]})
        survivor, _absorbed = merge_events(evt1, evt2)
        assert "#releases" in survivor.source_channels
        assert "#engineering" in survivor.source_channels


# ---------------------------------------------------------------------------
# deduplicate_event_list
# ---------------------------------------------------------------------------


class TestDeduplicateEventList:
    """deduplicate_event_list returns (survivors, absorbed_events) tuple."""

    def test_empty_input(self) -> None:
        survivors, absorbed = deduplicate_event_list([])
        assert survivors == []
        assert absorbed == []

    def test_no_merge_when_all_dissimilar(self) -> None:
        events = [
            _make_event(n=1, object_name="Auth service incident"),
            _make_event(n=2, object_name="Database migration completed"),
            _make_event(n=3, object_name="Telegram Stars launch"),
        ]
        survivors, absorbed = deduplicate_event_list(events)
        assert len(survivors) == 3
        assert len(absorbed) == 0

    def test_semantic_merge_reduces_survivors(self) -> None:
        evt1 = _make_event(n=1, object_name="loyalty program in Wallet")
        evt2 = _make_event(n=2, object_name="wallet loyalty program v1.0")
        evt3 = _make_event(n=3, object_name="database migration PostgreSQL")
        survivors, absorbed = deduplicate_event_list([evt1, evt2, evt3])
        assert len(survivors) == 2, f"Expected 2 survivors, got {len(survivors)}"
        assert len(absorbed) == 1, f"Expected 1 absorbed, got {len(absorbed)}"

    def test_absorbed_event_is_archived(self) -> None:
        evt1 = _make_event(n=1, object_name="loyalty program in Wallet")
        evt2 = _make_event(n=2, object_name="wallet loyalty program v1.0")
        _survivors, absorbed = deduplicate_event_list([evt1, evt2])
        assert len(absorbed) == 1
        assert absorbed[0].review_status == ReviewLifecycleStatus.ARCHIVED

    def test_survivor_has_absorbed_from_relation(self) -> None:
        evt1 = _make_event(n=1, object_name="loyalty program in Wallet")
        evt2 = _make_event(n=2, object_name="wallet loyalty program v1.0")
        survivors, absorbed = deduplicate_event_list([evt1, evt2])
        assert len(survivors) == 1
        rel_types = [r.relation_type for r in survivors[0].relations]
        assert RelationType.ABSORBED_FROM in rel_types

    def test_total_events_count_preserved(self) -> None:
        """Total events (survivors + absorbed) equals input count."""
        events = [
            _make_event(n=i, object_name=name)
            for i, name in enumerate(
                [
                    "loyalty program in Wallet",
                    "wallet loyalty program v1.0",
                    "Telegram Stars payment feature",
                    "payment via Telegram Stars",
                    "database migration PostgreSQL",
                ],
                start=1,
            )
        ]
        survivors, absorbed = deduplicate_event_list(events)
        assert len(survivors) + len(absorbed) == len(events)


# ---------------------------------------------------------------------------
# Unmerge integration — uses real SQLiteRepository
# ---------------------------------------------------------------------------


@pytest.fixture
def merge_scenario(tmp_path: Path) -> tuple[str, str, str]:
    """Sets up a seeded DB with one completed merge.

    Creates two near-duplicate events (semantic merge path),
    saves both to DB, performs the merge, persists the survivor +
    archives the absorbed event.

    Returns:
        (db_path, survivor_id, absorbed_id)
    """
    db_path = str(tmp_path / "merge_test.sqlite")
    repo = SQLiteRepository(db_path=db_path)

    evt1 = _make_event(n=901, object_name="loyalty program in Wallet")
    evt2 = _make_event(n=902, object_name="wallet loyalty program v1.0")

    # Save both events initially
    repo.save_events([evt1, evt2])

    # Run merge
    survivor, archived = merge_events(evt1, evt2)

    # Persist the merged survivor (with ABSORBED_FROM relation)
    repo.save_events([survivor])

    # Archive the absorbed event (as deduplicate_events_use_case would do)
    repo.update_event_review(
        event_id=str(archived.event_id),
        review_status=ReviewLifecycleStatus.ARCHIVED,
        reviewed_by="system_dedup",
    )

    yield db_path, str(survivor.event_id), str(archived.event_id)

    Path(db_path).unlink(missing_ok=True)


class TestUnmergeIntegration:
    """Integration tests for ReviewEventsUseCase.unmerge_event()."""

    def test_unmerge_restores_absorbed_event(
        self, merge_scenario: tuple[str, str, str]
    ) -> None:
        db_path, survivor_id, absorbed_id = merge_scenario
        repo = SQLiteRepository(db_path=db_path)
        uc = ReviewEventsUseCase(repo)

        ok, restored = uc.unmerge_event(survivor_id, actor="reviewer@test")

        assert ok is True
        assert absorbed_id in restored

    def test_unmerge_sets_needs_review_on_absorbed(
        self, merge_scenario: tuple[str, str, str]
    ) -> None:
        db_path, survivor_id, absorbed_id = merge_scenario
        repo = SQLiteRepository(db_path=db_path)
        uc = ReviewEventsUseCase(repo)

        uc.unmerge_event(survivor_id, actor="reviewer@test")

        restored_event = repo.get_event_by_id(absorbed_id)
        assert restored_event is not None
        assert restored_event.review_status == ReviewLifecycleStatus.NEEDS_REVIEW

    def test_unmerge_deletes_absorbed_from_relation(
        self, merge_scenario: tuple[str, str, str]
    ) -> None:
        db_path, survivor_id, absorbed_id = merge_scenario
        repo = SQLiteRepository(db_path=db_path)
        uc = ReviewEventsUseCase(repo)

        # Before unmerge: relation exists
        relations_before = repo.get_event_relations(
            survivor_id, relation_type=RelationType.ABSORBED_FROM.value
        )
        assert len(relations_before) == 1

        uc.unmerge_event(survivor_id, actor="reviewer@test")

        # After unmerge: relation is gone
        relations_after = repo.get_event_relations(
            survivor_id, relation_type=RelationType.ABSORBED_FROM.value
        )
        assert len(relations_after) == 0

    def test_unmerge_writes_audit_on_absorbed(
        self, merge_scenario: tuple[str, str, str]
    ) -> None:
        db_path, survivor_id, absorbed_id = merge_scenario
        repo = SQLiteRepository(db_path=db_path)
        uc = ReviewEventsUseCase(repo)

        uc.unmerge_event(survivor_id, actor="reviewer@test")

        audit = repo.get_audit_log(absorbed_id)
        actions = [e.action for e in audit]
        assert "restored_from_merge" in actions

    def test_unmerge_writes_audit_on_survivor(
        self, merge_scenario: tuple[str, str, str]
    ) -> None:
        db_path, survivor_id, absorbed_id = merge_scenario
        repo = SQLiteRepository(db_path=db_path)
        uc = ReviewEventsUseCase(repo)

        uc.unmerge_event(survivor_id, actor="reviewer@test")

        audit = repo.get_audit_log(survivor_id)
        actions = [e.action for e in audit]
        assert "unmerged" in actions

    def test_unmerge_is_idempotent(self, merge_scenario: tuple[str, str, str]) -> None:
        """Second unmerge call succeeds but restores nothing."""
        db_path, survivor_id, absorbed_id = merge_scenario
        repo = SQLiteRepository(db_path=db_path)
        uc = ReviewEventsUseCase(repo)

        ok1, restored1 = uc.unmerge_event(survivor_id, actor="reviewer@test")
        ok2, restored2 = uc.unmerge_event(survivor_id, actor="reviewer@test")

        assert ok1 is True
        assert ok2 is True  # Idempotent
        assert len(restored1) == 1
        assert len(restored2) == 0  # Nothing left to restore

    def test_unmerge_returns_false_for_missing_event(self, tmp_path: Path) -> None:
        """Unmerge on non-existent event returns (False, [])."""
        db_path = str(tmp_path / "empty.sqlite")
        repo = SQLiteRepository(db_path=db_path)
        uc = ReviewEventsUseCase(repo)

        ok, restored = uc.unmerge_event(
            "00000000-0000-0000-0000-000000000000", actor="test"
        )
        assert ok is False
        assert restored == []


# ---------------------------------------------------------------------------
# Repository: get_event_relations / delete_event_relations
# ---------------------------------------------------------------------------


class TestRepoRelationMethods:
    """Unit tests for the two new repository methods."""

    @pytest.fixture
    def repo_with_relations(self, tmp_path: Path) -> SQLiteRepository:
        db_path = str(tmp_path / "relations.sqlite")
        repo = SQLiteRepository(db_path=db_path)
        evt1 = _make_event(n=1, object_name="Wallet loyalty")
        evt2 = _make_event(n=2, object_name="Wallet loyalty v2")
        repo.save_events([evt1, evt2])
        # Manually insert relation via merge
        survivor, absorbed = merge_events(evt1, evt2)
        repo.save_events([survivor])
        return repo

    def test_get_event_relations_returns_absorbed_from(
        self, repo_with_relations: SQLiteRepository
    ) -> None:
        survivor_id = "00000000-0000-0000-0000-000000000001"
        rels = repo_with_relations.get_event_relations(
            survivor_id, relation_type=RelationType.ABSORBED_FROM.value
        )
        assert len(rels) == 1
        rel_type, target_id = rels[0]
        assert rel_type == RelationType.ABSORBED_FROM.value
        assert target_id == "00000000-0000-0000-0000-000000000002"

    def test_get_event_relations_no_filter_returns_all(
        self, repo_with_relations: SQLiteRepository
    ) -> None:
        survivor_id = "00000000-0000-0000-0000-000000000001"
        rels = repo_with_relations.get_event_relations(survivor_id)
        assert len(rels) >= 1

    def test_delete_event_relations_removes_correct_rows(
        self, repo_with_relations: SQLiteRepository
    ) -> None:
        survivor_id = "00000000-0000-0000-0000-000000000001"
        deleted = repo_with_relations.delete_event_relations(
            survivor_id, relation_type=RelationType.ABSORBED_FROM.value
        )
        assert deleted == 1
        remaining = repo_with_relations.get_event_relations(
            survivor_id, relation_type=RelationType.ABSORBED_FROM.value
        )
        assert len(remaining) == 0

    def test_delete_event_relations_other_types_unaffected(
        self, repo_with_relations: SQLiteRepository
    ) -> None:
        """Deleting ABSORBED_FROM leaves other relation types intact."""
        survivor_id = "00000000-0000-0000-0000-000000000001"
        # Only ABSORBED_FROM exists, so deleting a different type should delete 0
        deleted = repo_with_relations.delete_event_relations(
            survivor_id, relation_type="updates"
        )
        assert deleted == 0
        # Original ABSORBED_FROM still present
        remaining = repo_with_relations.get_event_relations(
            survivor_id, relation_type=RelationType.ABSORBED_FROM.value
        )
        assert len(remaining) == 1
