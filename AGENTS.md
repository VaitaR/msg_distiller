# AGENTS.md

Updated: 2026-02-09

This file is the contributor/agent handbook for the current codebase.

## What This Project Is

Slack Event Manager is now a **multi-source** event extraction system:
- Slack source
- Telegram source

It ingests messages, builds scored candidates, extracts structured events with LLM, deduplicates, and publishes digest summaries to Slack.

## Architecture Snapshot

### Domain & Source Model
- `MessageSource` enum: `slack`, `telegram` (`src/domain/models.py`)
- Source-aware models:
  - `SlackMessage`
  - `TelegramMessage`
  - `EventCandidate.source_id`
  - `Event.source_id`

### Configuration
- Main settings are merged from `config/*.yaml` and env vars in `Settings` (`src/config/settings.py`)
- Multi-source config exposed as `message_sources`
- Backward compatibility migration exists from legacy `channels` + `telegram_channels`

### Data Access
- Repository factory: SQLite/PostgreSQL (`src/adapters/repository_factory.py`)
- Source-aware repository methods for ingestion/candidates/events
- Per-source raw/state handling in both repository implementations

### Orchestration
- Direct multi-source runner: `scripts/run_multi_source_pipeline.py`
- Legacy Slack-only runner: `scripts/run_pipeline.py`
- Queue-based runtime:
  - Scheduler: `scripts/run_pipeline_scheduler.py`
  - Workers: ingest / extraction scheduler / llm / dedup scripts

### Message Clients
- Slack client adapter (`src/adapters/slack_client.py`)
- Telegram client adapter (`src/adapters/telegram_client.py`)
- Client factory by source (`src/adapters/message_client_factory.py`)

## Recommended Runtime Paths

### Local development
Use direct multi-source orchestrator:

```bash
python scripts/run_multi_source_pipeline.py
```

### Source-specific execution

```bash
python scripts/run_multi_source_pipeline.py --source slack
python scripts/run_multi_source_pipeline.py --source telegram
```

### Production-style queue mode

```bash
python scripts/run_pipeline_scheduler.py --interval-seconds 300
python scripts/run_ingest_worker.py
python scripts/run_extraction_worker.py
python scripts/run_llm_worker.py
python scripts/run_dedup_worker.py
```

Important:
- Queue ingest composition is currently Slack-oriented (`create_slack_ingestion_handlers` in `src/use_cases/pipeline_factories.py`).
- For complete multi-source end-to-end processing in one command, use `run_multi_source_pipeline.py`.

## Setup Commands

```bash
pip install uv
make sync-dev
./scripts/setup_config.sh
```

Then edit local configs and secrets:
- `.env`
- `config/main.yaml`
- `config/channels.yaml`
- `config/telegram_channels.yaml`
- `config/object_registry.yaml`

## Testing & Quality Gates

```bash
make test-quick
make test-cov
make format-check
make lint
make typecheck
make ci
```

Tooling in use:
- Ruff (format + lint)
- mypy (type checks)
- pytest

## Configuration Truths

- Secrets belong in `.env`
- Non-sensitive settings belong in `config/*.yaml`
- Runtime env vars override YAML settings
- Primary config reference: `docs/CONFIG.md`

## Current File-Level Guidance

### High-signal directories
- `src/domain`: canonical business model and protocols
- `src/use_cases`: application orchestration boundaries
- `src/adapters`: external interfaces and persistence
- `src/workers`: queue worker runtime behavior
- `scripts`: executable operational entry points

### Sources and prompts
- Slack prompt: `config/prompts/slack.yaml`
- Telegram prompt: `config/prompts/telegram.yaml`

### Observability
- Metrics and health: `docs/OPERATIONS_OBSERVABILITY.md`

## Docker

`docker-compose.yml` provisions:
- PostgreSQL
- Pipeline scheduler
- Telegram worker
- Ingest/extraction/llm/dedup workers
- Metrics exporter
- Streamlit UI

Start:

```bash
docker compose build
docker compose up -d
```

## Contribution Rules

- Prefer updating use cases/services over adding logic to scripts
- Preserve source isolation (`source_id`) in new features
- Keep Slack+Telegram behavior explicit in tests
- Do not reintroduce obsolete `config.yaml` references
- Keep docs links valid and local-file backed

## Known Legacy/Compatibility Notes

- `scripts/run_pipeline.py` remains for Slack-only compatibility.
- Multi-source is first-class in `run_multi_source_pipeline.py` and repository/model layers.
- Settings comments may still mention `config.yaml` historically; implementation loads `config/main.yaml` + `config/*.yaml`.

## Documentation Index

- Docs index: `docs/README.md`
- Project README: `README.md`
- Config reference: `docs/CONFIG.md`
- Worker pipeline details: `docs/pipeline_workers.md`
- Operations and observability: `docs/OPERATIONS_OBSERVABILITY.md`
