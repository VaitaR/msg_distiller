"""E2E Playwright fixtures for Dash UI testing.

Servers run on ISOLATED ports (18000 / 18050) so they never conflict with a
developer's live servers on 8000 / 8050.  Both processes receive DB_PATH
pointing at the session-scoped seeded SQLite database so every page load
shows real event data.
"""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Generator
from pathlib import Path
from typing import Any

import httpx
import pytest

# Skip all e2e tests if SKIP_E2E is set
pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_E2E", "1") == "1",
    reason="E2E tests disabled (set SKIP_E2E=0 to enable)",
)

# Dedicated test ports — never conflict with a dev server
API_TEST_PORT = 18000
DASH_TEST_PORT = 18050
DASH_TEST_URL = f"http://localhost:{DASH_TEST_PORT}"
API_TEST_URL = f"http://localhost:{API_TEST_PORT}"

# Project root for launching subprocess scripts
_PROJECT_ROOT = str(Path(__file__).parent.parent.parent)


def _wait_for_server(url: str, timeout: float = 20.0, interval: float = 0.5) -> None:
    """Poll *url* until it responds 200 or *timeout* seconds elapse."""
    deadline = time.monotonic() + timeout
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            httpx.get(url, timeout=2.0)
            return
        except Exception as exc:
            last_exc = exc
            time.sleep(interval)
    raise RuntimeError(
        f"Server at {url} did not become ready within {timeout}s. "
        f"Last error: {last_exc}"
    )


@pytest.fixture(scope="session")
def _start_servers(
    seeded_db_session: tuple[str, Any],
) -> Generator[None, None, None]:
    """Start API + Dash servers once per test session backed by seeded data.

    Both subprocesses inherit the current environment plus DB_PATH so pydantic-
    settings resolves the SQLite file to the seeded one.
    """
    db_path, _ = seeded_db_session

    env = {
        **os.environ,
        "DB_PATH": db_path,
        "SLACK_BOT_TOKEN": os.environ.get("SLACK_BOT_TOKEN", "test-token"),
        "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", "test-key"),
        "SKIP_E2E": "0",  # prevent child processes from triggering this guard
    }

    procs: list[subprocess.Popen[bytes]] = []

    api_proc = subprocess.Popen(
        [
            "uv",
            "run",
            "python",
            "scripts/run_api_server.py",
            "--port",
            str(API_TEST_PORT),
        ],
        cwd=_PROJECT_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    procs.append(api_proc)
    _wait_for_server(f"{API_TEST_URL}/api/v1/health")

    dash_proc = subprocess.Popen(
        [
            "uv",
            "run",
            "python",
            "scripts/run_dash.py",
            "--port",
            str(DASH_TEST_PORT),
        ],
        cwd=_PROJECT_ROOT,
        env={**env, "API_BASE_URL": API_TEST_URL},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    procs.append(dash_proc)
    _wait_for_server(DASH_TEST_URL)

    yield

    for p in procs:
        p.terminate()
        try:
            p.wait(timeout=8)
        except subprocess.TimeoutExpired:
            p.kill()


@pytest.fixture(scope="session")
def dash_url() -> str:
    """Base URL for the e2e Dash UI."""
    return DASH_TEST_URL


@pytest.fixture(scope="session")
def api_url() -> str:
    """Base URL for the e2e API."""
    return API_TEST_URL
