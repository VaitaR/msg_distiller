"""Tests for prompt metadata block (P0.2)."""

from __future__ import annotations

from datetime import UTC, datetime

from src.adapters.llm_client import LLMClient


def test_llm_prompt_includes_message_metadata_block() -> None:
    llm = LLMClient(
        api_key="test",
        model="gpt-5-nano",
        prompt_template="system",
        timeout=5,
    )

    context = {
        "source_id": "slack",
        "channel_id": "C123",
        "message_id": "msg-1",
        "anchors": ["ABC-123"],
        "reply_count": 2,
    }

    prompt = llm._build_prompt(
        "hello",
        ["https://example.com"],
        datetime(2025, 12, 1, 12, 0, tzinfo=UTC),
        "general",
        context=context,
    )

    assert "Message metadata" in prompt
    assert '"anchors"' in prompt
    assert '"ABC-123"' in prompt
