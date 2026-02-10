"""Azure OpenAI chat client for the Microsoft Agent Framework.

Wraps the ``openai.AzureOpenAI`` SDK into a ``BaseChatClient`` so that
HireWire agents can use real GPT-4o completions through Azure OpenAI Service.

Environment variables (set via azure-hackathon.env):
    AZURE_OPENAI_ENDPOINT   — Azure OpenAI resource endpoint
    AZURE_OPENAI_KEY        — API key
    AZURE_OPENAI_DEPLOYMENT — Model deployment name (default: gpt-4o)
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterable, MutableSequence
from typing import Any

from agent_framework import (
    BaseChatClient,
    ChatMessage,
    ChatResponse,
    ChatResponseUpdate,
    FinishReason,
    Role,
)


class AzureOpenAIChatClient(BaseChatClient):
    """Agent Framework chat client backed by Azure OpenAI (``openai`` SDK).

    Translates ``ChatMessage`` sequences into OpenAI-format messages,
    calls the Azure endpoint, and wraps the response back into framework types.
    """

    def __init__(
        self,
        endpoint: str | None = None,
        api_key: str | None = None,
        deployment: str = "gpt-4o",
        api_version: str = "2024-12-01-preview",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        from src.framework.azure_llm import AzureLLMProvider

        self._provider = AzureLLMProvider(
            endpoint=endpoint,
            api_key=api_key,
            deployment=deployment,
            api_version=api_version,
        )
        self._total_tokens = 0
        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0

    @property
    def usage_summary(self) -> dict[str, int]:
        """Cumulative token usage across all calls."""
        return {
            "prompt_tokens": self._total_prompt_tokens,
            "completion_tokens": self._total_completion_tokens,
            "total_tokens": self._total_tokens,
        }

    @staticmethod
    def _to_openai_messages(messages: MutableSequence[ChatMessage]) -> list[dict[str, str]]:
        """Convert agent framework messages to OpenAI format."""
        result: list[dict[str, str]] = []
        for msg in messages:
            role = "user"
            if msg.role == Role.SYSTEM:
                role = "system"
            elif msg.role == Role.ASSISTANT:
                role = "assistant"
            elif msg.role == Role.USER:
                role = "user"
            text = msg.text or ""
            if text:
                result.append({"role": role, "content": text})
        return result

    async def _inner_get_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        options: dict[str, Any],
        **kwargs: Any,
    ) -> ChatResponse:
        """Call Azure OpenAI and return a framework ChatResponse."""
        openai_msgs = self._to_openai_messages(messages)

        result = self._provider.chat_completion(
            messages=openai_msgs,
            temperature=options.get("temperature", 0.7),
            max_tokens=options.get("max_tokens", 2048),
        )

        usage = result.get("usage", {})
        self._total_prompt_tokens += usage.get("prompt_tokens", 0)
        self._total_completion_tokens += usage.get("completion_tokens", 0)
        self._total_tokens += usage.get("total_tokens", 0)

        return ChatResponse(
            messages=[
                ChatMessage(role=Role.ASSISTANT, text=result["content"]),
            ],
            response_id=str(uuid.uuid4()),
            model_id=result.get("model", self._provider.deployment),
            finish_reason=FinishReason(result.get("finish_reason", "stop")),
        )

    async def _inner_get_streaming_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        options: dict[str, Any],
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        """Non-streaming fallback — yields a single complete update."""
        openai_msgs = self._to_openai_messages(messages)

        result = self._provider.chat_completion(
            messages=openai_msgs,
            temperature=options.get("temperature", 0.7),
            max_tokens=options.get("max_tokens", 2048),
        )

        usage = result.get("usage", {})
        self._total_prompt_tokens += usage.get("prompt_tokens", 0)
        self._total_completion_tokens += usage.get("completion_tokens", 0)
        self._total_tokens += usage.get("total_tokens", 0)

        yield ChatResponseUpdate(
            text=result["content"],
            role=Role.ASSISTANT,
            response_id=str(uuid.uuid4()),
            model_id=result.get("model", self._provider.deployment),
            finish_reason=FinishReason(result.get("finish_reason", "stop")),
        )
