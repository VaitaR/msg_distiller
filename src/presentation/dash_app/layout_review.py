"""Review queue layout — table of events with approve/reject/edit controls."""

import dash_bootstrap_components as dbc
from dash import dash_table, html

# Category badge colors
CATEGORY_COLORS = {
    "product": "success",
    "risk": "danger",
    "process": "info",
    "marketing": "secondary",
    "org": "warning",
    "unknown": "light",
}


def review_layout() -> dbc.Container:
    """Build the review queue page layout."""
    return dbc.Container(
        fluid=True,
        children=[
            dbc.Row(
                [
                    dbc.Col(html.H3("📋 Review Queue"), width="auto"),
                    dbc.Col(
                        dbc.ButtonGroup(
                            [
                                dbc.Button(
                                    "Needs Review",
                                    id="filter-needs-review",
                                    color="warning",
                                    outline=True,
                                    active=True,
                                    size="sm",
                                ),
                                dbc.Button(
                                    "Approved",
                                    id="filter-approved",
                                    color="success",
                                    outline=True,
                                    size="sm",
                                ),
                                dbc.Button(
                                    "Published",
                                    id="filter-published",
                                    color="primary",
                                    outline=True,
                                    size="sm",
                                ),
                                dbc.Button(
                                    "Rejected",
                                    id="filter-rejected",
                                    color="danger",
                                    outline=True,
                                    size="sm",
                                ),
                                dbc.Button(
                                    "All",
                                    id="filter-all",
                                    color="secondary",
                                    outline=True,
                                    size="sm",
                                ),
                            ],
                            className="mb-3",
                        ),
                        width="auto",
                    ),
                ],
                align="center",
                className="mb-3",
            ),
            # Stats badges
            html.Div(id="review-stats-badges", className="mb-3"),
            # Events table
            dash_table.DataTable(  # type: ignore[attr-defined]  # runtime-valid; dash stub gap
                id="review-table",
                columns=[
                    {"name": "Title", "id": "title", "type": "text"},
                    {"name": "Category", "id": "category", "type": "text"},
                    {"name": "Status", "id": "status", "type": "text"},
                    {
                        "name": "Confidence",
                        "id": "confidence",
                        "type": "numeric",
                        "format": {"specifier": ".0%"},
                    },
                    {"name": "Importance", "id": "importance", "type": "numeric"},
                    {"name": "Source", "id": "source_id", "type": "text"},
                    {"name": "Review", "id": "review_status", "type": "text"},
                    {"name": "Extracted", "id": "extracted_at", "type": "datetime"},
                ],
                data=[],
                row_selectable="single",
                sort_action="native",
                sort_by=[{"column_id": "confidence", "direction": "asc"}],
                filter_action="native",
                page_size=25,
                style_table={"overflowX": "auto"},
                style_cell={
                    "textAlign": "left",
                    "padding": "8px",
                    "fontSize": "13px",
                },
                style_header={
                    "fontWeight": "bold",
                    "backgroundColor": "#f8f9fa",
                },
                style_data_conditional=[
                    {
                        "if": {"filter_query": "{review_status} = needs_review"},
                        "backgroundColor": "#fff3cd",
                    },
                    {
                        "if": {"filter_query": "{review_status} = approved"},
                        "backgroundColor": "#d4edda",
                    },
                    {
                        "if": {"filter_query": "{review_status} = rejected"},
                        "backgroundColor": "#f8d7da",
                    },
                ],
            ),
            html.Hr(),
            # Event detail panel (shown when row selected)
            html.Div(id="event-detail-panel"),
            # Action buttons (shown when event selected)
            html.Div(
                id="review-actions",
                className="mt-3",
                children=[
                    dbc.ButtonGroup(
                        [
                            dbc.Button(
                                "✅ Approve",
                                id="btn-approve",
                                color="success",
                                disabled=True,
                            ),
                            dbc.Button(
                                "❌ Reject",
                                id="btn-reject",
                                color="danger",
                                disabled=True,
                            ),
                            dbc.Button(
                                "📤 Publish",
                                id="btn-publish",
                                color="primary",
                                disabled=True,
                            ),
                        ]
                    ),
                    html.Div(id="action-result", className="mt-2"),
                ],
            ),
            # Hidden store for selected event ID
            dbc.Input(id="selected-event-id", type="hidden", value=""),
        ],
    )
