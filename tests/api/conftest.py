"""API integration test fixtures."""

import os
from typing import Any

import pytest

# Set required env vars before importing app code
os.environ.setdefault("SLACK_BOT_TOKEN", "test-token")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("REVIEW_API_TOKEN", "test-review-token")


@pytest.fixture
def api_client() -> Any:
    """Create a FastAPI TestClient with fresh DI state."""
    from fastapi.testclient import TestClient

    from src.api.app import create_app
    from src.api.dependencies import get_app_settings, get_repo

    # Clear LRU caches to avoid cross-test pollution
    get_app_settings.cache_clear()
    get_repo.cache_clear()

    app = create_app()
    with TestClient(app) as client:
        yield client

    get_app_settings.cache_clear()
    get_repo.cache_clear()


@pytest.fixture
def seeded_api_client(seeded_db: tuple[str, Any]) -> Any:
    """FastAPI TestClient whose repository points at the seeded SQLite DB.

    Overrides the DI-provided repo with a real SQLiteRepository backed by the
    seed data, so endpoint tests can assert on actual counts and fields.
    """
    from fastapi.testclient import TestClient

    from src.adapters.sqlite_repository import SQLiteRepository
    from src.api.app import create_app
    from src.api.dependencies import get_app_settings, get_repo

    db_path, _ = seeded_db

    get_app_settings.cache_clear()
    get_repo.cache_clear()

    seeded_repo = SQLiteRepository(db_path=db_path)

    app = create_app()
    app.dependency_overrides[get_repo] = lambda: seeded_repo

    with TestClient(
        app,
        headers={"X-Review-Api-Token": os.environ["REVIEW_API_TOKEN"]},
    ) as client:
        yield client

    app.dependency_overrides.pop(get_repo, None)
    get_app_settings.cache_clear()
    get_repo.cache_clear()

    try:
        seeded_repo.close()
    except Exception:
        pass


@pytest.fixture
def seeded_api_client_no_auth(seeded_db: tuple[str, Any]) -> Any:
    """FastAPI TestClient whose repository points at the seeded DB without auth."""
    from fastapi.testclient import TestClient

    from src.adapters.sqlite_repository import SQLiteRepository
    from src.api.app import create_app
    from src.api.dependencies import get_app_settings, get_repo

    db_path, _ = seeded_db

    get_app_settings.cache_clear()
    get_repo.cache_clear()

    seeded_repo = SQLiteRepository(db_path=db_path)

    app = create_app()
    app.dependency_overrides[get_repo] = lambda: seeded_repo

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.pop(get_repo, None)
    get_app_settings.cache_clear()
    get_repo.cache_clear()

    try:
        seeded_repo.close()
    except Exception:
        pass
