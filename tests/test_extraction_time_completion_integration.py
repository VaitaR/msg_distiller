"""Integration test for time completion in extract_events_use_case (P0.1)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from src.config.settings import Settings
from src.domain.models import (
    EventCandidate,
    EventCategory,
    LLMCallMetadata,
    LLMEvent,
    LLMResponse,
    MessageSource,
    ScoringFeatures,
    TimeSource,
)
from src.services.importance_scorer import ImportanceScorer
from src.use_cases.extract_events import build_object_registry, extract_events_use_case


def test_extract_events_fills_missing_completed_time_and_saves_event() -> None:
    settings = MagicMock(spec=Settings)
    settings.llm_daily_budget_usd = 100.0
    settings.llm_max_events_per_msg = 5
    settings.llm_cache_ttl_days = 21
    settings.object_registry_path = "config/defaults/object_registry.example.yaml"
    settings.get_scoring_config.return_value = None
    settings.extraction_time_completion_enabled = True
    settings.extraction_prompt_metadata_enabled = False

    candidate_ts = datetime(2025, 12, 1, 12, 0, tzinfo=UTC)
    candidate = EventCandidate(
        message_id="msg-1",
        channel="general",
        ts_dt=candidate_ts,
        text_norm="Release completed",
        links_norm=[],
        anchors=[],
        score=1.0,
        features=ScoringFeatures(),
        source_id=MessageSource.SLACK,
    )

    llm_event = LLMEvent(
        action="launch",
        object_name_raw="Widget",
        qualifiers=[],
        stroke=None,
        anchor=None,
        category=EventCategory.PRODUCT,
        status="completed",
        change_type="launch",
        environment="prod",
        severity=None,
        planned_start=None,
        planned_end=None,
        actual_start=None,
        actual_end=None,
        time_source="explicit",
        time_confidence=0.9,
        summary="Widget release completed",
        why_it_matters="Improves user reliability and reduces support load.",
        links=[],
        anchors=[],
        impact_area=[],
        impact_type=[],
        confidence=0.9,
    )
    llm_response = LLMResponse(is_event=True, events=[llm_event])

    llm_client = MagicMock()
    llm_client.model = "gpt-5-nano"
    llm_client.system_prompt_hash = "prompt-hash"
    llm_client.prompt_token_budget = 3000
    llm_client.prompt_version = "v1"
    llm_client.extract_events_with_retry.return_value = llm_response
    llm_client.get_call_metadata.return_value = LLMCallMetadata(
        message_id="",
        prompt_hash="prompt-hash",
        model="gpt-5-nano",
        tokens_in=10,
        tokens_out=10,
        cost_usd=0.01,
        latency_ms=50,
        cached=False,
    )

    repository = MagicMock()
    repository.get_candidates_for_extraction.return_value = [candidate]
    repository.get_cached_llm_response.return_value = None
    repository.update_candidate_status.return_value = None
    repository.save_llm_call.return_value = None
    repository.save_llm_response.return_value = None
    repository.get_daily_llm_cost.return_value = 0.0
    repository.save_events.return_value = 1

    object_registry = build_object_registry(settings)
    importance_scorer = ImportanceScorer()

    result = extract_events_use_case(
        llm_client=llm_client,
        repository=repository,
        settings=settings,
        source_id=MessageSource.SLACK,
        batch_size=5,
        check_budget=False,
        object_registry=object_registry,
        importance_scorer=importance_scorer,
    )

    assert result.events_extracted == 1
    saved_events = repository.save_events.call_args[0][0]
    assert saved_events[0].actual_end == candidate_ts
    assert saved_events[0].time_source == TimeSource.TS_FALLBACK
    assert saved_events[0].time_confidence <= 0.3
