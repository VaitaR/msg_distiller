"""Domain constants for candidate processing."""

from datetime import timedelta
from typing import Final

CANDIDATE_LEASE_TIMEOUT: Final[timedelta] = timedelta(minutes=15)

# Fallback when settings.llm_max_events_per_msg is unset or invalid.
LLM_MAX_EVENTS_PER_MSG_FALLBACK: Final[int] = 5

# Hard-collapse policy: 1 primary + optional 1 sub-event per message.
HARD_MAX_EVENTS_PER_MESSAGE: Final[int] = 2

__all__ = [
    "CANDIDATE_LEASE_TIMEOUT",
    "HARD_MAX_EVENTS_PER_MESSAGE",
    "LLM_MAX_EVENTS_PER_MSG_FALLBACK",
]
