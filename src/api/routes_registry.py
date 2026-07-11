"""Object registry API routes: suggestion queue for unmatched object names.

Approving a suggestion writes a synonym into the registry YAML (picked up
by mtime hot-reload) and resolves the suggestion in the database.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.dependencies import get_object_registry, get_repo, require_write_access
from src.api.schemas import (
    ApproveSuggestionRequest,
    ObjectSuggestionListResponse,
    ObjectSuggestionResponse,
)
from src.domain.protocols import RepositoryProtocol
from src.services.object_registry import ObjectRegistry

router = APIRouter(prefix="/api/v1/registry", tags=["registry"])


@router.get("/suggestions", response_model=ObjectSuggestionListResponse)
def list_suggestions(
    status: str = Query(default="pending", pattern="^(pending|approved|rejected)$"),
    repo: RepositoryProtocol = Depends(get_repo),
) -> ObjectSuggestionListResponse:
    """List object suggestions, most frequent first."""
    items = repo.list_object_suggestions(status=status)
    return ObjectSuggestionListResponse(
        items=[ObjectSuggestionResponse(**item) for item in items],
        total=len(items),
    )


@router.post(
    "/suggestions/{suggestion_id}/approve",
    response_model=ObjectSuggestionResponse,
    dependencies=[Depends(require_write_access)],
)
def approve_suggestion(
    suggestion_id: int,
    payload: ApproveSuggestionRequest,
    repo: RepositoryProtocol = Depends(get_repo),
    registry: ObjectRegistry = Depends(get_object_registry),
) -> ObjectSuggestionResponse:
    """Approve a suggestion: add the synonym to the registry YAML."""
    suggestion = _get_pending_suggestion(repo, suggestion_id)

    synonym = payload.synonym or suggestion["name_raw_sample"]
    try:
        registry.add_synonym(payload.object_id, synonym)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    repo.resolve_object_suggestion(
        suggestion_id, "approved", object_id=payload.object_id
    )
    return _reload_suggestion(repo, suggestion_id, "approved")


@router.post(
    "/suggestions/{suggestion_id}/reject",
    response_model=ObjectSuggestionResponse,
    dependencies=[Depends(require_write_access)],
)
def reject_suggestion(
    suggestion_id: int,
    repo: RepositoryProtocol = Depends(get_repo),
) -> ObjectSuggestionResponse:
    """Reject a suggestion without touching the registry."""
    _get_pending_suggestion(repo, suggestion_id)
    repo.resolve_object_suggestion(suggestion_id, "rejected")
    return _reload_suggestion(repo, suggestion_id, "rejected")


def _get_pending_suggestion(
    repo: RepositoryProtocol, suggestion_id: int
) -> dict:
    for item in repo.list_object_suggestions(status="pending"):
        if item["id"] == suggestion_id:
            return item
    raise HTTPException(status_code=404, detail="Pending suggestion not found")


def _reload_suggestion(
    repo: RepositoryProtocol, suggestion_id: int, status: str
) -> ObjectSuggestionResponse:
    for item in repo.list_object_suggestions(status=status):
        if item["id"] == suggestion_id:
            return ObjectSuggestionResponse(**item)
    raise HTTPException(status_code=500, detail="Suggestion state inconsistent")
