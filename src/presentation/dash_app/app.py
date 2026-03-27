"""Dash application factory.

Creates the Dash app with layout, callbacks, and styling.
Reads data exclusively via the FastAPI backend (no direct repo import).
"""

import os

import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

from src.presentation.dash_app.callbacks import register_callbacks

# API base URL (configurable via env, default to local API)
API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")


def create_dash_app() -> dash.Dash:
    """Build and return the Dash application."""
    app = dash.Dash(
        __name__,
        external_stylesheets=[dbc.themes.FLATLY],
        suppress_callback_exceptions=True,
        title="Event Manager",
        update_title="Loading…",
    )

    app.layout = dbc.Container(
        fluid=True,
        className="px-4 py-3",
        children=[
            # Navigation
            dbc.NavbarSimple(
                brand="📅 Event Manager",
                brand_href="/",
                color="primary",
                dark=True,
                children=[
                    dbc.NavItem(dbc.NavLink("Review Queue", href="/review")),
                    dbc.NavItem(dbc.NavLink("Timeline", href="/timeline")),
                ],
                className="mb-4",
            ),
            # URL routing
            dcc.Location(id="url", refresh=False),
            # Page content
            html.Div(id="page-content"),
            # Auto-refresh every 30 seconds
            dcc.Interval(id="refresh-interval", interval=30_000, n_intervals=0),
        ],
    )

    # Register all callbacks
    register_callbacks(app, api_base=API_BASE)

    return app
