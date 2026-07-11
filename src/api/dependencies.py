"""Dependency injection for FastAPI routes.

Provides repository, settings, and use-case instances to route handlers.
"""

from functools import lru_cache
from secrets import compare_digest

from fastapi import Depends, Header, HTTPException, status

from src.adapters.llm_client import LLMClient
from src.adapters.repository_factory import create_repository
from src.config.settings import Settings, get_settings
from src.domain.protocols import RepositoryProtocol
from src.services.object_registry import ObjectRegistry
from src.use_cases.review_events import ReviewEventsUseCase


@lru_cache(maxsize=1)
def get_app_settings() -> Settings:
    """Cached settings singleton."""
    return get_settings()


@lru_cache(maxsize=1)
def get_repo() -> RepositoryProtocol:
    """Cached repository singleton."""
    return create_repository(get_app_settings())


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    """Cached LLM client singleton (used for query embeddings)."""
    settings = get_app_settings()
    return LLMClient(
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.llm_model,
        timeout=settings.llm_timeout_seconds,
    )


@lru_cache(maxsize=1)
def get_object_registry() -> ObjectRegistry:
    """Cached object registry singleton (hot-reloads the YAML by mtime)."""
    return ObjectRegistry(get_app_settings().object_registry_path)


def get_review_use_case(
    repo: RepositoryProtocol = Depends(get_repo),
) -> ReviewEventsUseCase:
    """Construct ReviewEventsUseCase with DI-provided repo.

    Using Depends(get_repo) ensures dependency_overrides in tests will
    correctly substitute the repository without bypassing the override chain.
    """
    return ReviewEventsUseCase(repo=repo)


def require_write_access(
    settings: Settings = Depends(get_app_settings),
    review_api_token: str | None = Header(default=None, alias="X-Review-Api-Token"),
) -> None:
    """Protect mutating routes with a shared API token."""
    configured_token = settings.review_api_token
    if configured_token is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Write API is disabled until REVIEW_API_TOKEN is configured.",
        )

    if review_api_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing review API token.",
        )

    if not compare_digest(review_api_token, configured_token.get_secret_value()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid review API token.",
        )
