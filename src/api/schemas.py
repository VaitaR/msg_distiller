"""Pydantic schemas for API request/response serialization.

Separate from domain models to allow independent evolution of API contract.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.models import (
    ChangeType,
    Environment,
    EventCategory,
    EventOrigin,
    EventStatus,
    ReviewLifecycleStatus,
    Severity,
    TimeSource,
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
    object_id: str | None = None
    object_name_raw: str
    qualifiers: list[str]
    stroke: str | None = None
    anchor: str | None = None
    category: EventCategory
    status: EventStatus
    change_type: ChangeType
    environment: Environment
    severity: Severity | None = None
    confidence: float
    importance: int
    message_published_at: datetime | None = None
    summary: str
    why_it_matters: str | None = None
    links: list[str] = []
    anchors: list[str] = []
    impact_area: list[str] = []
    impact_type: list[str] = []
    time_source: TimeSource
    time_confidence: float
    cluster_key: str
    dedup_key: str
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


class StoryResponse(BaseModel):
    """Event story (lifecycle aggregate by cluster_key)."""

    cluster_key: str
    action: str
    object_id: str | None = None
    object_name_raw: str
    current_status: str
    event_count: int
    first_seen: datetime
    last_seen: datetime
    sources: list[str]
    max_importance: int
    events: list[EventResponse]
    followups: list[EventResponse] = Field(default_factory=list)


class StoryListResponse(BaseModel):
    """List of event stories."""

    items: list[StoryResponse]
    total: int


class SemanticSearchItem(BaseModel):
    """Event with its semantic similarity to the query."""

    event: EventResponse
    similarity: float


class SemanticSearchResponse(BaseModel):
    """Semantic search results."""

    items: list[SemanticSearchItem]
    total: int
    query: str


class ObjectSuggestionResponse(BaseModel):
    """Unmatched object name queued for registry review."""

    id: int
    name_normalized: str
    name_raw_sample: str
    occurrences: int
    sample_event_ids: list[str]
    status: str
    approved_object_id: str | None = None
    created_at: datetime | str
    updated_at: datetime | str


class ObjectSuggestionListResponse(BaseModel):
    """List of object registry suggestions."""

    items: list[ObjectSuggestionResponse]
    total: int


class ApproveSuggestionRequest(BaseModel):
    """Approve a suggestion: register a synonym under object_id."""

    object_id: str = Field(min_length=1, max_length=200)
    synonym: str | None = Field(default=None, min_length=1, max_length=500)


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


class EventRelationResponse(BaseModel):
    """Single relation originating from an event."""

    relation_type: str
    target_event_id: str


class EventVersionResponse(BaseModel):
    """Single historical snapshot for an event."""

    version_id: UUID
    event_id: UUID
    version: int
    origin: str
    snapshot: dict[str, Any]
    created_at: datetime


class MessageMetadataResponse(BaseModel):
    """Small source-message metadata subset for investigation views."""

    permalink: str | None = None
    post_url: str | None = None
    forwarded_from: str | None = None
    reply_count: int = 0
    reactions_count: int = 0
    has_file: bool = False
    file_mime: str | None = None


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
        description="One of: approve, reject, publish",
        pattern="^(approve|reject|publish)$",
    )
    actor: str = Field(..., description="User performing the action")
    note: str | None = Field(default=None, description="Optional comment")


class EventPatch(BaseModel):
    """Request body for editing event fields."""

    actor: str = Field(..., description="User performing the edit")
    updates: "EventPatchUpdates" = Field(
        ...,
        description="Allowed editable fields for a human edit",
    )


class EventPatchUpdates(BaseModel):
    """Bounded editable event fields."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, description="Human-corrected event title")
    summary: str | None = Field(
        default=None,
        description="Human-corrected event summary",
    )
    why_it_matters: str | None = Field(
        default=None,
        description="Human-corrected impact explanation",
    )

    @model_validator(mode="after")
    def validate_non_empty(self) -> "EventPatchUpdates":
        if not self.model_fields_set:
            raise ValueError("At least one editable field must be provided")
        return self


class UnmergeRequest(BaseModel):
    """Request body for unmerging absorbed events from a survivor."""

    actor: str = Field(..., description="User performing the unmerge")
