"""LLM client pool for per-channel prompt routing.

Implements P1.1 from docs/TECHNICAL_SPEC_EXTRACTION_QUALITY.md:
pick prompt per channel (if configured), otherwise per-source default, while
reusing LLMClient instances across candidates.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.adapters.llm_client import LLMClient
from src.config.logging_config import get_logger
from src.config.settings import Settings
from src.domain.models import MessageSource

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class _ClientKey:
    source_id: str
    prompt_file: str
    model: str
    temperature: float
    timeout_seconds: int


class LLMClientPool:
    """Cache of LLMClient instances keyed by prompt file and source settings."""

    def __init__(self, *, base_client: LLMClient, settings: Settings) -> None:
        self._base_client = base_client
        self._settings = settings
        self._clients: dict[_ClientKey, LLMClient] = {}

    def get_effective_prompt_file(
        self, *, source_id: MessageSource, channel_prompt_file: str | None
    ) -> str | None:
        """Resolve prompt file based on channel override and source defaults."""

        if isinstance(channel_prompt_file, str) and channel_prompt_file.strip():
            return channel_prompt_file.strip()

        source_config = self._settings.get_source_config(source_id)
        if source_config and isinstance(source_config.prompt_file, str):
            if source_config.prompt_file.strip():
                return source_config.prompt_file.strip()

        return None

    def get_client(
        self, *, source_id: MessageSource, prompt_file: str | None
    ) -> LLMClient:
        """Return an LLMClient for the prompt file (or the base client)."""

        if not (isinstance(prompt_file, str) and prompt_file.strip()):
            return self._base_client

        model = getattr(self._base_client, "model", self._settings.llm_model)
        temperature = float(getattr(self._base_client, "temperature", 1.0))
        timeout_seconds = int(
            getattr(
                self._base_client, "timeout_seconds", self._settings.llm_timeout_seconds
            )
        )

        source_config = self._settings.get_source_config(source_id)
        if source_config and isinstance(source_config.llm_settings, dict):
            temperature_raw = source_config.llm_settings.get("temperature")
            if isinstance(temperature_raw, int | float):
                temperature = float(temperature_raw)
            timeout_raw = source_config.llm_settings.get(
                "timeout_seconds"
            ) or source_config.llm_settings.get("timeout")
            if isinstance(timeout_raw, int):
                timeout_seconds = int(timeout_raw)

        key = _ClientKey(
            source_id=source_id.value,
            prompt_file=prompt_file.strip(),
            model=str(model),
            temperature=temperature,
            timeout_seconds=timeout_seconds,
        )

        cached = self._clients.get(key)
        if cached is not None:
            return cached

        api_key_obj = getattr(self._settings, "openai_api_key", None)
        api_key = None
        if api_key_obj is not None:
            try:
                api_key = api_key_obj.get_secret_value()
            except Exception:  # noqa: BLE001
                api_key = None

        if not isinstance(api_key, str) or not api_key.strip():
            logger.warning(
                "llm_pool_missing_api_key",
                source_id=source_id.value,
                prompt_file=prompt_file,
            )
            return self._base_client

        client = LLMClient(
            api_key=api_key,
            model=str(model),
            temperature=temperature,
            timeout=timeout_seconds,
            verbose=getattr(self._base_client, "verbose", False),
            prompt_file=prompt_file.strip(),
            prompt_budget=getattr(self._base_client, "prompt_token_budget", None),
        )

        self._clients[key] = client
        return client
