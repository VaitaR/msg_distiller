# justfile — project task runner (replaces Makefile over time)
# Install: brew install just / cargo install just
# Usage: just <recipe>

set dotenv-load := true
set shell := ["zsh", "-cu"]

python := "python3.12"
uv_python := "python3.12"

# Default recipe: show help
default:
    @just --list

# ─── Setup ──────────────────────────────────────────────────────────────

# Sync dev dependencies (frozen lockfile)
sync:
    uv sync --python {{uv_python}} --frozen --no-install-project

# Sync runtime only
sync-prod:
    uv sync --python {{uv_python}} --frozen --no-dev --no-install-project

# Lock dependencies
lock:
    uv lock --python {{uv_python}}

# Check lock is up-to-date
lock-check:
    uv lock --check

# Install pre-commit hooks
setup:
    uv sync --python {{uv_python}} --frozen --no-install-project
    uv run pre-commit install
    @echo "✓ Dev environment ready"

# ─── Quality ────────────────────────────────────────────────────────────

# Format code
fmt:
    uv run ruff format .

# Check formatting (no changes)
fmt-check:
    uv run ruff format --check .

# Lint
lint:
    uv run ruff check .

# Lint with auto-fix
lint-fix:
    uv run ruff check . --fix --unsafe-fixes

# Type check with mypy
typecheck:
    uv run mypy src --config-file pyproject.toml

# ─── Tests ──────────────────────────────────────────────────────────────

# Run tests (unit + integration, excludes postgres/telegram)
test:
    SLACK_BOT_TOKEN=dummy OPENAI_API_KEY=dummy uv run python -m pytest -k "not (test_postgres_repository or telegram)"

# Quick tests (no coverage)
test-quick:
    SLACK_BOT_TOKEN=dummy OPENAI_API_KEY=dummy uv run pytest -q --no-cov

# Tests with coverage
test-cov:
    SLACK_BOT_TOKEN=dummy OPENAI_API_KEY=dummy uv run pytest --cov=src --cov-report=term-missing --cov-report=html

# Run API tests only
test-api:
    SLACK_BOT_TOKEN=dummy OPENAI_API_KEY=dummy uv run pytest tests/api/ -v

# Run e2e tests (Playwright)
test-e2e:
    SKIP_E2E=0 SLACK_BOT_TOKEN=dummy OPENAI_API_KEY=dummy uv run pytest tests/e2e/ -v --timeout=120

# ─── CI ─────────────────────────────────────────────────────────────────

# Full CI pipeline (matches GitHub Actions)
ci: fmt-check lint typecheck test
    @echo "✓ All CI checks passed"

# Pre-commit hooks
pre-commit:
    uv run pre-commit run --all-files --show-diff-on-failure

# ─── Run ────────────────────────────────────────────────────────────────

# Run API server (FastAPI)
api:
    uv run python scripts/run_api_server.py

# Run Dash UI
dash:
    uv run python scripts/run_dash.py

# Run multi-source pipeline
pipeline *ARGS:
    uv run python scripts/run_multi_source_pipeline.py {{ARGS}}

# Run pipeline scheduler
scheduler *ARGS:
    uv run python scripts/run_pipeline_scheduler.py {{ARGS}}

# ─── DB ─────────────────────────────────────────────────────────────────

# Run Alembic migrations
db-upgrade:
    uv run alembic upgrade head

# Create new migration
db-revision MESSAGE:
    uv run alembic revision --autogenerate -m "{{MESSAGE}}"

# ─── Docker ─────────────────────────────────────────────────────────────

# Build all containers
docker-build:
    docker compose build

# Start all services
docker-up:
    docker compose up -d

# Stop all services
docker-down:
    docker compose down

# View logs
docker-logs *ARGS:
    docker compose logs -f {{ARGS}}

# ─── Clean ──────────────────────────────────────────────────────────────

# Remove generated files
clean:
    rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete
    @echo "✓ Clean"
