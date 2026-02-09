# Architecture Overview

This document is a living, LLM-oriented architecture guide for fast onboarding and safe changes.
Update it whenever runtime flows, storage, or interfaces change.

## 1. Project Structure

```text
slack-event-manager/
├── src/
│   ├── adapters/            # External integrations (Slack/Telegram clients, repositories, factories)
│   ├── clients/             # Wrapped client interfaces
│   ├── config/              # Settings + logging setup
│   ├── domain/              # Core models, enums, protocols, constants
│   ├── observability/       # Metrics/tracing
│   ├── ports/               # Abstractions for task queue / job runner
│   ├── presentation/        # Streamlit orchestration helpers
│   ├── services/            # Scoring, normalization, dedup helpers, registries
│   ├── use_cases/           # Pipeline business orchestration
│   └── workers/             # Queue worker implementations
├── scripts/                 # Operational entrypoints (pipeline runners, workers, auth, migration helpers)
├── config/
│   ├── defaults/            # *.example.yaml templates
│   ├── prompts/             # LLM prompt templates (slack.yaml, telegram.yaml)
│   └── schemas/             # JSON schemas for config validation
├── alembic/                 # DB migrations
├── tests/                   # Unit/integration tests
├── docs/                    # Operational docs (CONFIG, workers, observability)
├── docker-compose.yml       # Production-like local stack
├── Makefile                 # Dev/test/lint/typecheck commands
├── README.md                # User/developer quick start
└── ARCHITECTURE.md          # This file
```

## 2. High-Level System Diagram

```text
Slack API ----\
               \-> Ingestion -> Candidate Scoring -> LLM Extraction -> Dedup -> Events Store -> Digest Publish -> Slack
Telegram API -/

                                    \-> Streamlit UI (read/query)

Queue-based mode:
Scheduler -> pipeline_tasks -> ingest/extraction/llm/dedup workers -> same repositories/tables
```

## 3. Core Components

### 3.1. Runtime Entrypoints

Name: Direct Multi-Source Orchestrator

Description: Single-process end-to-end run across enabled sources.

Main script: `scripts/run_multi_source_pipeline.py`

Notes:
- Supports `--source slack|telegram`
- Supports continuous mode (`--interval-seconds`)
- Recommended for local and deterministic debugging

Name: Queue-Based Runtime

Description: Scheduler + workers with task queue table for distributed processing.

Main scripts:
- `scripts/run_pipeline_scheduler.py`
- `scripts/run_ingest_worker.py`
- `scripts/run_extraction_worker.py`
- `scripts/run_llm_worker.py`
- `scripts/run_dedup_worker.py`

Important current behavior:
- Ingest worker wiring is Slack-oriented via `create_slack_ingestion_handlers`.
- Full multi-source end-to-end path is implemented in `run_multi_source_pipeline.py`.

### 3.2. Source Integrations

#### 3.2.1 Slack Integration

Name: Slack Client Adapter

Description: Fetches channel history, user info, permalinks, and posts digest messages.

Code: `src/adapters/slack_client.py`

Technologies: `slack-sdk`

#### 3.2.2 Telegram Integration

Name: Telegram Client Adapter

Description: Fetches Telegram channel messages and normalizes source-specific fields.

Code: `src/adapters/telegram_client.py`, `src/use_cases/ingest_telegram_messages.py`

Technologies: `telethon`

### 3.3. Extraction and Business Logic

Name: Use Case Layer

Description:
- Ingestion: `ingest_messages.py`, `ingest_telegram_messages.py`
- Candidate building: `build_candidates.py`
- Event extraction: `extract_events.py`
- Deduplication: `deduplicate_events.py`
- Digest publishing: `publish_digest.py`

Key model fact:
- Source isolation is explicit via `source_id` (`MessageSource.SLACK`, `MessageSource.TELEGRAM`).

### 3.4. UI

Name: Streamlit Dashboard

Description: Read-only analytics/dashboard view over stored messages/candidates/events.

Entry point: `app.py`

Technologies: `streamlit`, `plotly`, `pandas`

Deployment: Docker service `streamlit-ui` or local `streamlit run app.py`

## 4. Data Stores

### 4.1 Primary Relational Store

Name: Pipeline Database

Type: SQLite (default dev) or PostgreSQL (production)

Purpose: Persist raw source data, candidates, events, state, LLM metadata, and queue tasks.

Important tables (across migrations):
- `raw_slack_messages`
- `raw_telegram_messages`
- `event_candidates`
- `events`
- `llm_calls`
- `slack_ingestion_state`
- `ingestion_state_telegram`
- `pipeline_tasks`
- `channel_watermarks`

Migration tool: Alembic (`alembic upgrade head`)

### 4.2 Task Queue

Name: Pipeline Task Queue

Type: DB-backed queue (`pipeline_tasks` table)

Purpose: Decouple scheduler and workers for ingestion/extraction/llm/dedup stages.

## 5. External Integrations / APIs

- Slack Web API
  - Purpose: Ingestion + digest delivery
  - Integration: `slack-sdk` (`WebClient`)

- Telegram API
  - Purpose: Telegram ingestion
  - Integration: `telethon` user client

- OpenAI API
  - Purpose: Event extraction from normalized candidate text
  - Integration: `openai` Python SDK through `src/adapters/llm_client.py`

## 6. Deployment & Infrastructure

Cloud/Runtime model:
- Local/dev: direct scripts or docker compose
- Production-style local stack: `docker-compose.yml`

Containerized services defined:
- `postgres`
- `pipeline-scheduler`
- `telegram-worker`
- `ingest-worker`
- `extraction-worker`
- `llm-worker`
- `dedup-worker`
- `metrics-exporter`
- `streamlit-ui`

CI/CD:
- GitHub Actions workflows in `.github/workflows/`
- `ci.yml` (lint/typecheck/test jobs)
- `pre-commit.yml` (pre-commit hook checks)

Monitoring & Logging:
- Structlog-based app logs (`src/config/logging_config.py`)
- Prometheus metrics exporter (`src/observability/metrics.py`)
- Health endpoint via Streamlit (`/_stcore/health`)

## 7. Security Considerations

Authentication / Secrets:
- Secrets are loaded from `.env` / process env:
  - `SLACK_BOT_TOKEN`
  - `OPENAI_API_KEY`
  - `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`
  - `POSTGRES_PASSWORD` (if postgres)

Authorization boundaries:
- Slack/Telegram/OpenAI authorization is delegated to respective tokens/credentials.

Data security practices:
- Keep secrets out of git
- Prefer env overrides for production secrets
- Restrict network access to metrics and Streamlit endpoints when deployed externally

## 8. Development & Testing Environment

Local setup (canonical):

```bash
make sync-dev
./scripts/setup_config.sh
make test-quick
```

Testing framework:
- `pytest`

Code quality tools:
- Ruff (format + lint)
- mypy (strict typing on `src`)
- pre-commit

Useful commands:

```bash
make pre-commit
make ci
python scripts/run_multi_source_pipeline.py --help
```

## 9. Future Considerations / Roadmap

- Align queue-based ingestion with full multi-source parity (currently Slack-oriented wiring).
- Keep docs and architecture notes synchronized with migrations and runtime scripts.
- Continue hardening source-specific isolation tests around `source_id` and dedup behavior.

## 10. Project Identification

Project Name: Slack Event Manager

Repository URL: `https://github.com/VaitaR/slack-event-manager`

Primary Runtime Language: Python 3.11

Date of Last Update: 2026-02-09

## 11. Glossary / Acronyms

- `LLM`: Large Language Model.
- `MessageSource`: Enum identifying source (`slack` / `telegram`).
- `Candidate`: Scored message selected for LLM extraction (`event_candidates`).
- `Dedup`: Event merge process to collapse semantically duplicated events.
- `Pipeline Tasks`: DB-backed queued work items used by worker runtime.
- `Direct Orchestrator`: `run_multi_source_pipeline.py` single-process full pipeline mode.
