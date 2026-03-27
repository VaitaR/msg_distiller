"""Timeline layout — Plotly Gantt/timeline view of events."""

import dash_bootstrap_components as dbc
from dash import dcc, html

# Category colors for timeline bars
CATEGORY_COLORS = {
    "product": "#2ECC71",
    "risk": "#E74C3C",
    "process": "#3498DB",
    "marketing": "#9B59B6",
    "org": "#F39C12",
    "unknown": "#95A5A6",
}


def timeline_layout() -> dbc.Container:
    """Build the timeline page layout."""
    return dbc.Container(
        fluid=True,
        children=[
            dbc.Row(
                [
                    dbc.Col(html.H3("📅 Event Timeline"), width="auto"),
                    dbc.Col(
                        dbc.Select(
                            id="timeline-days",
                            options=[
                                {"label": "7 days", "value": "7"},
                                {"label": "14 days", "value": "14"},
                                {"label": "30 days", "value": "30"},
                                {"label": "60 days", "value": "60"},
                                {"label": "90 days", "value": "90"},
                            ],
                            value="30",
                            className="mb-3",
                            style={"width": "150px"},
                        ),
                        width="auto",
                    ),
                    dbc.Col(
                        dbc.Select(
                            id="timeline-review-filter",
                            options=[
                                {"label": "All", "value": ""},
                                {"label": "Published", "value": "published"},
                                {"label": "Approved", "value": "approved"},
                                {"label": "Needs Review", "value": "needs_review"},
                            ],
                            value="",
                            className="mb-3",
                            style={"width": "180px"},
                        ),
                        width="auto",
                    ),
                ],
                align="center",
                className="mb-3",
            ),
            # Timeline chart
            dcc.Loading(
                dcc.Graph(
                    id="timeline-chart",
                    config={"displayModeBar": True, "responsive": True},
                    style={"height": "600px"},
                ),
            ),
            html.Hr(),
            # Event detail (click on bar)
            html.Div(id="timeline-event-detail"),
        ],
    )
