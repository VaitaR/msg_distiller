"""Tests for WS2: Slack thread ingestion and event stories."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

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
from src.domain.protocols import RepositoryProtocol
from src.use_cases.ingest_messages import (
    _fetch_slack_messages,
    process_slack_message,
)
from src.use_cases.stories import (
    get_stories_use_case,
    get_story_detail_use_case,
)


class FakeThreadedSlackClient:
    """Fake client serving a channel history plus per-thread replies."""

    def __init__(
        self,
        messages: list[dict[str, Any]],
        replies_by_thread: dict[str, list[dict[str, Any]]],
    ) -> None:
        self.messages = sorted(messages, key=lambda msg: float(msg["ts"]))
        self.replies_by_thread = replies_by_thread
        self.replies_requested: list[str] = []

    def _fetch_page_with_retries(
        self, channel_id: str, params: dict[str, Any], **_: Any
    ) -> dict[str, Any]:
        return {
            "ok": True,
            "messages": self.messages,
            "response_metadata": {"next_cursor": ""},
        }

    def fetch_thread_replies(
        self, channel_id: str, thread_ts: str, **_: Any
    ) -> list[dict[str, Any]]:
        self.replies_requested.append(thread_ts)
        return self.replies_by_thread.get(thread_ts, [])


def test_fetch_slack_messages_includes_thread_replies() -> None:
    root_ts = "1000.000100"
    root = {"ts": root_ts, "user": "U1", "text": "root", "reply_count": 2}
    plain = {"ts": "1001.000100", "user": "U2", "text": "no thread"}
    replies = [
        {"ts": "1002.000100", "user": "U3", "text": "r1", "thread_ts": root_ts},
        {"ts": "1003.000100", "user": "U4", "text": "r2", "thread_ts": root_ts},
    ]
    client = FakeThreadedSlackClient([root, plain], {root_ts: replies})

    messages, next_cursor, has_more = _fetch_slack_messages(
        client,  # type: ignore[arg-type]
        "C123",
        oldest_ts=None,
        cursor=None,
        limit=None,
        page_size=100,
    )

    assert client.replies_requested == [root_ts]
    assert {m["ts"] for m in messages} == {
        root_ts,
        "1001.000100",
        "1002.000100",
        "1003.000100",
    }
    assert not has_more


def test_fetch_slack_messages_skips_reply_fetch_for_leaf_messages() -> None:
    client = FakeThreadedSlackClient(
        [{"ts": "1000.000100", "user": "U1", "text": "leaf"}], {}
    )

    messages, _, _ = _fetch_slack_messages(
        client,  # type: ignore[arg-type]
        "C123",
        oldest_ts=None,
        cursor=None,
        limit=None,
        page_size=100,
    )

    assert client.replies_requested == []
    assert len(messages) == 1


def test_process_slack_message_normalizes_thread_ts() -> None:
    reply = process_slack_message(
        {"ts": "1002.5", "thread_ts": "1000.5", "text": "reply"}, "C123"
    )
    assert reply.thread_ts == "1000.5"

    root = process_slack_message(
        {"ts": "1000.5", "thread_ts": "1000.5", "text": "root", "reply_count": 3},
        "C123",
    )
    assert root.thread_ts is None

    plain = process_slack_message({"ts": "1001.5", "text": "plain"}, "C123")
    assert plain.thread_ts is None


# ---------------------------------------------------------------------------
# Event stories
# ---------------------------------------------------------------------------


def _story_event(
    n: int,
    *,
    cluster_key: str = "cluster-story",
    status: EventStatus = EventStatus.PLANNED,
    days_ago: int = 0,
    thread_ts: str | None = None,
) -> Event:
    when = datetime.now(tz=UTC) - timedelta(days=days_ago)
    return Event(
        event_id=f"00000000-0000-0000-0001-{n:012d}",
        message_id=f"msg-story-{n:03d}",
        source_channels=["#releases"],
        message_published_at=when,
        extracted_at=when,
        thread_ts=thread_ts,
        action=ActionType.LAUNCH,
        object_name_raw="Story Feature",
        category=EventCategory.PRODUCT,
        status=status,
        change_type=ChangeType.LAUNCH,
        environment=Environment.PROD,
        planned_start=when,
        time_source=TimeSource.EXPLICIT,
        time_confidence=0.9,
        summary=f"Story Feature step {n} in production rollout.",
        confidence=0.9,
        importance=50 + n,
        cluster_key=cluster_key,
        dedup_key=f"dedup-story-{n}",
        source_id=MessageSource.SLACK,
        review_status=ReviewLifecycleStatus.NEEDS_REVIEW,
        origin=EventOrigin.AI_EXTRACTION,
        version=1,
    )


def test_story_chronology_and_current_status(repo: RepositoryProtocol) -> None:
    events = [
        _story_event(1, status=EventStatus.PLANNED, days_ago=3),
        _story_event(2, status=EventStatus.STARTED, days_ago=2),
        _story_event(3, status=EventStatus.COMPLETED, days_ago=1),
    ]
    repo.save_events(events)

    stories = get_stories_use_case(repository=repo)

    assert len(stories) == 1
    story = stories[0]
    assert story.cluster_key == "cluster-story"
    assert story.event_count == 3
    assert story.current_status == EventStatus.COMPLETED.value
    assert [e.status for e in story.events] == [
        EventStatus.PLANNED,
        EventStatus.STARTED,
        EventStatus.COMPLETED,
    ]
    assert story.max_importance == 53


def test_story_detail_includes_thread_followups(repo: RepositoryProtocol) -> None:
    root_event = _story_event(1, days_ago=2)
    followup = _story_event(
        10,
        cluster_key="cluster-other",
        status=EventStatus.UPDATED,
        days_ago=1,
        thread_ts="1000.000100",
    )
    repo.save_events([root_event, followup])
    repo.save_event_relation(
        str(followup.event_id),
        RelationType.UPDATES.value,
        str(root_event.event_id),
    )

    story = get_story_detail_use_case(repository=repo, cluster_key="cluster-story")

    assert story is not None
    assert [str(e.event_id) for e in story.followups] == [str(followup.event_id)]
    assert story.followups[0].thread_ts == "1000.000100"


def test_story_detail_missing_cluster_returns_none(repo: RepositoryProtocol) -> None:
    assert get_story_detail_use_case(repository=repo, cluster_key="nope") is None


def test_archived_events_excluded_from_stories(repo: RepositoryProtocol) -> None:
    active = _story_event(1, days_ago=1)
    archived = _story_event(2, status=EventStatus.COMPLETED, days_ago=0)
    repo.save_events([active, archived])
    repo.update_event_review(
        event_id=str(archived.event_id),
        review_status=ReviewLifecycleStatus.ARCHIVED,
        reviewed_by="test",
    )

    stories = get_stories_use_case(repository=repo)
    assert len(stories) == 1
    assert stories[0].event_count == 1
    assert stories[0].current_status == EventStatus.PLANNED.value
