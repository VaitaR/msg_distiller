from __future__ import annotations

"""Entry point for the embedding worker (embed events + semantic dedup)."""

import argparse
import sys
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pydantic import SecretStr

from scripts import pipeline_runtime
from src.adapters.llm_client import LLMClient
from src.adapters.repository_factory import create_repository
from src.config.logging_config import get_logger
from src.config.settings import get_settings
from src.services.task_queue_factory import (
    TaskQueueUnavailableError,
    resolve_task_queue,
)
from src.use_cases.embed_events import embed_events_use_case
from src.use_cases.semantic_dedup import semantic_dedup_use_case
from src.workers.pipeline import EmbeddingWorker

logger = get_logger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the embedding worker")
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=10.0,
        help="Seconds to wait between lease attempts when the queue is idle",
    )
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Process a single task and exit",
    )
    parser.add_argument(
        "--json-logs",
        action="store_true",
        help="Emit logs in JSON format",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    settings = get_settings()
    pipeline_runtime.initialize_logging(settings, json_logs=args.json_logs)

    controller = pipeline_runtime.create_shutdown_controller()
    pipeline_runtime.install_signal_handlers(controller)

    repository = create_repository(settings)
    try:
        task_queue = resolve_task_queue(repository)
    except TaskQueueUnavailableError as exc:
        logger.error("task_queue_unavailable", error=str(exc))
        return 1

    try:
        llm_client = LLMClient(
            api_key=_extract_secret(settings.openai_api_key),
            model=settings.llm_model,
            timeout=settings.llm_timeout_seconds,
        )
    except Exception:  # noqa: BLE001
        logger.exception("llm_client_initialization_failed")
        return 1

    worker = EmbeddingWorker(
        task_queue=task_queue,
        embed_events=partial(
            embed_events_use_case,
            repository=repository,
            llm_client=llm_client,
            settings=settings,
        ),
        semantic_dedup=partial(
            semantic_dedup_use_case,
            repository=repository,
            settings=settings,
        ),
    )

    pipeline_runtime.run_worker_loop(
        worker,
        controller,
        poll_interval=args.poll_interval_seconds,
        run_once=args.run_once,
        idle_backoff_seconds=1.0,
    )

    return 0


def _extract_secret(secret: SecretStr) -> str:
    value = secret.get_secret_value()
    if not value:
        msg = "Secret value is empty"
        raise ValueError(msg)
    return value


if __name__ == "__main__":
    raise SystemExit(main())
