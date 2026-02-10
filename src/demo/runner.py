"""Live demo runner — submits tasks at intervals for real-time dashboard activity.

When started, the DemoRunner submits a curated task every 30 seconds,
triggering the full CEO -> analyze -> route -> GPT-4o -> pay pipeline so judges
can watch the dashboard update in real time.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
import uuid
from typing import Any

from src.agents.ceo_agent import analyze_task
from src.mcp_servers.payment_hub import ledger
from src.storage import get_storage

logger = logging.getLogger(__name__)

# Curated list of interesting demo tasks with agent routing hints
DEMO_TASK_LIST: list[dict[str, Any]] = [
    {
        "description": "Build a React dashboard for real-time agent monitoring",
        "budget": 4.00,
        "agent": "builder",
        "gpt_prompt": "Design a React dashboard architecture for monitoring AI agents in real-time. Cover: component hierarchy, WebSocket integration, state management, and key metrics to display. Be concise (under 150 words).",
    },
    {
        "description": "Research top 10 AI agent frameworks and compare features",
        "budget": 2.00,
        "agent": "research",
        "gpt_prompt": "Compare the top AI agent frameworks: AutoGen, CrewAI, LangGraph, Semantic Kernel, and SuperAGI. Rate each on: ease of use, multi-agent support, tool integration, and community. Be concise (under 150 words).",
    },
    {
        "description": "Design a mobile-first onboarding flow for the agent marketplace",
        "budget": 1.50,
        "agent": "designer-ext-001",
        "gpt_prompt": "Design a mobile-first onboarding flow for an AI agent marketplace. Cover: welcome screen, agent discovery, first task creation, and payment setup. Include 4 screen descriptions. Be concise (under 150 words).",
    },
    {
        "description": "Analyze customer churn patterns using transaction data",
        "budget": 1.75,
        "agent": "analyst-ext-001",
        "gpt_prompt": "Analyze potential churn patterns in an AI agent marketplace. Cover: key churn indicators, retention metrics, cohort analysis approach, and 3 actionable recommendations. Be concise (under 150 words).",
    },
    {
        "description": "Deploy a Redis cache layer for agent state management",
        "budget": 2.50,
        "agent": "builder",
        "gpt_prompt": "Plan a Redis caching layer for agent state management. Cover: data structures for agent state, TTL strategy, cache invalidation, and failover handling. Be concise (under 150 words).",
    },
    {
        "description": "Create a performance benchmarking suite for agent workflows",
        "budget": 2.25,
        "agent": "builder",
        "gpt_prompt": "Design a performance benchmarking suite for AI agent workflows. Cover: latency measurement, throughput testing, cost tracking per task, and comparison baselines. Be concise (under 150 words).",
    },
    {
        "description": "Write a technical blog post about agent-to-agent payments",
        "budget": 1.00,
        "agent": "research",
        "gpt_prompt": "Outline a technical blog post about x402 agent-to-agent micropayments. Cover: HTTP 402 protocol, escrow mechanism, USDC settlement, and real-world use cases. Be concise (under 150 words).",
    },
    {
        "description": "Research security best practices for agent marketplace APIs",
        "budget": 2.00,
        "agent": "research",
        "gpt_prompt": "Summarize security best practices for an AI agent marketplace API. Cover: authentication, rate limiting, input validation, escrow protection, and audit logging. Be concise (under 150 words).",
    },
    {
        "description": "Design brand identity system for the HireWire platform",
        "budget": 3.00,
        "agent": "designer-ext-002",
        "gpt_prompt": "Create a brand identity system for HireWire, an AI agent marketplace. Cover: logo concept, color palette, typography, and tone of voice. Be concise (under 150 words).",
    },
    {
        "description": "Evaluate pricing models for external agent services",
        "budget": 1.50,
        "agent": "analyst-ext-001",
        "gpt_prompt": "Compare pricing models for AI agent marketplace services: per-task, subscription, credits, and auction-based. Recommend the best model with pros/cons. Be concise (under 150 words).",
    },
]


def _get_gpt4o_response(prompt: str) -> str | None:
    """Call Azure OpenAI GPT-4o. Returns None if unavailable."""
    try:
        from src.framework.azure_llm import azure_available, get_azure_llm
        if not azure_available():
            return None
        provider = get_azure_llm()
        result = provider.chat_completion(
            messages=[
                {"role": "system", "content": "You are a HireWire AI agent. Provide concise, professional analysis. Use bullet points."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=250,
        )
        return result.get("content", "")
    except Exception as e:
        logger.warning("GPT-4o call failed in demo runner: %s", e)
        return None


class DemoRunner:
    """Submits curated tasks at regular intervals for live demo activity."""

    def __init__(self, interval: float = 30.0) -> None:
        self.interval = interval
        self._task: asyncio.Task | None = None
        self._running = False
        self._task_index = 0
        self._tasks_submitted = 0

    @property
    def is_running(self) -> bool:
        return self._running

    async def run(self) -> None:
        """Main demo loop — submit a task, wait, repeat."""
        self._running = True
        try:
            while self._running:
                await self._submit_next_task()
                self._task_index = (self._task_index + 1) % len(DEMO_TASK_LIST)
                self._tasks_submitted += 1
                await asyncio.sleep(self.interval)
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False

    async def _submit_next_task(self) -> None:
        """Submit the next demo task through the full pipeline with GPT-4o."""
        spec = DEMO_TASK_LIST[self._task_index]
        task_id = f"demo_{uuid.uuid4().hex[:8]}"
        storage = get_storage()
        now = time.time()

        # 1. Create the task
        storage.save_task(
            task_id=task_id,
            description=spec["description"],
            workflow="ceo",
            budget_usd=spec["budget"],
            status="pending",
            created_at=now,
        )

        # 2. CEO analyzes the task
        storage.update_task_status(task_id, "running")
        analysis = await analyze_task(spec["description"])

        # 3. Get real GPT-4o response
        gpt_response = await asyncio.get_event_loop().run_in_executor(
            None, _get_gpt4o_response, spec["gpt_prompt"]
        )

        elapsed_ms = (time.time() - now) * 1000
        agent = spec["agent"]

        # 4. Enrich result with GPT-4o response
        analysis["agent_response"] = gpt_response or f"Task completed by {agent}."
        analysis["agent_response_preview"] = (gpt_response or "Task completed.")[:150]
        analysis["assigned_agent"] = agent
        analysis["model"] = "gpt-4o" if gpt_response else "mock"
        analysis["response_time_ms"] = round(elapsed_ms, 0)

        # 5. Allocate budget and record payment
        estimated_cost = analysis.get("estimated_cost", 0.0)
        if estimated_cost > 0:
            ledger.allocate_budget(task_id, spec["budget"])
            ledger.record_payment(
                from_agent="ceo",
                to_agent=agent,
                amount=min(estimated_cost, spec["budget"]),
                task_id=task_id,
            )

        # 6. Mark completed
        storage.update_task_status(task_id, "completed", result=analysis)
        logger.info("Demo task completed: %s (agent=%s, gpt4o=%s)", spec["description"][:50], agent, bool(gpt_response))

    def start(self) -> None:
        """Start the demo loop as a background asyncio task."""
        if self._running or (self._task is not None and not self._task.done()):
            return  # already running
        self._running = True
        self._task = asyncio.create_task(self.run())

    def stop(self) -> None:
        """Stop the demo loop."""
        self._running = False
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task = None

    def status(self) -> dict[str, Any]:
        """Return current demo runner status."""
        return {
            "running": self._running,
            "tasks_submitted": self._tasks_submitted,
            "next_task_index": self._task_index,
            "interval_seconds": self.interval,
        }
