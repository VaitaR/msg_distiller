"""Shared priority constants for pipeline task orchestration."""

from __future__ import annotations

from typing import Final

INGEST_TASK_PRIORITY: Final[int] = 5
EXTRACTION_TASK_PRIORITY: Final[int] = 10
LLM_EXTRACTION_TASK_PRIORITY: Final[int] = 12
DEDUP_TASK_PRIORITY: Final[int] = 15
EMBEDDING_TASK_PRIORITY: Final[int] = 17
DIGEST_TASK_PRIORITY: Final[int] = 20

__all__ = [
    "DEDUP_TASK_PRIORITY",
    "DIGEST_TASK_PRIORITY",
    "EMBEDDING_TASK_PRIORITY",
    "EXTRACTION_TASK_PRIORITY",
    "INGEST_TASK_PRIORITY",
    "LLM_EXTRACTION_TASK_PRIORITY",
]
