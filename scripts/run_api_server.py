#!/usr/bin/env python3
"""Run the FastAPI API server.

Usage:
    python scripts/run_api_server.py
    python scripts/run_api_server.py --host 0.0.0.0 --port 8000
"""

import argparse
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn  # noqa: E402

from src.api.app import create_app  # noqa: E402
from src.config.settings import get_settings  # noqa: E402


def main() -> None:
    settings = get_settings()

    parser = argparse.ArgumentParser(description="Event Manager API Server")
    parser.add_argument(
        "--host",
        default=None,
        help="Bind host (defaults to API_BIND_HOST or 127.0.0.1)",
    )
    parser.add_argument("--port", type=int, default=8000, help="Bind port")
    parser.add_argument(
        "--reload", action="store_true", help="Auto-reload on code changes"
    )
    args = parser.parse_args()

    app = create_app()
    uvicorn.run(
        app,
        host=args.host or settings.api_bind_host,
        port=args.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
