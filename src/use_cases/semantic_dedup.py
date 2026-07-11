"""Semantic deduplication use case (second pass over fuzzy dedup).

Runs AFTER the per-source fuzzy dedup and works cross-source: finds pairs of
events with high embedding similarity and either auto-merges them (high
confidence + compatible fields) or links them with a DUPLICATE_SUSPECT
relation for human review.

Two-threshold policy (configurable via main.yaml embeddings section):
- cosine >= auto_merge_threshold (default 0.92) AND same action AND time
  delta <= dedup date window AND non-contradictory statuses -> auto-merge
  via deduplicator.merge_events (ABSORBED_FROM relation + archive).
- cosine >= suspect_threshold (default 0.80) otherwise -> DUPLICATE_SUSPECT
  relation, surfaced in review.
"""

from datetime import datetime, timedelta

import pytz

from src.adapters.query_builders import EventQueryCriteria
from src.config.logging_config import get_logger
from src.config.settings import Settings
from src.domain.models import (
    Event,
    EventAuditEntry,
    EventOrigin,
    EventStatus,
    RelationType,
    ReviewLifecycleStatus,
)
from src.domain.protocols import RepositoryProtocol
from src.services import deduplicator

logger = get_logger(__name__)

# Status pairs that describe genuinely different lifecycle outcomes:
# merging e.g. "completed" with "rolled_back" would erase signal.
_CONTRADICTORY_STATUS_PAIRS: frozenset[frozenset[EventStatus]] = frozenset(
    {
        frozenset({EventStatus.COMPLETED, EventStatus.ROLLED_BACK}),
        frozenset({EventStatus.COMPLETED, EventStatus.CANCELED}),
        frozenset({EventStatus.COMPLETED, EventStatus.POSTPONED}),
        frozenset({EventStatus.CANCELED, EventStatus.STARTED}),
        frozenset({EventStatus.CANCELED, EventStatus.CONFIRMED}),
        frozenset({EventStatus.ROLLED_BACK, EventStatus.PLANNED}),
    }
)


def _statuses_compatible(a: EventStatus, b: EventStatus) -> bool:
    """Whether two statuses can safely coexist in one merged event."""
    return frozenset({a, b}) not in _CONTRADICTORY_STATUS_PAIRS


def _event_time(event: Event) -> datetime:
    """Best-effort event time for the merge window check."""
    return (
        event.actual_start
        or event.planned_start
        or event.actual_end
        or event.planned_end
        or event.extracted_at
    )


def _is_mergeable(
    event: Event, neighbor: Event, *, date_window_hours: int
) -> bool:
    """Compatibility gate for auto-merge (beyond the similarity threshold)."""
    if event.action != neighbor.action:
        return False
    if not _statuses_compatible(event.status, neighbor.status):
        return False
    delta = abs(_event_time(event) - _event_time(neighbor))
    return delta <= timedelta(hours=date_window_hours)


def semantic_dedup_use_case(
    *,
    repository: RepositoryProtocol,
    settings: Settings,
    correlation_id: str | None = None,
) -> dict[str, int]:
    """Cross-source semantic dedup second pass.

    For each recent non-archived event with an embedding, finds its nearest
    neighbors above the suspect threshold (different dedup_key) and applies
    the two-threshold policy.

    Returns:
        Stats dict: candidates, merged, suspected
    """
    stats = {"candidates": 0, "merged": 0, "suspected": 0}

    if not settings.embeddings_enabled:
        return stats

    model = settings.embedding_model
    auto_merge_threshold = settings.semantic_auto_merge_threshold
    suspect_threshold = settings.semantic_suspect_threshold
    lookback_days = settings.dedup_message_lookback_days
    extracted_after = datetime.now(tz=pytz.UTC) - timedelta(days=lookback_days)

    recent_events = repository.query_events(
        EventQueryCriteria(
            extracted_after=extracted_after,
            order_by="extracted_at",
            order_desc=False,
        )
    )
    active_events = [
        e
        for e in recent_events
        if e.review_status != ReviewLifecycleStatus.ARCHIVED
    ]
    if not active_events:
        return stats

    embeddings = repository.get_event_embeddings(
        [str(e.event_id) for e in active_events], model
    )

    absorbed_ids: set[str] = set()

    for event in active_events:
        event_id = str(event.event_id)
        if event_id in absorbed_ids:
            continue
        vector = embeddings.get(event_id)
        if vector is None:
            continue
        stats["candidates"] += 1

        neighbors = repository.find_similar_events(
            vector,
            model=model,
            limit=10,
            min_similarity=suspect_threshold,
            extracted_after=extracted_after,
            exclude_event_id=event_id,
        )

        for neighbor, similarity in neighbors:
            neighbor_id = str(neighbor.event_id)
            if neighbor_id in absorbed_ids:
                continue
            if neighbor.dedup_key == event.dedup_key:
                continue  # first-pass dedup owns identical keys
            if neighbor.message_id == event.message_id:
                continue  # events split from one message are distinct on purpose
            if neighbor.review_status == ReviewLifecycleStatus.ARCHIVED:
                continue

            if similarity >= auto_merge_threshold and _is_mergeable(
                event,
                neighbor,
                date_window_hours=settings.dedup_date_window_hours,
            ):
                survivor, archived = deduplicator.merge_events(event, neighbor)
                if survivor.dedup_key != event.dedup_key:
                    # Keep the survivor's stored dedup_key: persistence upserts
                    # on dedup_key, and a refreshed key for an existing
                    # event_id would violate the events primary key.
                    survivor = survivor.model_copy(
                        update={"dedup_key": event.dedup_key}
                    )
                repository.save_events([survivor, archived])
                repository.update_event_review(
                    event_id=neighbor_id,
                    review_status=ReviewLifecycleStatus.ARCHIVED,
                    reviewed_by="system_semantic_dedup",
                )
                repository.save_audit_entry(
                    EventAuditEntry(
                        event_id=neighbor.event_id,
                        version=archived.version,
                        action="archived_by_merge",
                        origin=EventOrigin.SYSTEM_MERGE,
                        changes={
                            "reason": "absorbed_by_semantic_dedup",
                            "similarity": round(similarity, 4),
                        },
                        actor="system_semantic_dedup",
                    )
                )
                absorbed_ids.add(neighbor_id)
                event = survivor  # keep merging further neighbors into survivor
                stats["merged"] += 1
                logger.info(
                    "semantic_dedup_merged",
                    correlation_id=correlation_id,
                    survivor_event_id=event_id,
                    absorbed_event_id=neighbor_id,
                    similarity=round(similarity, 4),
                )
            else:
                # Record the pair once, in a deterministic direction, so the
                # reverse iteration (and future runs) don't duplicate it.
                if event_id > neighbor_id:
                    continue
                repository.save_event_relation(
                    event_id,
                    RelationType.DUPLICATE_SUSPECT.value,
                    neighbor_id,
                )
                stats["suspected"] += 1
                logger.info(
                    "semantic_dedup_suspect",
                    correlation_id=correlation_id,
                    source_event_id=event_id,
                    target_event_id=neighbor_id,
                    similarity=round(similarity, 4),
                )

    logger.info(
        "semantic_dedup_completed",
        correlation_id=correlation_id,
        candidates=stats["candidates"],
        merged=stats["merged"],
        suspected=stats["suspected"],
    )
    return stats
