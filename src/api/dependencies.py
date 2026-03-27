"""Dependency injection for FastAPI routes.

Provides repository, settings, and use-case instances to route handlers.
"""

from functools import lru_cache

from fastapi import Depends

from src.adapters.repository_factory import create_repository
from src.config.settings import Settings, get_settings
from src.domain.protocols import RepositoryProtocol
from src.use_cases.review_events import ReviewEventsUseCase


@lru_cache(maxsize=1)
def get_app_settings() -> Settings:
    """Cached settings singleton."""
    return get_settings()


@lru_cache(maxsize=1)
def get_repo() -> RepositoryProtocol:
    """Cached repository singleton."""
    return create_repository(get_app_settings())


def get_review_use_case(
    repo: RepositoryProtocol = Depends(get_repo),
) -> ReviewEventsUseCase:
    """Construct ReviewEventsUseCase with DI-provided repo.

    Using Depends(get_repo) ensures dependency_overrides in tests will
    correctly substitute the repository without bypassing the override chain.
    """
    return ReviewEventsUseCase(repo=repo)
