"""Tests for WS1: embeddings storage, cosine fallback, semantic dedup policy."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from src.config.settings import Settings
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
from src.services.vector_math import cosine_similarity
from src.use_cases.embed_events import (
    embed_events_use_case,
    embedding_text_hash,
    render_embedding_text,
)
from src.use_cases.semantic_dedup import semantic_dedup_use_case
from tests.factories import SEED_EVENTS

MODEL = "text-embedding-3-small"


def _make_event(
    n: int,
    *,
    action: ActionType = ActionType.LAUNCH,
    status: EventStatus = EventStatus.COMPLETED,
    dedup_key: str | None = None,
    source_id: MessageSource = MessageSource.SLACK,
) -> Event:
    """Recent event with a distinct dedup_key (semantic dedup ignores same keys)."""
    now = datetime.now(tz=UTC)
    return Event(
        event_id=f"00000000-0000-0000-0000-{n:012d}",
        message_id=f"msg-sem-{n:03d}",
        source_channels=["#releases"],
        message_published_at=now,
        extracted_at=now,
        action=action,
        object_name_raw=f"Feature {n}",
        category=EventCategory.PRODUCT,
        status=status,
        change_type=ChangeType.LAUNCH,
        environment=Environment.PROD,
        planned_start=now,
        time_source=TimeSource.EXPLICIT,
        time_confidence=0.9,
        summary=f"Feature {n} shipped to production.",
        confidence=0.9,
        importance=70,
        cluster_key=f"cluster-{n}",
        dedup_key=dedup_key or f"dedup-{n}",
        source_id=source_id,
        review_status=ReviewLifecycleStatus.NEEDS_REVIEW,
        origin=EventOrigin.AI_EXTRACTION,
        version=1,
    )


# ---------------------------------------------------------------------------
# vector_math
# ---------------------------------------------------------------------------


def test_cosine_identical_vectors() -> None:
    assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)


def test_cosine_orthogonal_vectors() -> None:
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_zero_norm_returns_zero() -> None:
    assert cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0


def test_cosine_length_mismatch_raises() -> None:
    with pytest.raises(ValueError, match="length mismatch"):
        cosine_similarity([1.0], [1.0, 2.0])


# ---------------------------------------------------------------------------
# Embedding text rendering
# ---------------------------------------------------------------------------


def test_render_embedding_text_contains_core_fields() -> None:
    event = SEED_EVENTS[0]
    text = render_embedding_text(event)
    assert event.summary in text
    assert event.object_name_raw in text
    assert event.why_it_matters in text


def test_embedding_text_hash_is_stable_and_content_sensitive() -> None:
    text = render_embedding_text(SEED_EVENTS[0])
    assert embedding_text_hash(text) == embedding_text_hash(text)
    assert embedding_text_hash(text) != embedding_text_hash(text + "x")


# ---------------------------------------------------------------------------
# SQLite storage roundtrip + cosine fallback search
# ---------------------------------------------------------------------------


def test_sqlite_embedding_roundtrip_and_similarity(repo: RepositoryProtocol) -> None:
    events = [_make_event(1), _make_event(2), _make_event(3)]
    repo.save_events(events)

    missing = repo.get_events_missing_embedding(MODEL)
    assert {str(e.event_id) for e in missing} == {str(e.event_id) for e in events}

    # Event 1 and 2 nearly parallel, event 3 orthogonal
    repo.save_event_embeddings(
        [
            (str(events[0].event_id), MODEL, "h1", [1.0, 0.0, 0.0]),
            (str(events[1].event_id), MODEL, "h2", [0.99, 0.14, 0.0]),
            (str(events[2].event_id), MODEL, "h3", [0.0, 0.0, 1.0]),
        ]
    )

    assert repo.get_events_missing_embedding(MODEL) == []

    stored = repo.get_event_embeddings([str(e.event_id) for e in events], MODEL)
    assert stored[str(events[0].event_id)] == [1.0, 0.0, 0.0]

    results = repo.find_similar_events(
        [1.0, 0.0, 0.0],
        model=MODEL,
        limit=10,
        min_similarity=0.5,
        exclude_event_id=str(events[0].event_id),
    )
    assert [str(e.event_id) for e, _ in results] == [str(events[1].event_id)]
    assert results[0][1] == pytest.approx(0.99, abs=0.01)


def test_sqlite_missing_embedding_excludes_archived(repo: RepositoryProtocol) -> None:
    active = _make_event(1)
    archived = _make_event(2)
    repo.save_events([active, archived])
    repo.update_event_review(
        event_id=str(archived.event_id),
        review_status=ReviewLifecycleStatus.ARCHIVED,
        reviewed_by="test",
    )

    missing = repo.get_events_missing_embedding(MODEL)
    assert [str(e.event_id) for e in missing] == [str(active.event_id)]


def test_sqlite_save_event_relation_idempotent(repo: RepositoryProtocol) -> None:
    a, b = _make_event(1), _make_event(2)
    repo.save_events([a, b])
    for _ in range(2):
        repo.save_event_relation(
            str(a.event_id),
            RelationType.DUPLICATE_SUSPECT.value,
            str(b.event_id),
        )
    relations = repo.get_event_relations(
        str(a.event_id), RelationType.DUPLICATE_SUSPECT.value
    )
    assert len(relations) == 1


# ---------------------------------------------------------------------------
# embed_events use case
# ---------------------------------------------------------------------------


def test_embed_events_batches_and_saves(repo: RepositoryProtocol, settings: Settings) -> None:
    events = [_make_event(i) for i in range(1, 4)]
    repo.save_events(events)

    llm_client = MagicMock()
    llm_client.embed_texts.side_effect = lambda texts, model: [
        [1.0, 0.0, 0.0] for _ in texts
    ]
    llm_client.get_call_metadata.return_value = MagicMock()

    test_settings = settings.model_copy(update={"embedding_batch_size": 2})
    # Avoid persisting MagicMock metadata into llm_calls
    repo.save_llm_call = MagicMock()  # type: ignore[method-assign]

    stats = embed_events_use_case(
        repository=repo, llm_client=llm_client, settings=test_settings
    )

    assert stats["events_embedded"] == 3
    assert stats["batches"] == 2  # batch_size=2 -> 2+1
    assert repo.get_events_missing_embedding(MODEL) == []


def test_embed_events_disabled_is_noop(repo: RepositoryProtocol, settings: Settings) -> None:
    llm_client = MagicMock()
    stats = embed_events_use_case(
        repository=repo,
        llm_client=llm_client,
        settings=settings.model_copy(update={"embeddings_enabled": False}),
    )
    assert stats["events_embedded"] == 0
    llm_client.embed_texts.assert_not_called()


# ---------------------------------------------------------------------------
# semantic dedup thresholds
# ---------------------------------------------------------------------------


def _seed_pair(
    repo: RepositoryProtocol,
    *,
    vec_a: list[float],
    vec_b: list[float],
    action_b: ActionType = ActionType.LAUNCH,
    status_b: EventStatus = EventStatus.COMPLETED,
) -> tuple[Event, Event]:
    a = _make_event(1, source_id=MessageSource.SLACK)
    b = _make_event(
        2, action=action_b, status=status_b, source_id=MessageSource.TELEGRAM
    )
    repo.save_events([a, b])
    repo.save_event_embeddings(
        [
            (str(a.event_id), MODEL, "ha", vec_a),
            (str(b.event_id), MODEL, "hb", vec_b),
        ]
    )
    return a, b


def test_semantic_dedup_auto_merges_high_similarity(
    repo: RepositoryProtocol, settings: Settings
) -> None:
    a, b = _seed_pair(repo, vec_a=[1.0, 0.0, 0.0], vec_b=[1.0, 0.02, 0.0])

    stats = semantic_dedup_use_case(repository=repo, settings=settings)

    assert stats["merged"] == 1
    assert stats["suspected"] == 0
    absorbed = repo.get_event_by_id(str(b.event_id))
    assert absorbed is not None
    assert absorbed.review_status == ReviewLifecycleStatus.ARCHIVED


def test_semantic_dedup_marks_suspect_in_band(
    repo: RepositoryProtocol, settings: Settings
) -> None:
    # cosine ~0.85: above suspect (0.80), below auto-merge (0.92)
    a, b = _seed_pair(repo, vec_a=[1.0, 0.0, 0.0], vec_b=[0.85, 0.527, 0.0])

    stats = semantic_dedup_use_case(repository=repo, settings=settings)

    assert stats["merged"] == 0
    assert stats["suspected"] == 1
    survivor = repo.get_event_by_id(str(b.event_id))
    assert survivor is not None
    assert survivor.review_status != ReviewLifecycleStatus.ARCHIVED


def test_semantic_dedup_incompatible_action_becomes_suspect(
    repo: RepositoryProtocol, settings: Settings
) -> None:
    # High similarity but different action -> no merge, suspect instead
    _seed_pair(
        repo,
        vec_a=[1.0, 0.0, 0.0],
        vec_b=[1.0, 0.02, 0.0],
        action_b=ActionType.INCIDENT,
        status_b=EventStatus.STARTED,
    )

    stats = semantic_dedup_use_case(repository=repo, settings=settings)

    assert stats["merged"] == 0
    assert stats["suspected"] == 1


def test_semantic_dedup_below_suspect_threshold_ignored(
    repo: RepositoryProtocol, settings: Settings
) -> None:
    _seed_pair(repo, vec_a=[1.0, 0.0, 0.0], vec_b=[0.5, 0.866, 0.0])  # cosine 0.5

    stats = semantic_dedup_use_case(repository=repo, settings=settings)

    assert stats["merged"] == 0
    assert stats["suspected"] == 0
