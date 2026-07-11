"""Event story API routes: lifecycle aggregates grouped by cluster_key."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.dependencies import get_repo
from src.api.routes_events import _event_to_response
from src.api.schemas import StoryListResponse, StoryResponse
from src.domain.models import EventStory
from src.domain.protocols import RepositoryProtocol
from src.use_cases.stories import get_stories_use_case, get_story_detail_use_case

router = APIRouter(prefix="/api/v1/stories", tags=["stories"])


def _story_to_response(story: EventStory) -> StoryResponse:
    return StoryResponse(
        cluster_key=story.cluster_key,
        action=story.action,
        object_id=story.object_id,
        object_name_raw=story.object_name_raw,
        current_status=story.current_status,
        event_count=story.event_count,
        first_seen=story.first_seen,
        last_seen=story.last_seen,
        sources=story.sources,
        max_importance=story.max_importance,
        events=[_event_to_response(e) for e in story.events],
        followups=[_event_to_response(e) for e in story.followups],
    )


@router.get("", response_model=StoryListResponse)
def list_stories(
    since_days: int = Query(default=30, ge=1, le=365),
    object_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    repo: RepositoryProtocol = Depends(get_repo),
) -> StoryListResponse:
    """List event stories ordered by most recent activity."""
    since = datetime.now(tz=UTC) - timedelta(days=since_days)
    stories = get_stories_use_case(
        repository=repo, since=since, object_id=object_id, limit=limit
    )
    return StoryListResponse(
        items=[_story_to_response(s) for s in stories],
        total=len(stories),
    )


@router.get("/{cluster_key}", response_model=StoryResponse)
def get_story(
    cluster_key: str,
    repo: RepositoryProtocol = Depends(get_repo),
) -> StoryResponse:
    """Get one story with its chronology and thread follow-ups."""
    story = get_story_detail_use_case(repository=repo, cluster_key=cluster_key)
    if story is None:
        raise HTTPException(status_code=404, detail="Story not found")
    return _story_to_response(story)
