"""Event stories use case.

An event story is the computed lifecycle of one initiative: all events
sharing a cluster_key, in chronological order, plus follow-up events linked
via UPDATES relations (e.g. extracted from Slack thread replies).
"""

from datetime import datetime

from src.config.logging_config import get_logger
from src.domain.models import (
    Event,
    EventStory,
    RelationType,
    ReviewLifecycleStatus,
)
from src.domain.protocols import RepositoryProtocol

logger = get_logger(__name__)


def _event_time(event: Event) -> datetime:
    return event.message_published_at or event.extracted_at


def _build_story(cluster_key: str, events: list[Event]) -> EventStory:
    """Assemble a story from the (non-empty) events of one cluster."""
    ordered = sorted(events, key=_event_time)
    latest = ordered[-1]
    sources = sorted({e.source_id.value for e in ordered})
    return EventStory(
        cluster_key=cluster_key,
        action=latest.action.value,
        object_id=latest.object_id,
        object_name_raw=latest.object_name_raw,
        current_status=latest.status.value,
        event_count=len(ordered),
        first_seen=_event_time(ordered[0]),
        last_seen=_event_time(latest),
        sources=sources,
        max_importance=max(e.importance for e in ordered),
        events=ordered,
    )


def _active_cluster_events(
    repository: RepositoryProtocol, cluster_key: str
) -> list[Event]:
    return [
        e
        for e in repository.get_events_by_cluster_key(cluster_key)
        if e.review_status != ReviewLifecycleStatus.ARCHIVED
    ]


def get_stories_use_case(
    *,
    repository: RepositoryProtocol,
    since: datetime | None = None,
    object_id: str | None = None,
    limit: int = 50,
) -> list[EventStory]:
    """List event stories ordered by most recent activity.

    Args:
        repository: Storage backend
        since: Only stories with activity at/after this time
        object_id: Optional canonical object filter
        limit: Max stories

    Returns:
        Stories with their full event chronology (followups not loaded here)
    """
    clusters = repository.list_event_clusters(
        since=since, object_id=object_id, limit=limit
    )

    stories: list[EventStory] = []
    for cluster in clusters:
        events = _active_cluster_events(repository, cluster["cluster_key"])
        if not events:
            continue
        stories.append(_build_story(cluster["cluster_key"], events))
    return stories


def get_story_detail_use_case(
    *,
    repository: RepositoryProtocol,
    cluster_key: str,
) -> EventStory | None:
    """Get one story with follow-up events (UPDATES relations) included.

    Args:
        repository: Storage backend
        cluster_key: Story identifier

    Returns:
        The story, or None if the cluster has no active events
    """
    events = _active_cluster_events(repository, cluster_key)
    if not events:
        return None

    story = _build_story(cluster_key, events)

    cluster_event_ids = {str(e.event_id) for e in events}
    followups = [
        e
        for e in repository.get_events_relating_to(
            sorted(cluster_event_ids), RelationType.UPDATES.value
        )
        if e.review_status != ReviewLifecycleStatus.ARCHIVED
        and str(e.event_id) not in cluster_event_ids
    ]
    story.followups = sorted(followups, key=_event_time)
    return story
