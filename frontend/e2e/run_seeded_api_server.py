#!/usr/bin/env python3
"""Start the FastAPI app against a deterministic seeded SQLite database."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

import uvicorn

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.adapters.repository_factory import create_repository  # noqa: E402
from src.api.app import create_app  # noqa: E402
from src.config.settings import Settings  # noqa: E402
from tests.factories import SEED_EVENTS  # noqa: E402


def ensure_seeded_database(db_path: str) -> None:
    settings = Settings().model_copy(
        update={'database_type': 'sqlite', 'db_path': db_path}
    )
    repository = create_repository(settings)
    repository.save_events(SEED_EVENTS)
    close = getattr(repository, 'close', None)
    if callable(close):
        close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Run FastAPI with seeded SQLite data'
    )
    parser.add_argument('--port', type=int, default=18000)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--db-path', default='')
    args = parser.parse_args()

    db_path = args.db_path or str(
        Path(tempfile.gettempdir()) / 'frontend-seeded-events.sqlite'
    )
    if Path(db_path).exists():
        Path(db_path).unlink()

    os.environ['DB_PATH'] = db_path
    os.environ.setdefault('SLACK_BOT_TOKEN', 'test-token')
    os.environ.setdefault('OPENAI_API_KEY', 'test-key')
    os.environ.setdefault('REVIEW_API_TOKEN', 'test-review-token')

    ensure_seeded_database(db_path)

    uvicorn.run(create_app(), host=args.host, port=args.port, log_level='warning')


if __name__ == '__main__':
    main()