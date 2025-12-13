.PHONY: help install install-pip sync sync-dev lock lock-check format lint typecheck test ci clean makefile

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m # No Color
UV_PYTHON ?= python3.11

help: ## Show this help message
	@echo "$(BLUE)Available targets:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-15s$(NC) %s\n", $$1, $$2}'

install: ## Install dependencies (uv, recommended)
	@make sync-dev

install-pip: ## Install dependencies (legacy pip)
	@echo "$(BLUE)Installing dependencies with pip (legacy)...$(NC)"
	pip install -r requirements.txt

sync: ## Sync runtime deps from uv.lock (frozen)
	@echo "$(BLUE)Syncing runtime dependencies (uv, frozen)...$(NC)"
	@uv sync --python "$(UV_PYTHON)" --frozen --no-dev --no-install-project && echo "$(GREEN)✓ Sync complete$(NC)" || (echo "$(RED)✗ Sync failed$(NC)" && exit 1)

sync-dev: ## Sync dev deps from uv.lock (frozen)
	@echo "$(BLUE)Syncing development dependencies (uv, frozen)...$(NC)"
	@uv sync --python "$(UV_PYTHON)" --frozen --no-install-project && echo "$(GREEN)✓ Sync complete$(NC)" || (echo "$(RED)✗ Sync failed$(NC)" && exit 1)

lock: ## Update uv.lock from pyproject.toml
	@echo "$(BLUE)Updating uv.lock...$(NC)"
	@uv lock --python "$(UV_PYTHON)" && echo "$(GREEN)✓ Lock updated$(NC)" || (echo "$(RED)✗ Lock update failed$(NC)" && exit 1)

lock-check: ## Check uv.lock is up-to-date
	@echo "$(BLUE)Checking uv.lock is up-to-date...$(NC)"
	@uv lock --check && echo "$(GREEN)✓ Lock is up-to-date$(NC)" || (echo "$(RED)✗ Lock is out-of-date$(NC)" && exit 1)

deps-check: ## Check dependency resolution (uv dry-run, matches CI)
	@echo "$(BLUE)Checking dependency resolution with uv...$(NC)"
	@if command -v uv >/dev/null 2>&1; then \
		uv lock --check >/dev/null && \
		echo "$(GREEN)✓ Dependency resolution OK$(NC)"; \
	else \
		echo "$(YELLOW)WARN: uv not found; skipping deps-check (CI uses uv)$(NC)"; \
	fi

format: ## Format code with ruff
	@echo "$(BLUE)Formatting code with ruff...$(NC)"
	uv run ruff format .
	@echo "$(GREEN)✓ Formatting complete$(NC)"

format-check: ## Check code formatting without modifying files
	@echo "$(BLUE)Checking code formatting...$(NC)"
	@uv run ruff format --check . && echo "$(GREEN)✓ Format check passed$(NC)" || (echo "$(RED)✗ Format check failed$(NC)" && exit 1)

lint: ## Run ruff linter
	@echo "$(BLUE)Running ruff linter...$(NC)"
	@uv run ruff check . && echo "$(GREEN)✓ Lint passed$(NC)" || (echo "$(RED)✗ Lint failed$(NC)" && exit 1)

lint-fix: ## Run ruff linter with auto-fix
	@echo "$(BLUE)Running ruff linter with auto-fix...$(NC)"
	uv run ruff check . --fix --unsafe-fixes
	@echo "$(GREEN)✓ Lint fixes applied$(NC)"

typecheck: ## Run mypy type checker (matches CI exactly)
	@echo "$(BLUE)Running mypy type checker...$(NC)"
	@uv run mypy src --config-file pyproject.toml && echo "$(GREEN)✓ Type check passed$(NC)" || (echo "$(RED)✗ Type check failed$(NC)" && exit 1)

test: ## Run tests with pytest (matches CI exactly)
	@echo "$(BLUE)Running tests...$(NC)"
	@SLACK_BOT_TOKEN=dummy OPENAI_API_KEY=dummy uv run python -m pytest -k "not (test_postgres_repository or telegram)" && echo "$(GREEN)✓ Tests passed$(NC)" || (echo "$(RED)✗ Tests failed$(NC)" && exit 1)

test-quick: ## Run tests without coverage
	@echo "$(BLUE)Running quick tests...$(NC)"
	@SLACK_BOT_TOKEN=dummy OPENAI_API_KEY=dummy uv run pytest -q --no-cov && echo "$(GREEN)✓ Tests passed$(NC)" || (echo "$(RED)✗ Tests failed$(NC)" && exit 1)

test-cov: ## Run tests with coverage report
	@echo "$(BLUE)Running tests with coverage...$(NC)"
	@SLACK_BOT_TOKEN=dummy OPENAI_API_KEY=dummy uv run pytest --cov=src --cov-report=term-missing --cov-report=html && echo "$(GREEN)✓ Tests passed with coverage$(NC)" || (echo "$(RED)✗ Tests failed$(NC)" && exit 1)

test-postgres: ## Run PostgreSQL tests (requires PostgreSQL running and TEST_POSTGRES=1)
	@echo "$(BLUE)Running PostgreSQL tests...$(NC)"
	@if [ -z "$$POSTGRES_PASSWORD" ]; then \
		echo "$(RED)✗ POSTGRES_PASSWORD not set$(NC)"; \
		echo "$(YELLOW)Set POSTGRES_PASSWORD and TEST_POSTGRES=1 to run PostgreSQL tests$(NC)"; \
		exit 1; \
	fi
	@if [ "$$TEST_POSTGRES" != "1" ]; then \
		echo "$(RED)✗ TEST_POSTGRES not set to 1$(NC)"; \
		echo "$(YELLOW)Set TEST_POSTGRES=1 to run PostgreSQL tests$(NC)"; \
		exit 1; \
	fi
	@SLACK_BOT_TOKEN=dummy OPENAI_API_KEY=dummy uv run pytest tests/test_postgres_repository.py -v && echo "$(GREEN)✓ PostgreSQL tests passed$(NC)" || (echo "$(RED)✗ PostgreSQL tests failed$(NC)" && exit 1)


clean: ## Clean up generated files
	@echo "$(BLUE)Cleaning up...$(NC)"
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf .ruff_cache
	rm -rf htmlcov
	rm -rf .coverage
	rm -rf **/__pycache__
	rm -rf **/*.pyc
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	@echo "$(GREEN)✓ Cleanup complete$(NC)"

pre-commit: ## Run pre-commit hooks (fastest feedback)
	@echo "$(BLUE)Running pre-commit hooks...$(NC)"
	@uv run pre-commit run --all-files --show-diff-on-failure && echo "$(GREEN)✓ Pre-commit checks passed!$(NC)" || (echo "$(RED)✗ Pre-commit failed$(NC)" && exit 1)

pre-commit-install: ## Install pre-commit hooks
	@echo "$(BLUE)Installing pre-commit hooks...$(NC)"
	@uv run pre-commit install && echo "$(GREEN)✓ Pre-commit hooks installed$(NC)"

pre-push: ## Run pre-push checks (matches CI exactly)
	@echo "$(BLUE)Running pre-push checks...$(NC)"
	@make ci && echo "$(GREEN)✓ Pre-push checks passed! Safe to push.$(NC)"

ci: ## Run all CI checks (format, lint, typecheck, test) - matches GitHub Actions
	@echo "$(BLUE)Running CI pipeline...$(NC)"
	@make format-check && make lint && make typecheck && make test && echo "$(GREEN)✓ All CI checks passed!$(NC)"

makefile: ## Run all linters and tests (alias for ci)
	@$(MAKE) ci

ci-local: ## Run CI checks locally (same as GitHub Actions)
	@echo "$(BLUE)===========================================$(NC)"
	@echo "$(BLUE)   Running CI Pipeline (Local)$(NC)"
	@echo "$(BLUE)===========================================$(NC)"
	@echo ""
	@echo "$(YELLOW)Step 0/7: Lock Check$(NC)"
	@make lock-check
	@echo ""
	@echo "$(YELLOW)Step 1/7: Sync Dependencies (frozen)$(NC)"
	@make sync-dev
	@echo ""
	@echo "$(YELLOW)Step 2/7: Pre-commit (auto-fix)$(NC)"
	@make pre-commit
	@echo ""
	@echo "$(YELLOW)Step 3/7: Format Check$(NC)"
	@make format-check
	@echo ""
	@echo "$(YELLOW)Step 4/7: Lint$(NC)"
	@make lint
	@echo ""
	@echo "$(YELLOW)Step 5/7: Type Check$(NC)"
	@make typecheck
	@echo ""
	@echo "$(YELLOW)Step 6/7: Tests$(NC)"
	@make test
	@echo ""
	@echo "$(GREEN)===========================================$(NC)"
	@echo "$(GREEN)   ✓ CI Pipeline Passed!$(NC)"
	@echo "$(GREEN)===========================================$(NC)"

dev-setup: ## Complete development environment setup
	@echo "$(BLUE)Setting up development environment...$(NC)"
	@make sync-dev
	@make pre-commit-install
	@echo "$(GREEN)✓ Development environment ready!$(NC)"
	@echo "$(YELLOW)Quick commands:$(NC)"
	@echo "  make pre-commit    # Fast feedback"
	@echo "  make ci-local      # Full CI check"
	@echo "  make pre-push      # Before pushing"
