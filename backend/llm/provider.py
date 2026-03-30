"""Unified LLM provider for SCL-Governor reasoning phases."""

from __future__ import annotations

from typing import Any

from utils.logger import get_logger

log = get_logger(__name__)


class LLMProvider:
    """Unified LLM provider supporting Anthropic Claude and OpenAI.

    Initialisation is lazy -- the underlying SDK client is only created if
    valid API keys are present in *settings*.  When no provider is available
    the ``reason`` method returns an empty string so that phases can fall
    back to heuristic logic.
    """

    def __init__(self, settings: Any) -> None:
        self.provider: str = getattr(settings, "LLM_PROVIDER", "anthropic")
        self.model: str = getattr(settings, "LLM_MODEL", "claude-sonnet-4-20250514")
        self._anthropic_client: Any | None = None
        self._openai_client: Any | None = None
        self._initialize(settings)

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _initialize(self, settings: Any) -> None:
        anthropic_key = getattr(settings, "ANTHROPIC_API_KEY", "")
        openai_key = getattr(settings, "OPENAI_API_KEY", "")

        if self.provider == "anthropic" and anthropic_key:
            try:
                import anthropic

                self._anthropic_client = anthropic.AsyncAnthropic(
                    api_key=anthropic_key,
                )
                log.info("llm_provider_initialized", provider="anthropic", model=self.model)
            except ImportError:
                log.warning("anthropic_sdk_not_installed")
            except Exception as exc:
                log.warning("anthropic_init_failed", error=str(exc))

        elif self.provider == "openai" and openai_key:
            try:
                import openai

                self._openai_client = openai.AsyncOpenAI(api_key=openai_key)
                log.info("llm_provider_initialized", provider="openai", model=self.model)
            except ImportError:
                log.warning("openai_sdk_not_installed")
            except Exception as exc:
                log.warning("openai_init_failed", error=str(exc))

        if not self.is_available:
            log.warning(
                "llm_provider_unavailable",
                provider=self.provider,
                hint="Set ANTHROPIC_API_KEY or OPENAI_API_KEY to enable LLM reasoning",
            )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_available(self) -> bool:
        """Return ``True`` when at least one LLM backend is configured."""
        return self._anthropic_client is not None or self._openai_client is not None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def reason(self, prompt: str, system_prompt: str = "") -> str:
        """Send a reasoning request to the configured LLM provider.

        Returns the response text.  On any failure returns an empty string
        so callers can fall back to heuristic paths.
        """
        if not self.is_available:
            log.debug("llm_reason_skipped", reason="no provider available")
            return ""

        try:
            if self._anthropic_client is not None:
                return await self._anthropic_reason(prompt, system_prompt)
            if self._openai_client is not None:
                return await self._openai_reason(prompt, system_prompt)
        except Exception as exc:
            log.error("llm_reason_failed", provider=self.provider, error=str(exc))

        return ""

    # ------------------------------------------------------------------
    # Provider-specific implementations
    # ------------------------------------------------------------------

    async def _anthropic_reason(self, prompt: str, system_prompt: str) -> str:
        """Call Anthropic Messages API."""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        response = await self._anthropic_client.messages.create(**kwargs)

        # Extract text from the first content block
        for block in response.content:
            if hasattr(block, "text"):
                return block.text
        return ""

    async def _openai_reason(self, prompt: str, system_prompt: str) -> str:
        """Call OpenAI Chat Completions API."""
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await self._openai_client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=2048,
            temperature=0.2,
        )

        choice = response.choices[0] if response.choices else None
        if choice and choice.message and choice.message.content:
            return choice.message.content
        return ""
