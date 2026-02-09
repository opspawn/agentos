"""Mock chat client for local development without an LLM backend.

Returns deterministic responses based on agent instructions and input messages.
Useful for testing orchestration patterns without incurring API costs.
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


class MockChatClient(BaseChatClient):
    """A deterministic chat client that echoes instructions and input.

    Responds with a structured summary of what was asked, making it
    possible to verify orchestration flow without a real model.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._call_count = 0

    def _build_reply(self, messages: MutableSequence[ChatMessage]) -> str:
        """Build a mock reply from the conversation history."""
        self._call_count += 1

        last_user_msg = ""
        agent_name = "unknown"
        for msg in messages:
            if msg.role == Role.SYSTEM and msg.text:
                if "CEO" in msg.text:
                    agent_name = "CEO"
                elif "Builder" in msg.text:
                    agent_name = "Builder"
                elif "Research" in msg.text:
                    agent_name = "Research"
            if msg.role == Role.USER and msg.text:
                last_user_msg = msg.text

        # GroupChat orchestrator expects structured JSON decisions
        if "Decide what to do next" in last_user_msg and "next_speaker" in last_user_msg:
            return json.dumps({
                "terminate": True,
                "reason": f"Mock orchestration complete (call #{self._call_count})",
                "next_speaker": None,
                "final_message": f"Mock group chat result from {agent_name} agent.",
            })

        parts: list[str] = [f"[MockLLM call #{self._call_count}]"]
        parts.append(f"Agent: {agent_name}")
        if last_user_msg:
            parts.append(f"Task: {last_user_msg[:200]}")
        parts.append("Status: TASK_COMPLETE")
        parts.append(f"Result: Mock response from {agent_name} agent.")

        return "\n".join(parts)

    async def _inner_get_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        options: dict[str, Any],
        **kwargs: Any,
    ) -> ChatResponse:
        """Return a mock response."""
        reply_text = self._build_reply(messages)

        return ChatResponse(
            messages=[
                ChatMessage(role=Role.ASSISTANT, text=reply_text),
            ],
            response_id=str(uuid.uuid4()),
            model_id="mock-model",
            finish_reason=FinishReason("stop"),
        )

    async def _inner_get_streaming_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        options: dict[str, Any],
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        """Yield a single mock streaming update."""
        reply_text = self._build_reply(messages)

        yield ChatResponseUpdate(
            text=reply_text,
            role=Role.ASSISTANT,
            response_id=str(uuid.uuid4()),
            model_id="mock-model",
            finish_reason=FinishReason("stop"),
        )

    @property
    def call_count(self) -> int:
        """Number of times this client has been called."""
        return self._call_count
