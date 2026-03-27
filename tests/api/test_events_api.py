"""Tests for the FastAPI event endpoints.

These are integration tests that use the real repository (SQLite in-memory/temp).
"""

from typing import Any

from tests.factories import NEEDS_REVIEW_IDS, SEED_COUNTS


class TestHealthEndpoint:
    """Health check endpoint tests."""

    def test_health_returns_ok(self, api_client: Any) -> None:
        response = api_client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "timestamp" in data

    def test_health_has_version(self, api_client: Any) -> None:
        response = api_client.get("/api/v1/health")
        data = response.json()
        assert "version" in data


class TestEventsEndpoint:
    """Event list/get endpoint tests."""

    def test_list_events_returns_list(self, api_client: Any) -> None:
        response = api_client.get("/api/v1/events")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_list_events_with_filter(self, api_client: Any) -> None:
        response = api_client.get(
            "/api/v1/events", params={"review_status": "needs_review"}
        )
        assert response.status_code == 200

    def test_get_nonexistent_event_returns_404(self, api_client: Any) -> None:
        response = api_client.get("/api/v1/events/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404


class TestReviewStatsEndpoint:
    """Review stats endpoint tests."""

    def test_stats_returns_counts(self, api_client: Any) -> None:
        response = api_client.get("/api/v1/events/stats")
        assert response.status_code == 200
        data = response.json()
        # Should have at least needs_review key
        assert "needs_review" in data


class TestTimelineEndpoint:
    """Timeline endpoint tests."""

    def test_timeline_returns_entries(self, api_client: Any) -> None:
        response = api_client.get("/api/v1/events/timeline")
        assert response.status_code == 200
        data = response.json()
        assert "entries" in data
        assert isinstance(data["entries"], list)

    def test_timeline_with_days_param(self, api_client: Any) -> None:
        response = api_client.get("/api/v1/events/timeline", params={"days": 7})
        assert response.status_code == 200


class TestOpenAPISchema:
    """OpenAPI schema availability."""

    def test_openapi_schema_available(self, api_client: Any) -> None:
        response = api_client.get("/api/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert "paths" in schema
        assert "/api/v1/events" in schema["paths"]

    def test_docs_page_available(self, api_client: Any) -> None:
        response = api_client.get("/api/docs")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Tests with seeded data — assert on real counts, fields, and workflows
# ---------------------------------------------------------------------------


class TestEventsWithSeedData:
    """Integration tests using the 15 deterministic seed events from tests/factories.py.

    All tests use the `seeded_api_client` fixture which points at a real
    SQLiteRepository pre-populated with SEED_EVENTS.
    """

    def test_list_events_returns_all_seeded(self, seeded_api_client: Any) -> None:
        response = seeded_api_client.get("/api/v1/events", params={"limit": 200})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == SEED_COUNTS["total"]
        assert len(data["items"]) == SEED_COUNTS["total"]

    def test_list_events_filter_needs_review(self, seeded_api_client: Any) -> None:
        response = seeded_api_client.get(
            "/api/v1/events", params={"review_status": "needs_review", "limit": 200}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == SEED_COUNTS["needs_review"]
        assert all(
            item["review_status"] == "needs_review" for item in data["items"]
        )

    def test_list_events_filter_published(self, seeded_api_client: Any) -> None:
        response = seeded_api_client.get(
            "/api/v1/events", params={"review_status": "published", "limit": 200}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == SEED_COUNTS["published"]

    def test_stats_shows_all_status_counts(self, seeded_api_client: Any) -> None:
        response = seeded_api_client.get("/api/v1/events/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["needs_review"] == SEED_COUNTS["needs_review"]
        assert data["approved"] == SEED_COUNTS["approved"]
        assert data["published"] == SEED_COUNTS["published"]
        assert data["rejected"] == SEED_COUNTS["rejected"]
        assert data["archived"] == SEED_COUNTS["archived"]

    def test_timeline_returns_entries_with_data(self, seeded_api_client: Any) -> None:
        # Use a 90-day window to capture all March 2026 seed events
        response = seeded_api_client.get(
            "/api/v1/events/timeline", params={"days": 90}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] > 0
        assert len(data["entries"]) > 0
        entry = data["entries"][0]
        assert "title" in entry
        assert "start" in entry
        assert "category" in entry
        assert "review_status" in entry

    def test_get_event_by_id_returns_full_fields(
        self, seeded_api_client: Any
    ) -> None:
        event_id = NEEDS_REVIEW_IDS[0]
        response = seeded_api_client.get(f"/api/v1/events/{event_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["event_id"] == event_id
        assert data["review_status"] == "needs_review"
        assert data["summary"] != ""
        assert data["confidence"] > 0

    def test_approve_then_publish_workflow(self, seeded_api_client: Any) -> None:
        event_id = NEEDS_REVIEW_IDS[0]

        # Step 1: approve
        r1 = seeded_api_client.post(
            f"/api/v1/events/{event_id}/review",
            json={"action": "approve", "actor": "test-user"},
        )
        assert r1.status_code == 200
        assert r1.json()["status"] == "ok"

        # Verify status changed
        r_check = seeded_api_client.get(f"/api/v1/events/{event_id}")
        assert r_check.json()["review_status"] == "approved"

        # Step 2: publish
        r2 = seeded_api_client.post(
            f"/api/v1/events/{event_id}/review",
            json={"action": "publish", "actor": "test-user"},
        )
        assert r2.status_code == 200
        assert r2.json()["status"] == "ok"

        # Verify final status
        r_final = seeded_api_client.get(f"/api/v1/events/{event_id}")
        assert r_final.json()["review_status"] == "published"

    def test_reject_event_changes_status(self, seeded_api_client: Any) -> None:
        event_id = NEEDS_REVIEW_IDS[1]

        r = seeded_api_client.post(
            f"/api/v1/events/{event_id}/review",
            json={"action": "reject", "actor": "test-user", "note": "low quality"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

        r_check = seeded_api_client.get(f"/api/v1/events/{event_id}")
        assert r_check.json()["review_status"] == "rejected"

    def test_patch_event_updates_summary(self, seeded_api_client: Any) -> None:
        event_id = NEEDS_REVIEW_IDS[2]
        new_summary = "Updated summary via PATCH endpoint test."

        r = seeded_api_client.patch(
            f"/api/v1/events/{event_id}",
            json={"actor": "test-user", "updates": {"summary": new_summary}},
        )
        assert r.status_code == 200

        r_check = seeded_api_client.get(f"/api/v1/events/{event_id}")
        assert r_check.json()["summary"] == new_summary

    def test_audit_log_after_review_action(self, seeded_api_client: Any) -> None:
        event_id = NEEDS_REVIEW_IDS[3]

        seeded_api_client.post(
            f"/api/v1/events/{event_id}/review",
            json={"action": "approve", "actor": "auditor"},
        )

        r = seeded_api_client.get(f"/api/v1/events/{event_id}/audit")
        assert r.status_code == 200
        entries = r.json()
        assert len(entries) >= 1
        assert any(e["actor"] == "auditor" for e in entries)
