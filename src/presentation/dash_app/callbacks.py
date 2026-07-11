"""Dash callbacks — all interactivity logic.

Fetches data from API backend via httpx, renders into layout components.
"""

import os
from datetime import UTC, datetime
from typing import Any

import dash
import dash_bootstrap_components as dbc
import httpx
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Input, Output, State, callback_context, html, no_update

from src.presentation.dash_app.layout_review import review_layout
from src.presentation.dash_app.layout_timeline import CATEGORY_COLORS, timeline_layout

# Timeout for API calls
API_TIMEOUT = 10.0
REVIEW_API_TOKEN = os.getenv("REVIEW_API_TOKEN", "")


def _request_headers(*, include_write_token: bool = False) -> dict[str, str] | None:
    headers: dict[str, str] = {}
    if include_write_token and REVIEW_API_TOKEN:
        headers["X-Review-Api-Token"] = REVIEW_API_TOKEN
    return headers or None


def _api_get(base: str, path: str, params: dict[str, Any] | None = None) -> Any:
    """Make a GET request to the API backend."""
    try:
        r = httpx.get(
            f"{base}{path}",
            params=params,
            headers=_request_headers(),
            timeout=API_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError:
        return None


def _api_post(base: str, path: str, json: dict[str, Any]) -> Any:
    """Make a POST request to the API backend."""
    try:
        r = httpx.post(
            f"{base}{path}",
            json=json,
            headers=_request_headers(include_write_token=True),
            timeout=API_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError:
        return None


def _api_patch(base: str, path: str, json: dict[str, Any]) -> Any:
    """Make a PATCH request to the API backend."""
    try:
        r = httpx.patch(
            f"{base}{path}",
            json=json,
            headers=_request_headers(include_write_token=True),
            timeout=API_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError:
        return None


def register_callbacks(app: dash.Dash, api_base: str) -> None:
    """Register all Dash callbacks."""

    # ------------------------------------------------------------------
    # Page routing
    # ------------------------------------------------------------------
    @app.callback(
        Output("page-content", "children"),
        Input("url", "pathname"),
    )
    def route_page(pathname: str | None) -> Any:
        if pathname == "/timeline":
            return timeline_layout()
        # Default to review queue
        return review_layout()

    # ------------------------------------------------------------------
    # Review queue: load data
    # ------------------------------------------------------------------
    @app.callback(
        [
            Output("review-table", "data"),
            Output("review-stats-badges", "children"),
        ],
        [
            Input("refresh-interval", "n_intervals"),
            Input("filter-needs-review", "n_clicks"),
            Input("filter-approved", "n_clicks"),
            Input("filter-published", "n_clicks"),
            Input("filter-rejected", "n_clicks"),
            Input("filter-all", "n_clicks"),
        ],
    )
    def load_review_data(*args: Any) -> tuple[list[dict[str, Any]], Any]:
        ctx = callback_context
        triggered = ctx.triggered[0]["prop_id"] if ctx.triggered else ""

        # Determine filter
        status_map = {
            "filter-needs-review.n_clicks": "needs_review",
            "filter-approved.n_clicks": "approved",
            "filter-published.n_clicks": "published",
            "filter-rejected.n_clicks": "rejected",
            "filter-all.n_clicks": None,
        }
        status = status_map.get(triggered, "needs_review")

        # Fetch events
        params: dict[str, Any] = {"limit": 200}
        if status:
            params["review_status"] = status
        data = _api_get(api_base, "/api/v1/events", params=params)
        items = data.get("items", []) if data else []

        # Fetch stats
        stats = _api_get(api_base, "/api/v1/events/stats") or {}
        badges = dbc.Row(
            [
                dbc.Col(
                    dbc.Badge(
                        f"⏳ Needs Review: {stats.get('needs_review', 0)}",
                        color="warning",
                        className="me-2 p-2",
                    ),
                    width="auto",
                ),
                dbc.Col(
                    dbc.Badge(
                        f"✅ Approved: {stats.get('approved', 0)}",
                        color="success",
                        className="me-2 p-2",
                    ),
                    width="auto",
                ),
                dbc.Col(
                    dbc.Badge(
                        f"📤 Published: {stats.get('published', 0)}",
                        color="primary",
                        className="me-2 p-2",
                    ),
                    width="auto",
                ),
                dbc.Col(
                    dbc.Badge(
                        f"❌ Rejected: {stats.get('rejected', 0)}",
                        color="danger",
                        className="me-2 p-2",
                    ),
                    width="auto",
                ),
            ]
        )

        return items, badges

    # ------------------------------------------------------------------
    # Review queue: select row → show detail
    # ------------------------------------------------------------------
    @app.callback(
        [
            Output("event-detail-panel", "children"),
            Output("selected-event-id", "value"),
            Output("btn-approve", "disabled"),
            Output("btn-reject", "disabled"),
            Output("btn-publish", "disabled"),
        ],
        Input("review-table", "selected_rows"),
        State("review-table", "data"),
    )
    def show_event_detail(
        selected_rows: list[int] | None, table_data: list[dict[str, Any]]
    ) -> tuple[Any, str, bool, bool, bool]:
        if not selected_rows or not table_data:
            return html.P("Select an event to see details."), "", True, True, True

        row = table_data[selected_rows[0]]
        event_id = row.get("event_id", "")
        detail = _api_get(api_base, f"/api/v1/events/{event_id}")

        if not detail:
            return html.P("Failed to load event."), "", True, True, True

        panel = dbc.Card(
            dbc.CardBody(
                [
                    html.H5(detail.get("title", ""), className="card-title"),
                    html.P(detail.get("summary", ""), className="card-text"),
                    dbc.Row(
                        [
                            dbc.Col(
                                [
                                    html.Small("Category: ", className="text-muted"),
                                    dbc.Badge(
                                        detail.get("category", ""),
                                        color="info",
                                    ),
                                ]
                            ),
                            dbc.Col(
                                [
                                    html.Small("Confidence: ", className="text-muted"),
                                    html.Span(f"{detail.get('confidence', 0):.0%}"),
                                ]
                            ),
                            dbc.Col(
                                [
                                    html.Small("Importance: ", className="text-muted"),
                                    html.Span(str(detail.get("importance", 0))),
                                ]
                            ),
                            dbc.Col(
                                [
                                    html.Small("Source: ", className="text-muted"),
                                    html.Span(detail.get("source_id", "")),
                                ]
                            ),
                        ],
                        className="mb-2",
                    ),
                    html.Small(
                        f"Why it matters: {detail.get('why_it_matters', 'N/A')}",
                        className="text-muted",
                    ),
                ]
            ),
            className="mb-3",
        )

        return panel, event_id, False, False, False

    # ------------------------------------------------------------------
    # Review actions: approve / reject / publish
    # ------------------------------------------------------------------
    @app.callback(
        Output("action-result", "children"),
        [
            Input("btn-approve", "n_clicks"),
            Input("btn-reject", "n_clicks"),
            Input("btn-publish", "n_clicks"),
        ],
        State("selected-event-id", "value"),
        prevent_initial_call=True,
    )
    def handle_review_action(
        approve_clicks: int | None,
        reject_clicks: int | None,
        publish_clicks: int | None,
        event_id: str,
    ) -> Any:
        if not event_id:
            return no_update

        ctx = callback_context
        triggered = ctx.triggered[0]["prop_id"] if ctx.triggered else ""

        action_map = {
            "btn-approve.n_clicks": "approve",
            "btn-reject.n_clicks": "reject",
            "btn-publish.n_clicks": "publish",
        }
        action = action_map.get(triggered)
        if not action:
            return no_update

        result = _api_post(
            api_base,
            f"/api/v1/events/{event_id}/review",
            json={"action": action, "actor": "ui_user"},
        )

        if result and result.get("status") == "ok":
            return dbc.Alert(
                f"✅ Event {action}d successfully.",
                color="success",
                duration=3000,
            )
        return dbc.Alert(
            f"❌ Failed to {action} event.",
            color="danger",
            duration=3000,
        )

    # ------------------------------------------------------------------
    # Timeline: load chart
    # ------------------------------------------------------------------
    @app.callback(
        Output("timeline-chart", "figure"),
        [
            Input("refresh-interval", "n_intervals"),
            Input("timeline-days", "value"),
            Input("timeline-review-filter", "value"),
        ],
    )
    def load_timeline(n_intervals: int, days: str, review_filter: str) -> Any:
        params: dict[str, Any] = {"days": int(days)}
        if review_filter:
            params["review_status"] = review_filter

        data = _api_get(api_base, "/api/v1/events/timeline", params=params)
        entries = data.get("entries", []) if data else []

        if not entries:
            fig = go.Figure()
            fig.update_layout(
                title="No events in selected range",
                template="plotly_white",
                height=500,
            )
            return fig

        # Build dataframe for Plotly timeline
        rows = []
        for e in entries:
            start = e.get("start")
            end = e.get("end") or start
            rows.append(
                {
                    "Task": e.get("title", ""),
                    "Start": start,
                    "Finish": end,
                    "Category": e.get("category", "unknown"),
                    "Status": e.get("review_status", ""),
                    "Importance": e.get("importance", 0),
                    "Source": e.get("source_id", ""),
                }
            )

        df = pd.DataFrame(rows)
        fig = px.timeline(
            df,
            x_start="Start",
            x_end="Finish",
            y="Task",
            color="Category",
            color_discrete_map=CATEGORY_COLORS,
            hover_data=["Status", "Importance", "Source"],
            title=f"Event Timeline ({days} days)",
        )
        fig.update_layout(
            template="plotly_white",
            height=max(400, len(rows) * 30 + 100),
            yaxis={"autorange": "reversed"},
            showlegend=True,
        )
        # Add TODAY marker — use add_shape to avoid annotation bug on datetime x-axis
        now_str = pd.Timestamp(datetime.now(tz=UTC)).isoformat()
        fig.add_shape(
            type="line",
            x0=now_str,
            x1=now_str,
            y0=0,
            y1=1,
            yref="paper",
            line=dict(color="red", dash="dash", width=2),
        )
        fig.add_annotation(
            x=now_str,
            y=1,
            yref="paper",
            text="Today",
            showarrow=False,
            font=dict(color="red"),
            yanchor="bottom",
        )

        return fig
