"""CEO Agent - The orchestrator that analyzes tasks, manages budget, and delegates work.

Uses ChatAgent with tools for task analysis, budget checking, and agent hiring.
"""

from __future__ import annotations

from typing import Any

from agent_framework import ChatAgent, tool

from src.config import get_chat_client, get_settings

CEO_INSTRUCTIONS = """You are the CEO Agent of AgentOS, an autonomous agent operating system.

Your responsibilities:
1. **Task Analysis**: When a user submits a task, break it down into subtasks
   and determine which specialist agents are needed.
2. **Hiring Decisions**: Decide whether to use internal agents (Builder, Research)
   or hire external agents from the marketplace via x402 micropayments.
3. **Budget Management**: Track spending against budget constraints. Never exceed
   the allocated budget for a task.
4. **Quality Control**: Review results from sub-agents and determine if the task
   is complete or needs revision.
5. **Delegation**: Route subtasks to the appropriate agents with clear instructions.

Available internal agents:
- Builder Agent: Writes code, runs tests, deploys services
- Research Agent: Searches the web, analyzes data, produces reports

Decision framework:
- If the task is purely research, delegate to Research Agent
- If the task requires code, delegate to Builder Agent
- For complex tasks, use sequential (research first, then build) or parallel execution
- If an internal agent can't handle it, search the marketplace for an external agent
- Always check budget before hiring external agents

When you receive a task, respond with a structured plan:
1. Task breakdown (subtasks)
2. Agent assignments
3. Execution order (sequential/parallel)
4. Estimated cost (if external agents needed)
5. Success criteria
"""


# --- CEO Tools ---

@tool(name="analyze_task", description="Break down a task into subtasks with agent assignments")
async def analyze_task(task_description: str) -> dict[str, Any]:
    """Analyze a task and return a structured breakdown."""
    return {
        "original_task": task_description,
        "subtasks": [
            {"id": "research", "description": f"Research: {task_description}", "agent": "research"},
            {"id": "build", "description": f"Build: {task_description}", "agent": "builder"},
        ],
        "execution_order": "sequential",
        "estimated_cost": 0.0,
        "status": "planned",
    }


@tool(name="check_budget", description="Check remaining budget for the current task")
async def check_budget(task_id: str) -> dict[str, Any]:
    """Check budget allocation for a task."""
    # Placeholder - will be backed by real ledger
    return {
        "task_id": task_id,
        "allocated": 1.00,
        "spent": 0.00,
        "remaining": 1.00,
        "currency": "USDC",
    }


@tool(name="approve_hire", description="Approve hiring an external agent for a subtask")
async def approve_hire(
    agent_name: str,
    subtask_id: str,
    price: float,
    max_budget: float = 1.0,
) -> dict[str, Any]:
    """Approve or reject hiring an external agent based on budget."""
    if price > max_budget:
        return {
            "approved": False,
            "reason": f"Price ${price:.2f} exceeds budget ${max_budget:.2f}",
        }
    return {
        "approved": True,
        "agent": agent_name,
        "subtask_id": subtask_id,
        "price": price,
    }


def create_ceo_agent(chat_client=None) -> ChatAgent:
    """Create and return the CEO agent.

    Args:
        chat_client: Optional ChatClientProtocol instance. If None, creates one
                     from environment config.
    """
    if chat_client is None:
        chat_client = get_chat_client()

    return ChatAgent(
        chat_client=chat_client,
        name="CEO",
        description="Orchestrator agent that analyzes tasks, manages budget, and delegates work",
        instructions=CEO_INSTRUCTIONS,
        tools=[analyze_task, check_budget, approve_hire],
    )
