"""Concurrent workflow: Parallel independent tasks.

Runs multiple agents simultaneously for independent subtasks,
then aggregates results.
"""

from __future__ import annotations

from agent_framework import ChatAgent, ConcurrentBuilder, Workflow

from src.agents.builder_agent import create_builder_agent
from src.agents.research_agent import create_research_agent
from src.workflows.sequential import _extract_output_text


def create_concurrent_workflow(
    agents: list[ChatAgent] | None = None,
    chat_client=None,
) -> Workflow:
    """Create a concurrent workflow for parallel execution.

    Default setup runs Research and Builder in parallel for tasks
    where they're independent (e.g., research docs while building scaffold).

    Args:
        agents: Optional list of agents to run concurrently
        chat_client: Optional shared chat client for all agents
    """
    if agents is None:
        agents = [
            create_research_agent(chat_client),
            create_builder_agent(chat_client),
        ]

    workflow = (
        ConcurrentBuilder()
        .participants(agents)
        .build()
    )

    return workflow


async def run_concurrent(task: str, chat_client=None) -> dict:
    """Run parallel agents on the same task.

    Each agent processes the task independently. Results are
    aggregated when all complete.

    Args:
        task: The task description (sent to all agents)
        chat_client: Optional shared chat client

    Returns:
        Dict with aggregated results
    """
    workflow = create_concurrent_workflow(chat_client=chat_client)
    result = await workflow.run(task)
    outputs = result.get_outputs()
    return {
        "workflow": "concurrent",
        "task": task,
        "status": str(result.get_final_state()),
        "output": _extract_output_text(outputs),
    }
