"""FastAPI application factory.

Creates and configures the FastAPI app with routes and middleware.
"""

from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes_events import router as events_router
from src.api.schemas import HealthResponse

try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    _HAS_OTEL = True
except ImportError:
    _HAS_OTEL = False


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
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
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
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

    # OpenTelemetry instrumentation (if available)
    if _HAS_OTEL:
        FastAPIInstrumentor.instrument_app(app)

    return app
