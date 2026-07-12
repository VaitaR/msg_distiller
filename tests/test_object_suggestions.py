"""Tests for WS4: object registry suggestions queue + YAML approve flow."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml

from src.domain.protocols import RepositoryProtocol
from src.services.object_registry import ObjectRegistry
from src.use_cases.extract_events import _record_unmatched_object_suggestions

# ---------------------------------------------------------------------------
# Repository: suggestions queue
# ---------------------------------------------------------------------------


def test_record_suggestion_upserts_and_increments(repo: RepositoryProtocol) -> None:
    repo.record_object_suggestion("New Service", "event-1")
    repo.record_object_suggestion("new service ", "event-2")
    repo.record_object_suggestion("NEW SERVICE", "event-2")

    items = repo.list_object_suggestions(status="pending")
    assert len(items) == 1
    item = items[0]
    assert item["name_normalized"] == "new service"
    assert item["name_raw_sample"] == "New Service"
    assert item["occurrences"] == 3
    assert item["sample_event_ids"] == ["event-1", "event-2"]
    assert item["status"] == "pending"


def test_sample_event_ids_capped_at_five(repo: RepositoryProtocol) -> None:
    for n in range(8):
        repo.record_object_suggestion("Busy Object", f"event-{n}")

    item = repo.list_object_suggestions(status="pending")[0]
    assert item["occurrences"] == 8
    assert len(item["sample_event_ids"]) == 5


def test_list_orders_by_occurrences_desc(repo: RepositoryProtocol) -> None:
    repo.record_object_suggestion("Rare", "e1")
    for n in range(3):
        repo.record_object_suggestion("Frequent", f"e{n}")

    items = repo.list_object_suggestions(status="pending")
    assert [i["name_normalized"] for i in items] == ["frequent", "rare"]


def test_resolve_suggestion_changes_status(repo: RepositoryProtocol) -> None:
    repo.record_object_suggestion("Approve Me", "e1")
    suggestion_id = repo.list_object_suggestions(status="pending")[0]["id"]

    assert repo.resolve_object_suggestion(
        suggestion_id, "approved", object_id="wallet.thing"
    )
    assert repo.list_object_suggestions(status="pending") == []
    approved = repo.list_object_suggestions(status="approved")
    assert approved[0]["approved_object_id"] == "wallet.thing"

    assert not repo.resolve_object_suggestion(99999, "rejected")


def test_record_suggestion_ignores_empty_name(repo: RepositoryProtocol) -> None:
    repo.record_object_suggestion("   ", "e1")
    assert repo.list_object_suggestions(status="pending") == []


# ---------------------------------------------------------------------------
# Extraction write path
# ---------------------------------------------------------------------------


def test_unmatched_events_recorded_matched_skipped() -> None:
    unmatched = MagicMock(object_id=None, object_name_raw="Mystery Box")
    unmatched.event_id = "id-1"
    matched = MagicMock(object_id="wallet.stocks", object_name_raw="Stocks")
    nameless = MagicMock(object_id=None, object_name_raw="")
    repository = MagicMock()

    _record_unmatched_object_suggestions(
        events=[unmatched, matched, nameless],
        repository=repository,
        correlation_id=None,
    )

    repository.record_object_suggestion.assert_called_once_with("Mystery Box", "id-1")


def test_suggestion_failure_does_not_raise() -> None:
    event = MagicMock(object_id=None, object_name_raw="Mystery Box")
    repository = MagicMock()
    repository.record_object_suggestion.side_effect = RuntimeError("db down")

    _record_unmatched_object_suggestions(
        events=[event], repository=repository, correlation_id=None
    )  # Must swallow the error


# ---------------------------------------------------------------------------
# Registry: add_synonym + hot reload
# ---------------------------------------------------------------------------

REGISTRY_TEXT = """\
# Canonical objects
objects:
  wallet.stocks:
    - Stocks & ETFs
    - Stock trading
  # data systems
  data.clickhouse:
    - ClickHouse
"""


@pytest.fixture
def registry_file(tmp_path: Path) -> Path:
    path = tmp_path / "registry.yaml"
    path.write_text(REGISTRY_TEXT, encoding="utf-8")
    return path


def test_add_synonym_appends_to_existing_block(registry_file: Path) -> None:
    registry = ObjectRegistry(registry_file)
    registry.add_synonym("wallet.stocks", "Equity wallet")

    text = registry_file.read_text(encoding="utf-8")
    assert "# Canonical objects" in text  # Comments survive
    assert "# data systems" in text
    data = yaml.safe_load(text)
    assert data["objects"]["wallet.stocks"] == [
        "Stocks & ETFs",
        "Stock trading",
        "Equity wallet",
    ]
    assert registry.canonicalize_object("equity wallet") == "wallet.stocks"


def test_add_synonym_creates_new_object_block(registry_file: Path) -> None:
    registry = ObjectRegistry(registry_file)
    registry.add_synonym("infra.k8s", "Kubernetes cluster")

    data = yaml.safe_load(registry_file.read_text(encoding="utf-8"))
    assert data["objects"]["infra.k8s"] == ["Kubernetes cluster"]
    assert registry.canonicalize_object("kubernetes cluster") == "infra.k8s"


def test_add_synonym_noop_when_already_present(registry_file: Path) -> None:
    registry = ObjectRegistry(registry_file)
    before = registry_file.read_text(encoding="utf-8")
    registry.add_synonym("wallet.stocks", "stocks & etfs")
    assert registry_file.read_text(encoding="utf-8") == before


def test_add_synonym_rejects_empty_args(registry_file: Path) -> None:
    registry = ObjectRegistry(registry_file)
    with pytest.raises(ValueError, match="non-empty"):
        registry.add_synonym("", "synonym")
    with pytest.raises(ValueError, match="non-empty"):
        registry.add_synonym("wallet.stocks", "   ")


def test_add_synonym_rolls_back_on_invalid_yaml(
    registry_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = ObjectRegistry(registry_file)
    original = registry_file.read_text(encoding="utf-8")

    monkeypatch.setattr(
        "src.services.object_registry.yaml.safe_load",
        MagicMock(side_effect=yaml.YAMLError("broken")),
    )
    with pytest.raises(ValueError, match="Failed to add synonym"):
        registry.add_synonym("wallet.stocks", "Broken entry")

    monkeypatch.undo()
    assert registry_file.read_text(encoding="utf-8") == original


def test_registry_hot_reloads_on_mtime_change(registry_file: Path) -> None:
    registry = ObjectRegistry(registry_file)
    assert registry.canonicalize_object("brand new thing") is None

    updated = REGISTRY_TEXT + "  new.object:\n    - Brand new thing\n"
    registry_file.write_text(updated, encoding="utf-8")
    os.utime(
        registry_file,
        (registry_file.stat().st_atime, registry_file.stat().st_mtime + 2),
    )

    assert registry.canonicalize_object("brand new thing") == "new.object"


# ---------------------------------------------------------------------------
# API flow
# ---------------------------------------------------------------------------


@pytest.fixture
def registry_api_client(repo: RepositoryProtocol, registry_file: Path) -> Any:
    from fastapi.testclient import TestClient

    from src.api.app import create_app
    from src.api.dependencies import (
        get_app_settings,
        get_object_registry,
        get_repo,
    )

    os.environ.setdefault("REVIEW_API_TOKEN", "test-review-token")
    get_app_settings.cache_clear()
    get_repo.cache_clear()
    get_object_registry.cache_clear()

    registry = ObjectRegistry(registry_file)
    app = create_app()
    app.dependency_overrides[get_repo] = lambda: repo
    app.dependency_overrides[get_object_registry] = lambda: registry

    with TestClient(
        app, headers={"X-Review-Api-Token": os.environ["REVIEW_API_TOKEN"]}
    ) as client:
        yield client, registry_file

    app.dependency_overrides.clear()
    get_app_settings.cache_clear()
    get_repo.cache_clear()
    get_object_registry.cache_clear()


def test_api_approve_writes_synonym_and_resolves(
    registry_api_client: Any, repo: RepositoryProtocol
) -> None:
    client, registry_file = registry_api_client
    repo.record_object_suggestion("Payment Gateway", "e1")
    suggestion_id = client.get("/api/v1/registry/suggestions").json()["items"][0]["id"]

    resp = client.post(
        f"/api/v1/registry/suggestions/{suggestion_id}/approve",
        json={"object_id": "wallet.payments"},
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"
    assert resp.json()["approved_object_id"] == "wallet.payments"
    data = yaml.safe_load(registry_file.read_text(encoding="utf-8"))
    assert "Payment Gateway" in data["objects"]["wallet.payments"]
    assert client.get("/api/v1/registry/suggestions").json()["total"] == 0


def test_api_reject_leaves_registry_untouched(
    registry_api_client: Any, repo: RepositoryProtocol
) -> None:
    client, registry_file = registry_api_client
    before = registry_file.read_text(encoding="utf-8")
    repo.record_object_suggestion("Noise", "e1")
    suggestion_id = client.get("/api/v1/registry/suggestions").json()["items"][0]["id"]

    resp = client.post(f"/api/v1/registry/suggestions/{suggestion_id}/reject")

    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"
    assert registry_file.read_text(encoding="utf-8") == before


def test_api_approve_unknown_suggestion_404(registry_api_client: Any) -> None:
    client, _ = registry_api_client
    resp = client.post(
        "/api/v1/registry/suggestions/424242/approve",
        json={"object_id": "wallet.payments"},
    )
    assert resp.status_code == 404


def test_api_write_requires_token(
    repo: RepositoryProtocol, registry_file: Path
) -> None:
    from fastapi.testclient import TestClient

    from src.api.app import create_app
    from src.api.dependencies import get_app_settings, get_repo

    get_app_settings.cache_clear()
    get_repo.cache_clear()
    app = create_app()
    app.dependency_overrides[get_repo] = lambda: repo

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/registry/suggestions/1/approve",
            json={"object_id": "wallet.payments"},
        )

    app.dependency_overrides.clear()
    get_app_settings.cache_clear()
    get_repo.cache_clear()
    assert resp.status_code in (401, 503)
