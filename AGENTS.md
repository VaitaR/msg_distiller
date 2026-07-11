# AGENTS.md

Updated: 2026-03-28

This file is the contributor/agent handbook for the current codebase.

## What This Project Is

Slack Event Manager is a **multi-source** event extraction and review system:
- Slack source
- Telegram source

It ingests messages, builds scored candidates, extracts structured events with LLM, deduplicates, supports human review/edit workflow, and publishes events to a timeline and API.

**Tech stack**: Python 3.12, uv, ruff, pytest, structlog, FastAPI, Dash+Plotly, React+TypeScript+Vite, Tailwind, Pydantic v2, OpenTelemetry, SQLite/PostgreSQL.

## Architecture Snapshot

### Layers (inside → outside)

1. **`src/domain`** — Models, enums, protocols (zero I/O)
2. **`src/use_cases`** — Business orchestration
3. **`src/services`** — Stateless helpers (scoring, dedup, title rendering)
4. **`src/adapters`** — DB repos, clients, LLM (implements protocols)
5. **`src/api`** — FastAPI backend (events CRUD, timeline, review)
6. **`src/presentation/dash_app`** — Dash UI (reads only via API)
7. **`frontend`** — React MVP frontend (review queue + timeline)
8. **`src/workers`** — Queue worker runtime
9. **`src/observability`** — Metrics and tracing

### Domain & Source Model
- `MessageSource` enum: `slack`, `telegram` (`src/domain/models.py`)
- `ReviewLifecycleStatus` enum: `needs_review → approved → published → rejected → archived`
- `EventOrigin` enum: `ai_extraction`, `human_edit`, `human_review`, `system_merge`
- `EventAuditEntry` — append-only audit log
- `EventVersion` — full snapshot history

### Configuration
- Main settings merged from `config/*.yaml` and env vars in `Settings` (`src/config/settings.py`)
- Multi-source config exposed as `message_sources`

### Data Access
- Repository factory: SQLite/PostgreSQL (`src/adapters/repository_factory.py`)
- Review lifecycle methods: `get_events_for_review`, `update_event_review`, `update_event_fields`, audit/version persistence

### API Layer
- FastAPI app: `src/api/app.py`
- Events endpoints: `src/api/routes_events.py`
- Schemas: `src/api/schemas.py`
- Run: `python scripts/run_api_server.py` or `just api`

### Presentation Layer
- Dash UI: `src/presentation/dash_app/`
- Review queue, timeline views, callbacks
- Run: `python scripts/run_dash.py` or `just dash`

### Frontend MVP
- React app: `frontend/`
- Review queue and timeline are backed by FastAPI only
- Run: `cd frontend && npm run dev`
- Build: `cd frontend && npm run build`
- Browser smoke: `cd frontend && npm run test:e2e`

### Orchestration
- Multi-source runner: `scripts/run_multi_source_pipeline.py`
- Queue-based workers: ingest / extraction / llm / dedup scripts

## Recommended Runtime Paths

### Local development — quick start

```bash
just sync            # Install deps
just api             # Start API server (port 8000)
just dash            # Start Dash UI (port 8050)
cd frontend && npm run dev   # Start React frontend (port 5173)
```

### Pipeline execution

```bash
just pipeline                           # Run all sources
just pipeline --source slack            # Slack only
just pipeline --source telegram         # Telegram only
```

### Full quality check

```bash
just ci              # format-check + lint + typecheck + test
```

### Production-style (Docker)

```bash
docker compose build && docker compose up -d
# Services: postgres, api-server, dash-ui, pipeline-scheduler, workers
```

## Setup Commands

```bash
pip install uv
just sync                    # or: make sync-dev
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
just test            # Unit + integration (excl. postgres/telegram)
just test-api        # API tests only
just test-e2e        # Playwright e2e (SKIP_E2E=0 + seeded servers on ports 18000/18050)
just test-cov        # With coverage
just ci              # Full CI: fmt-check + lint + typecheck + test
```

### Test seed data

`tests/factories.py` is the single source of truth for **15 deterministic seed events** used at every test layer:

| IDs | Status | Source |
|-----|--------|--------|
| 1-5 | `needs_review` | slack (#1-3), telegram (#4-5) |
| 6-8 | `approved` | slack (#6-7), telegram (#8) |
| 9-11 | `published` | slack (#9), telegram (#10-11) |
| 12-13 | `rejected` | slack (#12), telegram (#13) |
| 14-15 | `archived` | slack (#14), telegram (#15) |

Key exports: `SEED_EVENTS`, `SEED_COUNTS`, `NEEDS_REVIEW_IDS`, `APPROVED_IDS`, `PUBLISHED_IDS`.

### Test fixtures

- `seeded_db` (function-scoped) — fresh isolated SQLite DB per test; yields `(db_path, events)`.
- `seeded_db_session` (session-scoped) — shared DB across a test session (used by e2e servers).
- `seeded_api_client` — FastAPI `TestClient` with `dependency_overrides[get_repo]` pointing at the seeded DB.

### E2e server setup

E2e tests start isolated subprocess servers on **ports 18000 (API) and 18050 (Dash)** using the session-scoped seeded DB. `SKIP_E2E=0` must be set — `just test-e2e` sets it automatically. `scripts/run_dash.py` uses `threaded=True` to handle concurrent requests during tests.

Tooling in use:
- Ruff (format + lint)
- mypy (type checks)
- pytest
- Playwright (e2e, chromium)
- Vitest (frontend unit/component tests)
- Storybook (frontend component states)
- pre-commit

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
- `src/api`: FastAPI REST endpoints, schemas, DI
- `src/presentation/dash_app`: Dash UI layouts and callbacks
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
- API server (FastAPI, port 8000)
- Dash UI (port 8050)
- Pipeline scheduler
- Telegram worker
- Ingest/extraction/llm/dedup workers
- Metrics exporter

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
- Frontend API calls belong in `frontend/src/features/**/api.ts` or shared `frontend/src/lib/api/client.ts`, not inline in components
- For browser smoke checks of the React frontend, use `frontend/e2e/run_seeded_api_server.py` instead of mocking the main backend flows

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
