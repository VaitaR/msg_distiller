"""Embed events use case.

Generates one embedding per event for semantic search and the cross-source
dedup second pass. Selects events that have no stored embedding for the
configured model (this also backfills legacy events incrementally), renders
a compact text representation, and embeds in batches.

Known v1 limitation: an event edited after embedding is NOT re-embedded
(selection is by missing row, not by text_hash drift). Given small loads
and rare human edits this is acceptable; revisit if edits become frequent.
"""

import hashlib
from datetime import datetime
from typing import Any

import pytz

from src.config.logging_config import get_logger
from src.config.settings import Settings
from src.domain.exceptions import BudgetExceededError, LLMAPIError
from src.domain.models import Event
from src.domain.protocols import RepositoryProtocol
from src.services.title_renderer import TitleRenderer

logger = get_logger(__name__)

_title_renderer = TitleRenderer()


def render_embedding_text(event: Event) -> str:
    """Render the canonical text that gets embedded for an event."""
    parts = [
        _title_renderer.render_canonical_title(event),
        event.summary,
    ]
    if event.why_it_matters:
        parts.append(event.why_it_matters)
    if event.object_name_raw:
        parts.append(f"Object: {event.object_name_raw}")
    return "\n".join(part.strip() for part in parts if part and part.strip())


def embedding_text_hash(text: str) -> str:
    """Stable hash of the embedded text (stored for future drift detection)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _ensure_budget_allows_call(
    *, repository: RepositoryProtocol, settings: Settings
) -> None:
    """Raise BudgetExceededError if the daily LLM budget is exhausted."""
    today = datetime.now(tz=pytz.UTC)
    daily_cost = repository.get_daily_llm_cost(today)
    if daily_cost >= settings.llm_daily_budget_usd:
        raise BudgetExceededError(
            f"Daily budget ${settings.llm_daily_budget_usd} exceeded: ${daily_cost:.2f}"
        )


def embed_events_use_case(
    *,
    repository: RepositoryProtocol,
    llm_client: Any,
    settings: Settings,
    limit: int = 500,
) -> dict[str, int]:
    """Embed events that have no stored embedding for the configured model.

    Args:
        repository: Storage backend
        llm_client: LLM client exposing embed_texts / get_call_metadata
        settings: Application settings (model, batch size, budget)
        limit: Max events to process in one run

    Returns:
        Stats dict: events_selected, events_embedded, batches, budget_stopped
    """
    stats = {
        "events_selected": 0,
        "events_embedded": 0,
        "batches": 0,
        "budget_stopped": 0,
    }

    if not settings.embeddings_enabled:
        logger.info("embeddings_disabled_skipping")
        return stats

    model = settings.embedding_model
    events = repository.get_events_missing_embedding(model, limit=limit)
    stats["events_selected"] = len(events)
    if not events:
        return stats

    batch_size = settings.embedding_batch_size
    for start in range(0, len(events), batch_size):
        batch = events[start : start + batch_size]
        texts = [render_embedding_text(event) for event in batch]

        try:
            _ensure_budget_allows_call(repository=repository, settings=settings)
            vectors = llm_client.embed_texts(texts, model=model)
        except BudgetExceededError:
            logger.warning(
                "embedding_budget_exceeded",
                embedded_so_far=stats["events_embedded"],
                remaining=len(events) - stats["events_embedded"],
            )
            stats["budget_stopped"] = 1
            break
        except LLMAPIError as exc:
            logger.error("embedding_batch_failed", error=str(exc))
            break

        repository.save_event_embeddings(
            [
                (str(event.event_id), model, embedding_text_hash(text), vector)
                for event, text, vector in zip(batch, texts, vectors, strict=True)
            ]
        )
        repository.save_llm_call(llm_client.get_call_metadata())

        stats["events_embedded"] += len(batch)
        stats["batches"] += 1

    logger.info(
        "embed_events_completed",
        events_embedded=stats["events_embedded"],
        batches=stats["batches"],
    )
    return stats
