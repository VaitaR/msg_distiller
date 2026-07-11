# Configuration Guide

## Sources of Configuration

`Settings` loads and merges:

1. `config/main.yaml`
2. Other `config/*.yaml` files (for example `channels.yaml`, `telegram_channels.yaml`, `object_registry.yaml`)
3. Environment variables (`.env` and process env)

Environment variables have highest priority and override YAML values.

## Required Secrets

Set in `.env`:

```bash
SLACK_BOT_TOKEN=xoxb-...
OPENAI_API_KEY=sk-...
```

Optional Telegram integration:

```bash
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=...
```

Optional PostgreSQL:

```bash
POSTGRES_PASSWORD=...
```

Mutating review API routes require an explicit shared token:

```bash
REVIEW_API_TOKEN=change-me
```

## Core Config Files

- `config/main.yaml`: global settings (LLM, database, processing, dedup, digest, logging)
- `config/channels.yaml`: Slack channel scoring settings
- `config/telegram_channels.yaml`: Telegram channel scoring settings
- `config/object_registry.yaml`: object canonicalization map

Templates live in `config/defaults/*.example.yaml` and are copied by:

```bash
./scripts/setup_config.sh
```

## Multi-Source Model

The system supports two sources:
- `slack`
- `telegram`

`Settings` exposes `message_sources` and source-aware helpers (`get_source_config`, `get_enabled_sources`, `get_scoring_config`).

If `message_sources` is not explicitly configured, legacy `channels` and `telegram_channels` configs are auto-migrated at runtime.

## Database Selection

Default is SQLite.

To use PostgreSQL, set:

```bash
DATABASE_TYPE=postgres
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DATABASE=slack_events
POSTGRES_USER=postgres
POSTGRES_PASSWORD=...
```

Run migrations:

```bash
alembic upgrade head
```

## API Runtime

Safe local defaults:

- `API_BIND_HOST=127.0.0.1`
- explicit browser origins via `api.allowed_origins` in `config/main.yaml`

Example:

```yaml
api:
	bind_host: 127.0.0.1
	allowed_origins:
		- http://127.0.0.1:5173
		- http://127.0.0.1:4173
		- http://127.0.0.1:4174
```

## Validation

YAML sections are validated against JSON schemas in `config/schemas/` when schemas are present.

## Recommended Local Setup

```bash
make sync-dev
./scripts/setup_config.sh
python -c "from src.config.settings import get_settings; get_settings(); print('settings ok')"
```
