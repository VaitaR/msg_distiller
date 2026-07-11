"""Regression tests for deterministic extraction policy guards (P0/P1)."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

from src.config.settings import Settings
from src.domain.models import (
    ActionType,
    ChannelConfig,
    EventCategory,
    LLMCallMetadata,
    LLMEvent,
    LLMResponse,
    MessageSource,
)
from src.services.extraction_policy import (
    is_non_event_message,
    is_t_product_rescue_candidate,
)
from src.services.importance_scorer import ImportanceScorer
from src.use_cases.extract_events import (
    build_object_registry,
    convert_llm_event_to_domain,
    extract_events_use_case,
)
from tests.test_extract_events_caching import _make_candidate


def _settings() -> MagicMock:
    settings = MagicMock(spec=Settings)
    settings.llm_daily_budget_usd = 100.0
    settings.llm_max_events_per_msg = 5
    settings.llm_cache_ttl_days = 21
    settings.get_scoring_config.return_value = None
    settings.dedup_date_window_hours = 48
    settings.dedup_title_similarity = 0.8
    settings.object_registry_path = "config/defaults/object_registry.example.yaml"
    settings.extraction_time_completion_enabled = False
    settings.extraction_prompt_metadata_enabled = False
    return settings


def _llm_event(*, summary: str, why_it_matters: str | None, action: str = "Launch") -> LLMEvent:
    return LLMEvent(
        action=action,
        object_name_raw="Wallet Rewards",
        qualifiers=[],
        stroke="launched",
        anchor="ABC-123",
        category=EventCategory.PRODUCT,
        status="planned",
        change_type="launch",
        environment="prod",
        severity=None,
        planned_start=datetime.now(tz=UTC).isoformat(),
        planned_end=None,
        actual_start=None,
        actual_end=None,
        time_source="explicit",
        time_confidence=0.9,
        summary=summary,
        why_it_matters=why_it_matters,
        links=[],
        anchors=["ABC-123"],
        impact_area=["wallet"],
        impact_type=["ux_change"],
        confidence=0.95,
    )


def _llm_client(response: LLMResponse) -> MagicMock:
    llm_client = MagicMock()
    llm_client.model = "gpt-5-nano"
    llm_client.system_prompt_hash = "prompt-hash"
    llm_client.prompt_token_budget = 3000
    llm_client.prompt_version = "v1"
    llm_client.extract_events_with_retry.return_value = response
    llm_client.get_call_metadata.return_value = LLMCallMetadata(
        message_id="",
        prompt_hash="prompt-hash",
        model="gpt-5-nano",
        tokens_in=100,
        tokens_out=50,
        cost_usd=0.1,
        latency_ms=100,
        cached=False,
    )
    return llm_client


def _repo(candidate):
    repository = MagicMock()
    repository.get_candidates_for_extraction.return_value = [candidate]
    repository.get_cached_llm_response.return_value = None
    repository.update_candidate_status.return_value = None
    repository.get_daily_llm_cost.return_value = 0.0
    repository.save_events.return_value = 0
    repository.save_llm_call.return_value = None
    repository.save_llm_response.return_value = None
    return repository


def test_non_event_message_is_filtered_before_llm_call() -> None:
    settings = _settings()
    candidate = _make_candidate(
        text="Webinar announcement: join product seminar next week in support help thread"
    )
    repository = _repo(candidate)
    llm_client = _llm_client(LLMResponse(is_event=True, events=[_llm_event(summary="x", why_it_matters="y")]))

    result = extract_events_use_case(
        llm_client=llm_client,
        repository=repository,
        settings=settings,
        source_id=MessageSource.SLACK,
        batch_size=5,
        check_budget=False,
        object_registry=build_object_registry(settings),
        importance_scorer=ImportanceScorer(),
    )

    assert result.events_extracted == 0
    llm_client.extract_events_with_retry.assert_not_called()
    repository.save_events.assert_not_called()


def test_planned_only_event_without_release_evidence_is_rejected() -> None:
    settings = _settings()
    candidate = _make_candidate(text="Plan for next week: prepare rollout draft and discuss timeline")
    repository = _repo(candidate)
    llm_client = _llm_client(
        LLMResponse(
            is_event=True,
            events=[
                _llm_event(
                    summary="Wallet Rewards launched for wallet users.",
                    why_it_matters="Increases engagement and conversions.",
                )
            ],
        )
    )

    result = extract_events_use_case(
        llm_client=llm_client,
        repository=repository,
        settings=settings,
        source_id=MessageSource.SLACK,
        batch_size=5,
        check_budget=False,
        object_registry=build_object_registry(settings),
        importance_scorer=ImportanceScorer(),
    )

    assert result.events_extracted == 0
    repository.save_events.assert_not_called()


def test_planned_event_with_release_evidence_is_allowed() -> None:
    settings = _settings()
    candidate = _make_candidate(
        text="We rolled out Wallet Rewards and it is live in production for all users."
    )
    repository = _repo(candidate)
    llm_client = _llm_client(
        LLMResponse(
            is_event=True,
            events=[
                _llm_event(
                    summary="Wallet Rewards launched in wallet for all users and increased engagement.",
                    why_it_matters="Improves retention and drives activity.",
                )
            ],
        )
    )
    repository.save_events.return_value = 1

    result = extract_events_use_case(
        llm_client=llm_client,
        repository=repository,
        settings=settings,
        source_id=MessageSource.SLACK,
        batch_size=5,
        check_budget=False,
        object_registry=build_object_registry(settings),
        importance_scorer=ImportanceScorer(),
    )

    assert result.events_extracted == 1
    repository.save_events.assert_called_once()


def test_summary_missing_effect_is_soft_accepted_with_change_and_scope() -> None:
    settings = _settings()
    candidate = _make_candidate(
        text="We rolled out Wallet Rewards and it is live in production for all users."
    )
    repository = _repo(candidate)
    llm_client = _llm_client(
        LLMResponse(
            is_event=True,
            events=[
                _llm_event(
                    summary="Wallet Rewards launched in wallet for all users.",
                    why_it_matters=None,
                )
            ],
        )
    )
    repository.save_events.return_value = 1

    result = extract_events_use_case(
        llm_client=llm_client,
        repository=repository,
        settings=settings,
        source_id=MessageSource.SLACK,
        batch_size=5,
        check_budget=False,
        object_registry=build_object_registry(settings),
        importance_scorer=ImportanceScorer(),
    )

    assert result.events_extracted == 1
    repository.save_events.assert_called_once()


def test_summary_missing_change_is_rejected() -> None:
    settings = _settings()
    candidate = _make_candidate(
        text="We rolled out Wallet Rewards and it is live in production for all users."
    )
    repository = _repo(candidate)
    llm_client = _llm_client(
        LLMResponse(
            is_event=True,
            events=[
                _llm_event(
                    summary="Wallet Rewards for all users in wallet.",
                    why_it_matters="Improves retention.",
                    action="Other",
                )
            ],
        )
    )

    result = extract_events_use_case(
        llm_client=llm_client,
        repository=repository,
        settings=settings,
        source_id=MessageSource.SLACK,
        batch_size=5,
        check_budget=False,
        object_registry=build_object_registry(settings),
        importance_scorer=ImportanceScorer(),
    )

    assert result.events_extracted == 0
    repository.save_events.assert_not_called()


def test_summary_missing_change_is_recovered_when_action_implies_change() -> None:
    settings = _settings()
    candidate = _make_candidate(
        text="We rolled out Wallet Rewards and it is live in production for all users."
    )
    repository = _repo(candidate)
    llm_client = _llm_client(
        LLMResponse(
            is_event=True,
            events=[
                _llm_event(
                    summary="Wallet Rewards for all users in wallet.",
                    why_it_matters="Improves retention.",
                    action="Launch",
                )
            ],
        )
    )
    repository.save_events.return_value = 1

    result = extract_events_use_case(
        llm_client=llm_client,
        repository=repository,
        settings=settings,
        source_id=MessageSource.SLACK,
        batch_size=5,
        check_budget=False,
        object_registry=build_object_registry(settings),
        importance_scorer=ImportanceScorer(),
    )

    assert result.events_extracted == 1
    repository.save_events.assert_called_once()


def test_summary_missing_change_is_recovered_for_policy_action() -> None:
    settings = _settings()
    candidate = _make_candidate(
        text="Policy update is live in production for wallet verification workflow."
    )
    repository = _repo(candidate)
    llm_client = _llm_client(
        LLMResponse(
            is_event=True,
            events=[
                _llm_event(
                    summary="Wallet verification rules for active users.",
                    why_it_matters="Improves compliance coverage.",
                    action="Policy",
                )
            ],
        )
    )
    repository.save_events.return_value = 1

    result = extract_events_use_case(
        llm_client=llm_client,
        repository=repository,
        settings=settings,
        source_id=MessageSource.SLACK,
        batch_size=5,
        check_budget=False,
        object_registry=build_object_registry(settings),
        importance_scorer=ImportanceScorer(),
    )

    assert result.events_extracted == 1
    repository.save_events.assert_called_once()


def test_summary_missing_scope_is_rejected() -> None:
    settings = _settings()
    candidate = _make_candidate(
        text="We rolled out a release and it is live in production for all users."
    )
    repository = _repo(candidate)
    llm = _llm_event(
        summary="Release launched and increased engagement.",
        why_it_matters="Improves retention.",
    )
    llm.object_name_raw = ""
    llm_client = _llm_client(LLMResponse(is_event=True, events=[llm]))

    result = extract_events_use_case(
        llm_client=llm_client,
        repository=repository,
        settings=settings,
        source_id=MessageSource.SLACK,
        batch_size=5,
        check_budget=False,
        object_registry=build_object_registry(settings),
        importance_scorer=ImportanceScorer(),
    )

    assert result.events_extracted == 0
    repository.save_events.assert_not_called()


def test_t_product_rescue_candidate_heuristic() -> None:
    assert is_t_product_rescue_candidate(
        "Policy gate enabled and rolled out in production for wallet verification"
    )
    assert is_t_product_rescue_candidate(
        "*🚀 key launch dates* perps launched in prod and workflow updated"
    )
    assert is_t_product_rescue_candidate(
        "Сегодня делистнули ассет X, нужно отключить покупку и обнулить комиссию"
    )
    assert not is_t_product_rescue_candidate(
        "Can someone help with research question on roadmap ideas?"
    )
    assert not is_non_event_message(
        "Мне нужна помощь: сегодня делистнули актив, нужно отключить покупку"
    )


def test_t_product_second_pass_recovers_event() -> None:
    settings = _settings()
    settings.get_scoring_config.return_value = ChannelConfig(
        channel_id="C04UCRJ7UTF",
        channel_name="t-product",
        rescue_enabled=True,
    )
    candidate = _make_candidate(
        text="We rolled out policy gate in production for wallet verification users."
    )
    candidate.channel = "C04UCRJ7UTF"
    repository = _repo(candidate)

    first_response = LLMResponse(is_event=False, events=[])
    second_response = LLMResponse(
        is_event=True,
        events=[
            _llm_event(
                action="Policy",
                summary="Wallet verification rules for active users.",
                why_it_matters="Improves compliance coverage.",
            )
        ],
    )
    llm_client = _llm_client(first_response)
    llm_client.extract_events_with_retry.side_effect = [first_response, second_response]
    repository.save_events.return_value = 1

    result = extract_events_use_case(
        llm_client=llm_client,
        repository=repository,
        settings=settings,
        source_id=MessageSource.SLACK,
        batch_size=5,
        check_budget=False,
        object_registry=build_object_registry(settings),
        importance_scorer=ImportanceScorer(),
    )

    assert result.events_extracted == 1
    assert llm_client.extract_events_with_retry.call_count == 2
    repository.save_events.assert_called_once()


def test_rescue_skipped_when_channel_flag_disabled() -> None:
    settings = _settings()
    settings.get_scoring_config.return_value = ChannelConfig(
        channel_id="C04UCRJ7UTF",
        channel_name="t-product",
        rescue_enabled=False,
    )
    candidate = _make_candidate(
        text="We rolled out policy gate in production for wallet verification users."
    )
    candidate.channel = "C04UCRJ7UTF"
    repository = _repo(candidate)

    llm_client = _llm_client(LLMResponse(is_event=False, events=[]))

    result = extract_events_use_case(
        llm_client=llm_client,
        repository=repository,
        settings=settings,
        source_id=MessageSource.SLACK,
        batch_size=5,
        check_budget=False,
        object_registry=build_object_registry(settings),
        importance_scorer=ImportanceScorer(),
    )

    assert result.events_extracted == 0
    assert llm_client.extract_events_with_retry.call_count == 1
    repository.save_events.assert_not_called()


def test_action_normalization_maps_lowercase_to_canonical_enum() -> None:
    settings = _settings()
    llm_event = _llm_event(
        summary="Wallet Rewards launched in wallet and increased engagement.",
        why_it_matters="Improves retention.",
        action="launch",
    )

    event = convert_llm_event_to_domain(
        llm_event,
        message_id="m1",
        message_ts_dt=datetime.now(tz=UTC),
        channel_name="general",
        source_id=MessageSource.SLACK,
        object_registry=build_object_registry(settings),
    )

    assert event.action == ActionType.LAUNCH
