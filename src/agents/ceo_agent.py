"""CEO Agent - The orchestrator that analyzes tasks, manages budget, and delegates work.

Uses ChatAgent with tools for task analysis, budget checking, and agent hiring.
"""

from __future__ import annotations

import re
from typing import Any

from agent_framework import ChatAgent, tool

from src.config import get_chat_client, get_settings
from src.learning.feedback import FeedbackRecord, get_feedback_collector
from src.learning.scorer import AgentScorer
from src.learning.optimizer import HiringOptimizer
from src.mcp_servers.payment_hub import ledger
from src.mcp_servers.tool_server import tool_registry
from src.metrics.collector import get_metrics_collector
from src.metrics.analytics import CostAnalyzer, ROICalculator

CEO_INSTRUCTIONS = """You are the CEO Agent of HireWire, an autonomous agent operating system.

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

Available MCP tools (via Tool Server):
- Use discover_tools to find external tools by capability or tag
- Azure tools: resource checking, DevOps work items, Key Vault secrets
- Tools can be composed into workflows (chains of tools)

Decision framework:
- If the task is purely research, delegate to Research Agent
- If the task requires code, delegate to Builder Agent
- For complex tasks, use sequential (research first, then build) or parallel execution
- If an internal agent can't handle it, search the marketplace for an external agent
- Use discover_tools to find MCP tools that can augment agent capabilities
- Always check budget before hiring external agents

Learning & Feedback:
- After EVERY task completion, call record_task_feedback to log the outcome
- Before hiring, call get_hiring_recommendation to get data-driven suggestions
- The system uses Thompson sampling to balance proven agents vs exploring new ones
- Agent scores use exponential decay — recent performance matters more

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
    """Analyze a task and return a structured breakdown.

    Parses the task description to detect task types using keyword matching
    and returns appropriate subtask breakdowns with cost estimates.
    """
    try:
        desc_lower = task_description.lower()
        words = desc_lower.split()
        word_count = len(words)

        # Keyword sets for detecting task types
        research_keywords = {
            "search", "find", "compare", "analyze", "research", "investigate",
            "evaluate", "review", "assess", "study", "explore", "look",
            "report", "summarize", "survey", "benchmark", "discover",
        }
        build_keywords = {
            "build", "create", "implement", "deploy", "code", "write",
            "develop", "fix", "refactor", "test", "install", "setup",
            "configure", "migrate", "update", "upgrade", "ship", "launch",
        }

        has_research = any(kw in desc_lower for kw in research_keywords)
        has_build = any(kw in desc_lower for kw in build_keywords)

        # Determine task type and build subtasks
        subtasks: list[dict[str, Any]] = []

        if has_research and has_build:
            # Complex task: research first, then build
            subtasks = [
                {
                    "id": "research",
                    "description": f"Research phase: gather information for '{task_description}'",
                    "agent": "research",
                },
                {
                    "id": "build",
                    "description": f"Build phase: implement based on research for '{task_description}'",
                    "agent": "builder",
                },
            ]
            execution_order = "sequential"
        elif has_research:
            subtasks = [
                {
                    "id": "research",
                    "description": f"Research: {task_description}",
                    "agent": "research",
                },
            ]
            execution_order = "parallel"
        elif has_build:
            subtasks = [
                {
                    "id": "build",
                    "description": f"Build: {task_description}",
                    "agent": "builder",
                },
            ]
            execution_order = "parallel"
        else:
            # Default: treat as research + build sequential
            subtasks = [
                {
                    "id": "research",
                    "description": f"Research: {task_description}",
                    "agent": "research",
                },
                {
                    "id": "build",
                    "description": f"Build: {task_description}",
                    "agent": "builder",
                },
            ]
            execution_order = "sequential"

        # Estimate cost based on complexity (word count)
        if word_count <= 10:
            estimated_cost = 0.10
            complexity = "simple"
        elif word_count <= 30:
            estimated_cost = 0.25
            complexity = "moderate"
        elif word_count <= 60:
            estimated_cost = 0.50
            complexity = "complex"
        else:
            estimated_cost = 1.00
            complexity = "very_complex"

        # Scale cost by number of subtasks
        estimated_cost *= len(subtasks)

        return {
            "original_task": task_description,
            "subtasks": subtasks,
            "execution_order": execution_order,
            "estimated_cost": round(estimated_cost, 2),
            "complexity": complexity,
            "task_type": "research+build" if (has_research and has_build) else
                         "research" if has_research else
                         "build" if has_build else "general",
            "status": "planned",
        }
    except Exception as e:
        return {
            "original_task": task_description,
            "subtasks": [],
            "execution_order": "sequential",
            "estimated_cost": 0.0,
            "status": "error",
            "error": str(e),
        }


@tool(name="check_budget", description="Check remaining budget for the current task")
async def check_budget(task_id: str) -> dict[str, Any]:
    """Check budget allocation for a task using the real PaymentLedger."""
    try:
        budget = ledger.get_budget(task_id)
        if budget is None:
            return {
                "task_id": task_id,
                "allocated": 0.0,
                "spent": 0.0,
                "remaining": 0.0,
                "currency": "USDC",
                "message": f"No budget allocated for task '{task_id}'. Call allocate_budget first.",
            }
        return {
            "task_id": task_id,
            "allocated": budget.allocated,
            "spent": budget.spent,
            "remaining": budget.remaining,
            "currency": "USDC",
        }
    except Exception as e:
        return {
            "task_id": task_id,
            "error": f"Failed to check budget: {e}",
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


@tool(name="discover_tools", description="Discover available MCP tools by capability or tag")
async def discover_tools(query: str = "", tag: str = "") -> dict[str, Any]:
    """Search the MCP tool registry for available tools.

    Agents use this to find external tools they can invoke.
    Search by free-text query or by tag (e.g., 'azure', 'security').
    """
    from dataclasses import asdict

    try:
        if tag:
            tools = tool_registry.search_by_tag(tag)
        elif query:
            tools = tool_registry.search(query)
        else:
            tools = tool_registry.list_all()

        return {
            "tools_found": len(tools),
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "provider": t.provider,
                    "tags": t.tags,
                }
                for t in tools
            ],
        }
    except Exception as e:
        return {"tools_found": 0, "tools": [], "error": str(e)}


@tool(
    name="record_task_feedback",
    description="Record feedback after a task is completed to improve future hiring",
)
async def record_task_feedback(
    task_id: str,
    agent_id: str,
    outcome: str,
    quality_score: float,
    latency_ms: float = 0.0,
    cost_usdc: float = 0.0,
) -> dict[str, Any]:
    """Record feedback for a completed task.

    Called by the CEO after a sub-agent finishes work. This data feeds
    into the scoring and optimization systems.

    Args:
        task_id: Unique identifier of the completed task.
        agent_id: The agent that performed the work.
        outcome: "success", "partial", or "failure".
        quality_score: Quality rating from 0.0 to 1.0.
        latency_ms: How long the task took in milliseconds.
        cost_usdc: How much the task cost in USDC.
    """
    try:
        collector = get_feedback_collector()
        record = FeedbackRecord(
            task_id=task_id,
            agent_id=agent_id,
            outcome=outcome,
            quality_score=max(0.0, min(1.0, quality_score)),
            latency_ms=latency_ms,
            cost_usdc=cost_usdc,
        )
        collector.record_feedback(record)

        # Recompute the agent's score
        scorer = AgentScorer(collector)
        score = scorer.compute_score(agent_id)

        return {
            "status": "recorded",
            "task_id": task_id,
            "agent_id": agent_id,
            "outcome": outcome,
            "updated_score": score.composite_score,
            "confidence": score.confidence,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@tool(
    name="get_hiring_recommendation",
    description="Get an AI-optimized agent recommendation for a task",
)
async def get_hiring_recommendation(
    candidate_ids: str,
    skill: str = "",
    budget: float = 1.0,
) -> dict[str, Any]:
    """Recommend the best agent for a task using learning-based optimization.

    Uses Thompson sampling to balance exploiting proven agents with
    exploring undersampled ones.

    Args:
        candidate_ids: Comma-separated list of agent IDs to choose from.
        skill: Optional skill requirement for the task.
        budget: Maximum budget in USDC.
    """
    try:
        candidates = [c.strip() for c in candidate_ids.split(",") if c.strip()]
        if not candidates:
            return {"status": "error", "error": "No candidates provided"}

        collector = get_feedback_collector()
        optimizer = HiringOptimizer(collector)
        rec = optimizer.recommend_agent(candidates, skill=skill or None, budget=budget)

        if rec is None:
            return {"status": "no_recommendation", "candidates": candidates}

        return {
            "status": "recommended",
            "agent_id": rec.agent_id,
            "expected_score": rec.expected_score,
            "confidence_interval": [rec.confidence_lower, rec.confidence_upper],
            "reason": rec.reason,
            "is_exploration": rec.is_exploration,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@tool(
    name="check_metrics",
    description="Get system and agent performance metrics for data-driven hiring decisions",
)
async def check_metrics(agent_id: str = "") -> dict[str, Any]:
    """Check performance metrics. Optionally filter by agent_id.

    Returns system-wide metrics if no agent_id, or per-agent metrics otherwise.
    Also includes cost efficiency and best-value agents.
    """
    try:
        mc = get_metrics_collector()
        analyzer = CostAnalyzer()
        roi = ROICalculator()

        if agent_id:
            return {
                "status": "ok",
                "agent_metrics": mc.get_agent_metrics(agent_id),
                "roi": roi.best_value_agents(),
            }

        return {
            "status": "ok",
            "system_metrics": mc.get_system_metrics(),
            "efficiency": analyzer.efficiency_score(),
            "trend": analyzer.trend_analysis(),
            "best_value_agents": roi.best_value_agents(),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


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
        tools=[
            analyze_task,
            check_budget,
            approve_hire,
            discover_tools,
            record_task_feedback,
            get_hiring_recommendation,
            check_metrics,
        ],
    )
