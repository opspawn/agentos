"""Group Chat workflow: CEO manages Builder + Research in collaborative discussion.

Implements a multi-agent group chat where the CEO orchestrates discussion
between specialist agents to solve complex tasks.
"""

from __future__ import annotations

from agent_framework import ChatAgent, GroupChatBuilder, Workflow

from src.agents.ceo_agent import create_ceo_agent
from src.agents.builder_agent import create_builder_agent
from src.agents.research_agent import create_research_agent
from src.workflows.sequential import _extract_output_text


def create_group_chat_workflow(
    ceo: ChatAgent | None = None,
    builder: ChatAgent | None = None,
    research: ChatAgent | None = None,
    max_rounds: int = 10,
    chat_client=None,
) -> Workflow:
    """Create a group chat workflow with CEO as orchestrator.

    The CEO agent manages the discussion, directing Research and Builder
    agents to collaborate on complex tasks. The CEO decides when the task
    is complete.

    Args:
        ceo: Optional pre-created CEO agent
        builder: Optional pre-created Builder agent
        research: Optional pre-created Research agent
        max_rounds: Maximum discussion rounds before termination
        chat_client: Optional shared chat client for all agents
    """
    if ceo is None:
        ceo = create_ceo_agent(chat_client)
    if builder is None:
        builder = create_builder_agent(chat_client)
    if research is None:
        research = create_research_agent(chat_client)

    workflow = (
        GroupChatBuilder()
        .participants([builder, research])
        .with_orchestrator(agent=ceo)
        .with_max_rounds(max_rounds)
        .build()
    )

    return workflow


async def run_group_chat(task: str, max_rounds: int = 10, chat_client=None) -> dict:
    """Run the group chat workflow.

    CEO coordinates Builder and Research agents in a collaborative
    discussion to solve the task.

    Args:
        task: The task description
        max_rounds: Maximum discussion rounds
        chat_client: Optional shared chat client

    Returns:
        Dict with group chat result
    """
    workflow = create_group_chat_workflow(
        max_rounds=max_rounds,
        chat_client=chat_client,
    )
    result = await workflow.run(task)
    outputs = result.get_outputs()
    return {
        "workflow": "group_chat",
        "task": task,
        "max_rounds": max_rounds,
        "status": str(result.get_final_state()),
        "output": _extract_output_text(outputs),
    }
