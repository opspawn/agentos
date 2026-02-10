"""Sequential workflow: Research -> CEO -> Builder -> Deploy.

Implements a pipeline where each agent processes in order, passing results forward.
"""

from __future__ import annotations

import time

from agent_framework import ChatAgent, SequentialBuilder, Workflow

from src.agents.ceo_agent import create_ceo_agent
from src.agents.builder_agent import create_builder_agent
from src.agents.research_agent import create_research_agent
from src.metrics.collector import get_metrics_collector


def create_sequential_workflow(
    ceo: ChatAgent | None = None,
    builder: ChatAgent | None = None,
    research: ChatAgent | None = None,
    chat_client=None,
) -> Workflow:
    """Create a sequential Research -> CEO -> Builder workflow.

    This pipeline:
    1. Research agent gathers information about the task
    2. CEO agent analyzes findings and creates an execution plan
    3. Builder agent implements the plan

    Args:
        ceo: Optional pre-created CEO agent
        builder: Optional pre-created Builder agent
        research: Optional pre-created Research agent
        chat_client: Optional shared chat client for all agents
    """
    if research is None:
        research = create_research_agent(chat_client)
    if ceo is None:
        ceo = create_ceo_agent(chat_client)
    if builder is None:
        builder = create_builder_agent(chat_client)

    workflow = (
        SequentialBuilder()
        .participants([research, ceo, builder])
        .build()
    )

    return workflow


async def run_sequential(task: str, chat_client=None) -> dict:
    """Run the sequential workflow with a task.

    Args:
        task: The task description to process
        chat_client: Optional shared chat client

    Returns:
        Dict with workflow result
    """
    workflow = create_sequential_workflow(chat_client=chat_client)
    t0 = time.time()
    result = await workflow.run(task)
    elapsed_ms = (time.time() - t0) * 1000
    outputs = result.get_outputs()
    output_text = _extract_output_text(outputs)

    # Record metrics
    status = str(result.get_final_state())
    mc = get_metrics_collector()
    mc.update_metrics({
        "task_id": task[:32],
        "agent_id": "sequential",
        "task_type": "sequential",
        "status": "success" if "complete" in status.lower() else "failure",
        "cost_usdc": 0.0,
        "latency_ms": elapsed_ms,
    })

    return {
        "workflow": "sequential",
        "task": task,
        "status": status,
        "output": output_text,
    }


def _extract_output_text(outputs: list) -> str:
    """Extract readable text from workflow outputs."""
    parts: list[str] = []
    for item in outputs:
        if isinstance(item, list):
            for msg in item:
                if hasattr(msg, "text") and msg.text:
                    parts.append(msg.text)
        elif hasattr(item, "text") and item.text:
            parts.append(item.text)
        else:
            parts.append(str(item))
    return "\n".join(parts)
