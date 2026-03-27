"""E2E smoke + feature tests for the Dash UI.

All tests run against the seeded DB (15 deterministic events, March 2026).
Servers are launched once per session on ports 18000 (API) / 18050 (Dash).

Run with:
    SKIP_E2E=0 uv run pytest tests/e2e/ -v
"""

from __future__ import annotations

import os
import re
from typing import Any

import pytest
from playwright.sync_api import Page, expect

pytestmark = [
    pytest.mark.skipif(
        os.environ.get("SKIP_E2E", "1") == "1",
        reason="E2E tests disabled (set SKIP_E2E=0 to enable)",
    ),
    pytest.mark.timeout(120),
]

# DataTable row selector — Dash renders rows inside .dash-spreadsheet-inner
_TABLE_ROWS = ".dash-spreadsheet-inner table tbody tr"
# How long to wait for table rows to appear (JS rendering takes a moment)
_TABLE_WAIT_JS = (
    f"() => document.querySelectorAll('{_TABLE_ROWS}').length > 0"
)
# Base selector wait — generous to handle concurrent-request contention
_SEL_WAIT = 30_000


class TestDashSmokeWithSeedData:
    """Smoke + feature tests using the 15-event seeded database."""

    # ------------------------------------------------------------------
    # Page loading
    # ------------------------------------------------------------------

    def test_review_page_has_events(
        self, page: Page, dash_url: str, _start_servers: Any
    ) -> None:
        """Review queue table must contain rows from the seeded DB."""
        page.goto(f"{dash_url}/review")
        page.wait_for_selector("#review-table", timeout=_SEL_WAIT)
        page.wait_for_function(_TABLE_WAIT_JS, timeout=_SEL_WAIT)

        rows = page.locator(_TABLE_ROWS)
        assert rows.count() >= 1, "Expected at least one row in the review table"
        assert page.title() == "Event Manager"

    def test_timeline_shows_bars(
        self, page: Page, dash_url: str, _start_servers: Any
    ) -> None:
        """Timeline chart must render event bars for the seeded events."""
        page.goto(f"{dash_url}/timeline")
        page.wait_for_selector("#timeline-chart", timeout=_SEL_WAIT)

        # Plotly renders bars as <g class="trace bars"> inside .barlayer
        # Use a generous timeout since Plotly loads its bundle lazily
        page.wait_for_selector(
            ".js-plotly-plot .barlayer .trace", timeout=20_000
        )
        trace_count = page.locator(".js-plotly-plot .barlayer .trace").count()
        assert trace_count > 0, "Expected timeline chart to have bar traces"

        # Also confirm the empty-state text is NOT present
        chart_html = page.inner_html("#timeline-chart")
        assert "No events in selected range" not in chart_html

    def test_stats_badges_show_correct_counts(
        self, page: Page, dash_url: str, _start_servers: Any
    ) -> None:
        """Stats badges must display non-zero counts matching the seed data."""
        page.goto(f"{dash_url}/review")
        page.wait_for_selector("#review-stats-badges", timeout=_SEL_WAIT)
        # Wait until Dash has populated the badges (initial n_intervals=0 fires callback)
        page.wait_for_function(
            "() => document.querySelector('#review-stats-badges').innerText.includes('Needs Review')",
            timeout=_SEL_WAIT,
        )

        text = page.inner_text("#review-stats-badges")
        # Needs Review: 5 / Approved: 3 / Published: 3
        nr_match = re.search(r"Needs Review[:\s]+(\d+)", text)
        ap_match = re.search(r"Approved[:\s]+(\d+)", text)
        pub_match = re.search(r"Published[:\s]+(\d+)", text)
        assert nr_match, f"'Needs Review' count not found in badges text: {text!r}"
        assert int(nr_match.group(1)) == 5
        assert ap_match and int(ap_match.group(1)) == 3
        assert pub_match and int(pub_match.group(1)) == 3

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def test_navigation_review_to_timeline_and_back(
        self, page: Page, dash_url: str, _start_servers: Any
    ) -> None:
        """Clicking nav links must switch between pages without full reload."""
        page.goto(dash_url)
        page.wait_for_selector("#review-table", timeout=_SEL_WAIT)

        # Navigate to Timeline
        page.click("a[href='/timeline']")
        page.wait_for_selector("#timeline-chart", timeout=_SEL_WAIT)

        # Navigate back to Review Queue
        page.click("a[href='/review']")
        page.wait_for_selector("#review-table", timeout=_SEL_WAIT)

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def test_filter_by_published_shows_three_rows(
        self, page: Page, dash_url: str, _start_servers: Any
    ) -> None:
        """'Published' filter button must show exactly 3 seed events."""
        page.goto(f"{dash_url}/review")
        page.wait_for_selector("#review-table", timeout=_SEL_WAIT)
        page.wait_for_function(_TABLE_WAIT_JS, timeout=_SEL_WAIT)

        # Capture the Dash callback response to verify data returned
        with page.expect_response(
            lambda r: "/_dash-update-component" in r.url,
            timeout=_SEL_WAIT,
        ) as resp_info:
            page.click("#filter-published")

        resp_body = resp_info.value.json()

        # Extract table data from the Dash response payload
        try:
            table_data = resp_body["response"]["review-table"]["data"]
        except KeyError:
            pytest.fail(
                f"Unexpected Dash response structure; keys: {list(resp_body.get('response', {}).keys())}"
            )

        assert len(table_data) == 3, (
            f"Dash callback returned {len(table_data)} items, expected 3"
        )
        assert all(
            row.get("review_status") == "published" for row in table_data
        ), "Not all returned rows have review_status=published"

    # ------------------------------------------------------------------
    # Review actions
    # ------------------------------------------------------------------

    def test_approve_event_flow(
        self, page: Page, dash_url: str, _start_servers: Any
    ) -> None:
        """Selecting a needs-review row and clicking Approve must show success."""
        page.goto(f"{dash_url}/review")
        page.wait_for_selector("#review-table", timeout=_SEL_WAIT)
        page.wait_for_function(_TABLE_WAIT_JS, timeout=_SEL_WAIT)

        # Click the radio button in the first row to select it
        # (Dash DataTable row_selectable="single" renders radio inputs)
        page.locator("input[type='radio']").first.click()

        # Action buttons enable after row selection
        page.wait_for_selector("#btn-approve:not([disabled])", timeout=10_000)
        page.click("#btn-approve")

        # Success alert should appear
        page.wait_for_selector("#action-result .alert", timeout=10_000)
        alert_text = page.inner_text("#action-result .alert")
        assert "approved" in alert_text.lower(), (
            f"Expected success message for approve, got: {alert_text!r}"
        )

    def test_reject_event_flow(
        self, page: Page, dash_url: str, _start_servers: Any
    ) -> None:
        """Selecting a different needs-review row and clicking Reject must show success."""
        page.goto(f"{dash_url}/review")
        page.wait_for_selector("#review-table", timeout=_SEL_WAIT)
        page.wait_for_function(_TABLE_WAIT_JS, timeout=_SEL_WAIT)

        # Use the second radio button to avoid collision with the approve test
        page.locator("input[type='radio']").nth(1).click()

        page.wait_for_selector("#btn-reject:not([disabled])", timeout=10_000)
        page.click("#btn-reject")

        page.wait_for_selector("#action-result .alert", timeout=10_000)
        alert_text = page.inner_text("#action-result .alert")
        assert "reject" in alert_text.lower(), (
            f"Expected success message for reject, got: {alert_text!r}"
        )
