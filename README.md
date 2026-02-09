# Slack Event Manager

Multi-source event extraction pipeline for **Slack** and **Telegram**.

The system ingests channel messages, scores candidates, extracts structured events with LLMs, deduplicates results, and optionally publishes a digest to Slack.

## Current Architecture

### Sources
- Slack (`MessageSource.SLACK`)
- Telegram (`MessageSource.TELEGRAM`)

### Pipeline Modes
1. **Direct orchestrator (recommended for local/dev):**
   - `scripts/run_multi_source_pipeline.py`
   - Runs ingest -> candidates -> LLM extraction -> dedup in one process
2. **Queue-based workers (recommended for production):**
   - Scheduler + workers (`scripts/run_pipeline_scheduler.py`, `scripts/run_ingest_worker.py`, `scripts/run_extraction_worker.py`, `scripts/run_llm_worker.py`, `scripts/run_dedup_worker.py`)

### Key Design Points
- Source-aware domain model (`source_id` on messages/candidates/events)
- Source-aware repository methods for ingestion, candidate selection, extraction, and dedup
- Per-source prompt configuration (`config/prompts/slack.yaml`, `config/prompts/telegram.yaml`)
- SQLite and PostgreSQL support through repository factory

## Repository Layout

```text
src/
  adapters/        # Slack/Telegram clients, repositories, factories
  clients/         # Wrapped client interfaces
  config/          # Settings + logging
  domain/          # Models, protocols, business constants
  observability/   # Metrics/tracing
  ports/           # Task queue and job runner ports
  presentation/    # Streamlit orchestration helpers
  services/        # Scoring, dedup, normalization, object registry, etc.
  use_cases/       # Ingest/extract/dedup/publish orchestration
  workers/         # Task-queue workers
scripts/           # CLI entry points and operational scripts
config/defaults/   # Example YAML templates copied by setup script
```

## Requirements

- Python `3.11+`
- `uv`
- Slack bot token (`SLACK_BOT_TOKEN`)
- OpenAI API key (`OPENAI_API_KEY`)
- Optional for Telegram:
  - `TELEGRAM_API_ID`
  - `TELEGRAM_API_HASH`

## Quick Start

### 1. Install

```bash
git clone https://github.com/VaitaR/slack-event-manager.git
cd slack-event-manager
pip install uv
make sync-dev
```

### 2. Generate Config Files

```bash
./scripts/setup_config.sh
```

This creates local editable files from `config/defaults/*.example.yaml`:
- `config/main.yaml`
- `config/channels.yaml`
- `config/object_registry.yaml`
- `config/telegram_channels.yaml`
- `.env`

### 3. Fill Secrets

Edit `.env`:

```bash
SLACK_BOT_TOKEN=xoxb-...
OPENAI_API_KEY=sk-...

# Optional Telegram
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=...

# Optional PostgreSQL
POSTGRES_PASSWORD=...
```

## Configuration Model

Runtime config is loaded from `config/main.yaml` + other `config/*.yaml` files and merged.

Important files:
- `config/main.yaml` - global pipeline/db/llm/digest settings
- `config/channels.yaml` - Slack scoring/channel config
- `config/telegram_channels.yaml` - Telegram channel config
- `config/object_registry.yaml` - canonical object mappings

Detailed reference: [`docs/CONFIG.md`](docs/CONFIG.md)

## Run Commands

### Multi-source Pipeline

```bash
# Run all enabled sources once
python scripts/run_multi_source_pipeline.py

# Run only Slack
python scripts/run_multi_source_pipeline.py --source slack

# Run only Telegram
python scripts/run_multi_source_pipeline.py --source telegram

# Continuous mode
python scripts/run_multi_source_pipeline.py --interval-seconds 3600

# Publish digest
python scripts/run_multi_source_pipeline.py --publish

# Dry-run publish
python scripts/run_multi_source_pipeline.py --publish --dry-run
```

### Legacy Slack-only Pipeline

```bash
python scripts/run_pipeline.py
```

Use this only if you need the older Slack-only flow. For two-source processing use `run_multi_source_pipeline.py`.

### Queue-based Runtime

```bash
# Enqueue periodic iterations
python scripts/run_pipeline_scheduler.py --interval-seconds 300

# Workers
python scripts/run_ingest_worker.py
python scripts/run_extraction_worker.py
python scripts/run_llm_worker.py
python scripts/run_dedup_worker.py
```

Notes:
- Current ingest worker composition is Slack-oriented (`create_slack_ingestion_handlers`).
- Multi-source end-to-end processing is fully supported via `run_multi_source_pipeline.py`.

## Docker

```bash
docker compose build
docker compose up -d
```

Services include PostgreSQL, pipeline scheduler/workers, Telegram worker, metrics exporter, and Streamlit UI.

## Testing & Quality

```bash
# Fast tests
make test-quick

# Coverage
make test-cov

# Lint + format + typecheck + tests
make ci

# Fast local checks
make pre-commit
```

Tooling:
- Formatter/Linter: Ruff
- Type checking: mypy
- Tests: pytest

## Streamlit UI

```bash
streamlit run app.py
```

Default URL: `http://127.0.0.1:8501`

## Operations & Reference Docs

- Docs index: [`docs/README.md`](docs/README.md)
- Configuration: [`docs/CONFIG.md`](docs/CONFIG.md)
- Metrics/health/observability: [`docs/OPERATIONS_OBSERVABILITY.md`](docs/OPERATIONS_OBSERVABILITY.md)
- Pipeline workers: [`docs/pipeline_workers.md`](docs/pipeline_workers.md)

## Development Notes

- Keep secrets only in `.env`
- Keep non-sensitive app config in `config/*.yaml`
- Prefer `make` targets over manual tool invocations
- Validate changes with `make ci` before pushing
