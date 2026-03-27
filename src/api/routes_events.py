"""Event-related API routes: CRUD, timeline, review actions, audit."""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.dependencies import get_repo, get_review_use_case
from src.api.schemas import (
    AuditEntryResponse,
    EventListResponse,
    EventPatch,
    EventResponse,
    ReviewAction,
    ReviewStatsResponse,
    TimelineEntry,
    TimelineResponse,
)
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
        object_name_raw=e.object_name_raw,
        qualifiers=e.qualifiers,
        category=e.category,
        status=e.status,
        confidence=e.confidence,
        importance=e.importance,
        summary=e.summary,
        why_it_matters=e.why_it_matters,
        links=e.links,
        impact_area=e.impact_area,
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
    return EventListResponse(
        items=[_event_to_response(e) for e in events],
        total=len(events),  # TODO: separate count query for proper pagination
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
) -> dict[str, Any]:
    """Approve, reject, publish, or archive an event."""
    action_map = {
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


@router.patch("/{event_id}")
def patch_event(
    event_id: str,
    body: EventPatch,
    uc: ReviewEventsUseCase = Depends(get_review_use_case),
) -> dict[str, Any]:
    """Edit event fields (human edit). Creates version snapshot + audit entry."""
    ok = uc.edit_event(event_id, body.actor, body.updates)
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
