# SYSTEM_MAP

## End-to-end runtime map

### Primary runtime entrypoints
- [scripts/run_multi_source_pipeline.py](scripts/run_multi_source_pipeline.py)
  - `run_single_iteration()`
  - `run_source_pipeline()`
- Legacy single-source:
  - [scripts/run_pipeline.py](scripts/run_pipeline.py)

### Ingestion
- Slack path:
  - [src/use_cases/ingest_messages.py](src/use_cases/ingest_messages.py)
  - Called from `run_source_pipeline()` in [scripts/run_multi_source_pipeline.py](scripts/run_multi_source_pipeline.py)
- Telegram path:
  - [src/use_cases/ingest_telegram_messages.py](src/use_cases/ingest_telegram_messages.py)
  - Called via `ingest_telegram_messages_use_case_async()` in [scripts/run_multi_source_pipeline.py](scripts/run_multi_source_pipeline.py)

### Candidate scoring and candidate persistence
- [src/use_cases/build_candidates.py](src/use_cases/build_candidates.py)
  - `build_candidates_use_case()`
- Scoring logic:
  - [src/services/scoring_engine.py](src/services/scoring_engine.py)

### LLM extraction and event shaping
- [src/use_cases/extract_events.py](src/use_cases/extract_events.py)
  - `extract_events_use_case()`
  - `_process_candidate_with_llm()`
  - `convert_llm_event_to_domain()`
- Intra-message dedup/rank:
  - [src/services/intra_message_postprocess.py](src/services/intra_message_postprocess.py)
- Prompt routing / per-source prompt:
  - [src/services/llm_client_pool.py](src/services/llm_client_pool.py)
- Prompt files:
  - [config/prompts/slack.yaml](config/prompts/slack.yaml)
  - [config/prompts/telegram.yaml](config/prompts/telegram.yaml)

### Event validation and quality gates
- Structural/semantic validator:
  - [src/services/validators.py](src/services/validators.py)
- New deterministic policy layer:
  - [src/services/extraction_policy.py](src/services/extraction_policy.py)

### Deduplication across events
- [src/use_cases/deduplicate_events.py](src/use_cases/deduplicate_events.py)
  - `deduplicate_events_use_case()`
- Core service:
  - [src/services/deduplicator.py](src/services/deduplicator.py)

### Persistence
- SQLite:
  - [src/adapters/sqlite_repository.py](src/adapters/sqlite_repository.py)
- PostgreSQL:
  - [src/adapters/postgres_repository.py](src/adapters/postgres_repository.py)

### Timeline exposure and digest publication
- API timeline:
  - [src/api/routes_events.py](src/api/routes_events.py) (`/api/v1/events/timeline`)
- Digest:
  - [src/use_cases/publish_digest.py](src/use_cases/publish_digest.py)

### Workers path
- [src/workers/pipeline.py](src/workers/pipeline.py)
- Composition:
  - [src/use_cases/pipeline_factories.py](src/use_cases/pipeline_factories.py)

## Slack vs Telegram path differences

- Ingestion diverges by source-specific use cases (Slack sync vs Telegram async) in [scripts/run_multi_source_pipeline.py](scripts/run_multi_source_pipeline.py).
- Candidate scoring, extraction, post-processing, validation, dedup, persistence are shared.
- Prompt file can diverge per source and per channel via [src/services/llm_client_pool.py](src/services/llm_client_pool.py) and config.

## Critical control points for remediation

1. Intra-message cardinality control:
   - [src/services/intra_message_postprocess.py](src/services/intra_message_postprocess.py)
2. Pre-save event policy gates:
   - [src/use_cases/extract_events.py](src/use_cases/extract_events.py)
3. Action normalization:
   - `convert_llm_event_to_domain()` in [src/use_cases/extract_events.py](src/use_cases/extract_events.py)
4. Summary contract enforcement:
   - [src/services/extraction_policy.py](src/services/extraction_policy.py) + extraction save path
5. Recurring quality metrics:
   - quality snapshot log in [src/use_cases/extract_events.py](src/use_cases/extract_events.py)
   - local reporting script [scripts/quality_metrics_report.py](scripts/quality_metrics_report.py)
