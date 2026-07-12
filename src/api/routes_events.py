"""Event-related API routes: CRUD, timeline, review actions, audit."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from src.adapters.llm_client import LLMClient
from src.api.dependencies import (
    get_app_settings,
    get_llm_client,
    get_repo,
    get_review_use_case,
    require_write_access,
)
from src.api.schemas import (
    AuditEntryResponse,
    EventListResponse,
    EventPatch,
    EventRelationResponse,
    EventResponse,
    EventVersionResponse,
    MessageMetadataResponse,
    ReviewAction,
    ReviewStatsResponse,
    SemanticSearchItem,
    SemanticSearchResponse,
    TimelineEntry,
    TimelineResponse,
    UnmergeRequest,
)
from src.config.settings import Settings
from src.domain.exceptions import LLMAPIError
from src.domain.models import Event, ReviewLifecycleStatus
from src.domain.protocols import RepositoryProtocol
from src.use_cases.review_events import ReviewEventsUseCase

router = APIRouter(prefix="/api/v1/events", tags=["events"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _event_to_response(e: Event) -> EventResponse:
    """Map domain Event to API EventResponse."""
    return EventResponse(
        event_id=e.event_id,
        message_id=e.message_id,
        source_channels=e.source_channels,
        title=e.title,
        action=e.action.value,
        object_id=e.object_id,
        object_name_raw=e.object_name_raw,
        qualifiers=e.qualifiers,
        stroke=e.stroke,
        anchor=e.anchor,
        category=e.category,
        status=e.status,
        change_type=e.change_type,
        environment=e.environment,
        severity=e.severity,
        confidence=e.confidence,
        importance=e.importance,
        message_published_at=e.message_published_at,
        summary=e.summary,
        why_it_matters=e.why_it_matters,
        links=e.links,
        anchors=e.anchors,
        impact_area=e.impact_area,
        impact_type=e.impact_type,
        time_source=e.time_source,
        time_confidence=e.time_confidence,
        cluster_key=e.cluster_key,
        dedup_key=e.dedup_key,
        source_id=e.source_id.value,
        review_status=e.review_status,
        reviewed_by=e.reviewed_by,
        reviewed_at=e.reviewed_at,
        version=e.version,
        origin=e.origin,
        extracted_at=e.extracted_at,
        planned_start=e.planned_start,
        planned_end=e.planned_end,
        actual_start=e.actual_start,
        actual_end=e.actual_end,
        event_date=e.event_date,
    )


# ---------------------------------------------------------------------------
# List / Get
# ---------------------------------------------------------------------------


@router.get("", response_model=EventListResponse)
def list_events(
    review_status: ReviewLifecycleStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    uc: ReviewEventsUseCase = Depends(get_review_use_case),
) -> EventListResponse:
    """List events with optional review_status filter."""
    events = uc.get_review_queue(status=review_status, limit=limit, offset=offset)
    counts = uc.get_stats()
    total = (
        sum(counts.values())
        if review_status is None
        else counts.get(review_status.value, 0)
    )

    return EventListResponse(
        items=[_event_to_response(e) for e in events],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/stats", response_model=ReviewStatsResponse)
def review_stats(
    uc: ReviewEventsUseCase = Depends(get_review_use_case),
) -> ReviewStatsResponse:
    """Get counts of events grouped by review status."""
    counts = uc.get_stats()
    return ReviewStatsResponse(**counts)


@router.get("/timeline", response_model=TimelineResponse)
def timeline(
    days: int = Query(default=30, ge=1, le=365),
    review_status: ReviewLifecycleStatus | None = Query(default=None),
    repo: RepositoryProtocol = Depends(get_repo),
) -> TimelineResponse:
    """Get events formatted for timeline / Gantt view."""
    end_dt = datetime.now(tz=UTC)
    start_dt = end_dt - timedelta(days=days)
    events = repo.get_events_in_window(start_dt, end_dt)

    # Optional filter by review status
    if review_status is not None:
        events = [e for e in events if e.review_status == review_status]

    entries = []
    for e in events:
        start = e.actual_start or e.planned_start or e.extracted_at
        end = e.actual_end or e.planned_end or None
        entries.append(
            TimelineEntry(
                event_id=e.event_id,
                title=e.title,
                category=e.category.value,
                status=e.status.value,
                review_status=e.review_status.value,
                start=start,
                end=end,
                importance=e.importance,
                confidence=e.confidence,
                source_id=e.source_id.value,
            )
        )

    return TimelineResponse(entries=entries, total=len(entries))


@router.get("/search", response_model=SemanticSearchResponse)
def search_events(
    q: str = Query(min_length=2, max_length=500),
    limit: int = Query(default=10, ge=1, le=50),
    min_similarity: float = Query(default=0.3, ge=0.0, le=1.0),
    repo: RepositoryProtocol = Depends(get_repo),
    llm_client: LLMClient = Depends(get_llm_client),
    settings: Settings = Depends(get_app_settings),
) -> SemanticSearchResponse:
    """Semantic search over events via embedding similarity."""
    if not settings.embeddings_enabled:
        raise HTTPException(status_code=503, detail="Embeddings are disabled")

    # Query embedding is a paid call: respect the daily budget and record it
    # in the llm_calls ledger like every other spend.
    if repo.get_daily_llm_cost(datetime.now(tz=UTC)) >= settings.llm_daily_budget_usd:
        raise HTTPException(
            status_code=429, detail="Daily LLM budget exhausted; try again tomorrow"
        )

    try:
        query_vector = llm_client.embed_texts([q], model=settings.embedding_model)[0]
    except LLMAPIError as exc:
        raise HTTPException(
            status_code=502, detail=f"Failed to embed query: {exc}"
        ) from exc
    repo.save_llm_call(llm_client.get_call_metadata())

    results = repo.find_similar_events(
        query_vector,
        model=settings.embedding_model,
        limit=limit,
        min_similarity=min_similarity,
    )
    items = [
        SemanticSearchItem(
            event=_event_to_response(event), similarity=round(similarity, 4)
        )
        for event, similarity in results
        if event.review_status != ReviewLifecycleStatus.ARCHIVED
    ]
    return SemanticSearchResponse(items=items, total=len(items), query=q)


@router.get("/{event_id}", response_model=EventResponse)
def get_event(
    event_id: str,
    uc: ReviewEventsUseCase = Depends(get_review_use_case),
) -> EventResponse:
    """Get single event by ID."""
    event = uc.get_event_detail(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return _event_to_response(event)


# ---------------------------------------------------------------------------
# Review actions
# ---------------------------------------------------------------------------


@router.post("/{event_id}/review")
def review_event(
    event_id: str,
    body: ReviewAction,
    uc: ReviewEventsUseCase = Depends(get_review_use_case),
    _: None = Depends(require_write_access),
) -> dict[str, Any]:
    """Approve, reject, or publish an event."""
    action_map: dict[str, Callable[[str, str], bool]] = {
        "approve": uc.approve_event,
        "reject": uc.reject_event,
        "publish": uc.publish_event,
    }
    handler = action_map.get(body.action)
    if handler is None:
        raise HTTPException(status_code=400, detail=f"Unknown action: {body.action}")

    if body.action == "reject":
        ok = uc.reject_event(event_id, body.actor, note=body.note)
    else:
        ok = handler(event_id, body.actor)

    if not ok:
        raise HTTPException(status_code=404, detail="Event not found")
    return {"status": "ok", "action": body.action, "event_id": event_id}


@router.post("/{event_id}/unmerge")
def unmerge_event(
    event_id: str,
    body: UnmergeRequest,
    uc: ReviewEventsUseCase = Depends(get_review_use_case),
    _: None = Depends(require_write_access),
) -> dict[str, Any]:
    """Unmerge absorbed events from a survivor event.

    Restores all events previously absorbed into this event during
    deduplication. Each restored event is set back to needs_review.
    The ABSORBED_FROM relations are deleted from the survivor.
    """
    ok, restored = uc.unmerge_event(event_id, body.actor)
    if not ok:
        raise HTTPException(status_code=404, detail="Event not found")
    return {
        "status": "ok",
        "action": "unmerge",
        "event_id": event_id,
        "restored_event_ids": restored,
    }


@router.patch("/{event_id}")
def patch_event(
    event_id: str,
    body: EventPatch,
    uc: ReviewEventsUseCase = Depends(get_review_use_case),
    _: None = Depends(require_write_access),
) -> dict[str, Any]:
    """Edit event fields (human edit). Creates version snapshot + audit entry."""
    try:
        ok = uc.edit_event(
            event_id,
            body.actor,
            body.updates.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not ok:
        raise HTTPException(status_code=404, detail="Event not found")
    return {"status": "ok", "event_id": event_id}


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------


@router.get("/{event_id}/audit", response_model=list[AuditEntryResponse])
def get_audit(
    event_id: str,
    uc: ReviewEventsUseCase = Depends(get_review_use_case),
) -> list[AuditEntryResponse]:
    """Get full audit trail for an event."""
    entries = uc.get_audit_trail(event_id)
    return [
        AuditEntryResponse(
            audit_id=a.audit_id,
            event_id=a.event_id,
            version=a.version,
            action=a.action,
            origin=a.origin.value,
            changes=a.changes,
            actor=a.actor,
            timestamp=a.timestamp,
            note=a.note,
        )
        for a in entries
    ]


@router.get("/{event_id}/relations", response_model=list[EventRelationResponse])
def get_relations(
    event_id: str,
    repo: RepositoryProtocol = Depends(get_repo),
) -> list[EventRelationResponse]:
    """Get relations originating from an event."""
    event = repo.get_event_by_id(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    relations = repo.get_event_relations(event_id)
    return [
        EventRelationResponse(
            relation_type=relation_type,
            target_event_id=target_event_id,
        )
        for relation_type, target_event_id in relations
    ]


@router.get("/{event_id}/versions", response_model=list[EventVersionResponse])
def get_versions(
    event_id: str,
    uc: ReviewEventsUseCase = Depends(get_review_use_case),
) -> list[EventVersionResponse]:
    """Get version snapshots for an event."""
    event = uc.get_event_detail(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    versions = uc.get_versions(event_id)
    return [
        EventVersionResponse(
            version_id=version.version_id,
            event_id=version.event_id,
            version=version.version,
            origin=version.origin.value,
            snapshot=version.snapshot,
            created_at=version.created_at,
        )
        for version in versions
    ]


@router.get("/{event_id}/message-metadata", response_model=MessageMetadataResponse)
def get_message_metadata(
    event_id: str,
    repo: RepositoryProtocol = Depends(get_repo),
) -> MessageMetadataResponse:
    """Get compact source-message metadata for an event."""
    event = repo.get_event_by_id(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    metadata = repo.get_message_metadata(event.message_id, event.source_id)
    return MessageMetadataResponse(**metadata)
