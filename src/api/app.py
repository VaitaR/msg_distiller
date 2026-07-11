"""FastAPI application factory.

Creates and configures the FastAPI app with routes and middleware.
"""

from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.dependencies import get_app_settings
from src.api.routes_events import router as events_router
from src.api.routes_registry import router as registry_router
from src.api.routes_stories import router as stories_router
from src.api.schemas import HealthResponse

try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    _HAS_OTEL = True
except ImportError:
    _HAS_OTEL = False


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_app_settings()

    app = FastAPI(
        title="Slack Event Manager API",
        description="Events, timeline, review workflow for internal company events",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # CORS — allow Dash UI and local dev
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", "X-Review-Api-Token"],
    )

    # Health endpoint
    @app.get("/api/v1/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            version="0.1.0",
            timestamp=datetime.now(tz=UTC),
        )

    # Mount event routes
    app.include_router(events_router)
    app.include_router(stories_router)
    app.include_router(registry_router)

    # OpenTelemetry instrumentation (if available)
    if _HAS_OTEL:
        FastAPIInstrumentor.instrument_app(app)

    return app
