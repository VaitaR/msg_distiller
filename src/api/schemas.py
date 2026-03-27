"""Pydantic schemas for API request/response serialization.

Separate from domain models to allow independent evolution of API contract.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from src.domain.models import (
    EventCategory,
    EventOrigin,
    EventStatus,
    ReviewLifecycleStatus,
)

# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class EventResponse(BaseModel):
    """Single event in API responses."""

    event_id: UUID
    message_id: str
    source_channels: list[str]
    title: str
    action: str
    object_name_raw: str
    qualifiers: list[str]
    category: EventCategory
    status: EventStatus
    confidence: float
    importance: int
    summary: str
    why_it_matters: str | None = None
    links: list[str] = []
    impact_area: list[str] = []
    source_id: str
    review_status: ReviewLifecycleStatus
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    version: int
    origin: EventOrigin
    extracted_at: datetime
    planned_start: datetime | None = None
    planned_end: datetime | None = None
    actual_start: datetime | None = None
    actual_end: datetime | None = None
    event_date: datetime | None = None


class EventListResponse(BaseModel):
    """Paginated list of events."""

    items: list[EventResponse]
    total: int
    limit: int
    offset: int


class TimelineEntry(BaseModel):
    """Event formatted for timeline (Gantt) rendering."""

    event_id: UUID
    title: str
    category: str
    status: str
    review_status: str
    start: datetime
    end: datetime | None = None
    importance: int
    confidence: float
    source_id: str


class TimelineResponse(BaseModel):
    """Timeline response."""

    entries: list[TimelineEntry]
    total: int


class AuditEntryResponse(BaseModel):
    """Single audit log entry."""

    audit_id: UUID
    event_id: UUID
    version: int
    action: str
    origin: str
    changes: dict[str, Any]
    actor: str
    timestamp: datetime
    note: str | None = None


class ReviewStatsResponse(BaseModel):
    """Review status counts."""

    needs_review: int = 0
    approved: int = 0
    published: int = 0
    rejected: int = 0
    archived: int = 0


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str = "0.1.0"
    timestamp: datetime


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class ReviewAction(BaseModel):
    """Request body for approve/reject/publish."""

    action: str = Field(
        ...,
        description="One of: approve, reject, publish, archive",
        pattern="^(approve|reject|publish|archive)$",
    )
    actor: str = Field(..., description="User performing the action")
    note: str | None = Field(default=None, description="Optional comment")


class EventPatch(BaseModel):
    """Request body for editing event fields."""

    actor: str = Field(..., description="User performing the edit")
    updates: dict[str, Any] = Field(..., description="Field-value pairs to patch")
