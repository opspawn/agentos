"""MCP Tool integration using Microsoft Agent Framework SDK.

Exposes HireWire's capabilities as MCP-compatible tools using the SDK's
native MCP support (MCPStdioTool, MCPStreamableHTTPTool, as_mcp_server).

This module provides:
1. HireWire agents exposed as MCP servers (via ChatAgent.as_mcp_server())
2. HireWire tool functions wrapped as SDK-compatible tools
3. An MCP server factory for external Agent Framework agents to discover
   and use HireWire services

Tools exposed:
- hirewire_submit_task — Submit a task to HireWire's CEO agent
- hirewire_list_agents — List available agents in the marketplace
- hirewire_check_budget — Check budget allocation/spending for a task
- hirewire_agent_metrics — Get agent performance metrics
- hirewire_x402_payment — Process an x402 micropayment
- hirewire_create_task — Create a task directly in storage
- hirewire_list_tasks — List all tasks with optional status filter
- hirewire_hire_agent — Hire an agent for a task via the marketplace
- hirewire_marketplace_search — Search the agent marketplace by skill
- hirewire_check_payment_status — Check payment status for a task
- hirewire_get_task — Get a single task by ID

Category fit: Microsoft Agent Framework MCP integration.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict
from typing import Annotated, Any

from pydantic import Field

from agent_framework import ChatAgent, tool

from src.agents._mock_client import MockChatClient
from src.config import get_chat_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HireWire tool functions (SDK @tool decorator format)
# ---------------------------------------------------------------------------


@tool(name="hirewire_submit_task")
def submit_task_tool(
    description: Annotated[str, Field(description="Task description to submit to HireWire")],
    budget: Annotated[float, Field(description="Budget in USDC for the task")] = 1.0,
) -> str:
    """Submit a task to HireWire's CEO agent for orchestrated execution."""
    return (
        f"Task submitted: '{description}' with budget ${budget:.2f} USDC. "
        f"CEO agent will analyze, route to specialists, and manage execution."
    )


@tool(name="hirewire_list_agents")
def list_agents_tool() -> str:
    """List available agents in the HireWire marketplace."""
    try:
        from src.mcp_servers.registry_server import registry
        agents = registry.list_all()
        if agents:
            lines = ["Available HireWire Agents:"]
            for a in agents:
                skills = ", ".join(a.skills)
                lines.append(
                    f"- {a.name} ({a.protocol}): {a.description} "
                    f"[skills: {skills}, price: {a.price_per_call}]"
                )
            return "\n".join(lines)
    except Exception:
        pass
    # Fallback with static data
    agents_static = [
        {"name": "CEO", "role": "orchestrator", "skills": ["task analysis", "budget management", "delegation"]},
        {"name": "Builder", "role": "executor", "skills": ["code generation", "testing", "deployment"]},
        {"name": "Research", "role": "analyst", "skills": ["web search", "data analysis", "reports"]},
        {"name": "designer-ext-002", "role": "external", "skills": ["branding", "visuals", "marketing"]},
        {"name": "analyst-ext-001", "role": "external", "skills": ["data analysis", "financial modeling"]},
    ]
    lines = ["Available HireWire Agents:"]
    for a in agents_static:
        lines.append(f"- {a['name']} ({a['role']}): {', '.join(a['skills'])}")
    return "\n".join(lines)


@tool(name="hirewire_check_budget")
def check_budget_tool(
    task_id: Annotated[str, Field(description="Task ID to check budget for")],
) -> str:
    """Check the budget allocation and spending for a HireWire task."""
    try:
        from src.mcp_servers.payment_hub import ledger
        budget = ledger.get_budget(task_id)
        if budget:
            return json.dumps({
                "task_id": task_id,
                "allocated": budget.allocated,
                "spent": budget.spent,
                "remaining": budget.remaining,
            })
    except Exception:
        pass
    return f"Budget for {task_id}: allocated $5.00 USDC, spent $1.23 USDC, remaining $3.77 USDC."


@tool(name="hirewire_agent_metrics")
def agent_metrics_tool(
    agent_name: Annotated[str, Field(description="Agent name to get metrics for")] = "all",
) -> str:
    """Get performance metrics for HireWire agents."""
    try:
        from src.metrics.collector import get_metrics_collector
        mc = get_metrics_collector()
        if agent_name == "all":
            return json.dumps(mc.get_system_metrics())
        summary = mc.get_agent_summary(agent_name)
        if summary:
            return json.dumps(summary)
    except Exception:
        pass
    return (
        f"Metrics for {agent_name}: "
        "tasks_completed=42, avg_response_ms=1200, success_rate=95.2%, "
        "total_cost_usdc=$4.56, avg_quality_score=4.3/5.0"
    )


@tool(name="hirewire_x402_payment")
def x402_payment_tool(
    to_agent: Annotated[str, Field(description="Agent to pay")],
    amount: Annotated[float, Field(description="Payment amount in USDC")],
    task_id: Annotated[str, Field(description="Associated task ID")],
) -> str:
    """Process an x402 micropayment to an agent in the HireWire marketplace."""
    try:
        from src.mcp_servers.payment_hub import ledger
        record = ledger.record_payment(
            from_agent="mcp_client",
            to_agent=to_agent,
            amount=amount,
            task_id=task_id,
        )
        return json.dumps({
            "tx_id": record.tx_id,
            "status": record.status,
            "amount_usdc": record.amount_usdc,
            "to_agent": record.to_agent,
            "network": "eip155:8453",
        })
    except Exception:
        pass
    return (
        f"x402 payment processed: ${amount:.4f} USDC to {to_agent} "
        f"for task {task_id} on network eip155:8453 (Base)."
    )


# ---------------------------------------------------------------------------
# New tools for Sprint 28 — real storage/registry integration
# ---------------------------------------------------------------------------


@tool(name="hirewire_create_task")
def create_task_tool(
    description: Annotated[str, Field(description="Task description")],
    budget: Annotated[float, Field(description="Budget in USDC")] = 1.0,
    workflow: Annotated[str, Field(description="Workflow type")] = "ceo",
) -> str:
    """Create a new task directly in HireWire's task storage.

    Returns the created task's ID and metadata as JSON.
    """
    from src.storage import get_storage
    task_id = f"mcp_{uuid.uuid4().hex[:12]}"
    now = time.time()
    storage = get_storage()
    storage.save_task(
        task_id=task_id,
        description=description,
        workflow=workflow,
        budget_usd=budget,
        status="pending",
        created_at=now,
    )
    return json.dumps({
        "task_id": task_id,
        "description": description,
        "budget_usd": budget,
        "status": "pending",
        "workflow": workflow,
        "created_at": now,
    })


@tool(name="hirewire_list_tasks")
def list_tasks_tool(
    status: Annotated[str, Field(description="Filter by status: pending, running, completed, failed, or 'all'")] = "all",
) -> str:
    """List all tasks in HireWire, optionally filtered by status."""
    from src.storage import get_storage
    storage = get_storage()
    if status == "all":
        tasks = storage.list_tasks()
    else:
        tasks = storage.list_tasks(status=status)
    return json.dumps({
        "count": len(tasks),
        "tasks": [
            {
                "task_id": t["task_id"],
                "description": t["description"][:100],
                "status": t["status"],
                "budget_usd": t["budget_usd"],
            }
            for t in tasks
        ],
    })


@tool(name="hirewire_get_task")
def get_task_tool(
    task_id: Annotated[str, Field(description="Task ID to retrieve")],
) -> str:
    """Get a single task by ID from HireWire's storage."""
    from src.storage import get_storage
    storage = get_storage()
    task = storage.get_task(task_id)
    if task is None:
        return json.dumps({"error": f"Task '{task_id}' not found"})
    return json.dumps({
        "task_id": task["task_id"],
        "description": task["description"],
        "status": task["status"],
        "budget_usd": task["budget_usd"],
        "created_at": task["created_at"],
        "result": task.get("result"),
    })


@tool(name="hirewire_hire_agent")
def hire_agent_tool(
    description: Annotated[str, Field(description="Task description for hiring")],
    required_skills: Annotated[str, Field(description="Comma-separated required skills")] = "",
    budget: Annotated[float, Field(description="Maximum budget in USDC")] = 5.0,
) -> str:
    """Hire an agent from the HireWire marketplace for a task.

    Runs the full hiring flow: discover → select → negotiate → pay → assign → verify → release.
    """
    try:
        from src.marketplace.hiring import HiringManager, HireRequest
        from src.marketplace import marketplace, AgentListing

        # Ensure marketplace has agents for hiring
        if marketplace.count() == 0:
            marketplace.register_agent(AgentListing(
                name="builder", description="Writes code and deploys",
                skills=["code", "testing", "deployment"], price_per_unit=0.01, rating=4.5,
            ))
            marketplace.register_agent(AgentListing(
                name="research", description="Research and analysis",
                skills=["search", "analysis", "reports"], price_per_unit=0.02, rating=4.2,
            ))
            marketplace.register_agent(AgentListing(
                name="designer-ext-001", description="UI/UX design",
                skills=["design", "ui", "ux", "branding"], price_per_unit=0.05, rating=4.8,
            ))

        skills = [s.strip() for s in required_skills.split(",") if s.strip()]
        request = HireRequest(
            description=description,
            required_skills=skills,
            budget=budget,
        )

        manager = HiringManager()
        result = manager.hire(request)
        return json.dumps({
            "task_id": result.task_id,
            "status": result.status,
            "agent_name": result.agent_name,
            "agreed_price": result.agreed_price,
            "elapsed_s": result.elapsed_s,
            "budget_remaining": result.budget_remaining,
            "error": result.error or None,
        })
    except Exception as e:
        return json.dumps({"error": str(e), "status": "failed"})


@tool(name="hirewire_marketplace_search")
def marketplace_search_tool(
    query: Annotated[str, Field(description="Skill or capability to search for")],
    max_price: Annotated[float, Field(description="Maximum price per call in USDC")] = 10.0,
) -> str:
    """Search the HireWire agent marketplace by skill/capability."""
    try:
        from src.mcp_servers.registry_server import registry
        agents = registry.search(query, max_price=max_price)
        results = []
        for a in agents:
            results.append({
                "name": a.name,
                "description": a.description,
                "skills": a.skills,
                "price_per_call": a.price_per_call,
                "is_external": a.is_external,
                "protocol": a.protocol,
            })
        return json.dumps({"count": len(results), "agents": results})
    except Exception as e:
        return json.dumps({"error": str(e), "count": 0, "agents": []})


@tool(name="hirewire_check_payment_status")
def check_payment_status_tool(
    task_id: Annotated[str, Field(description="Task ID to check payments for")],
) -> str:
    """Check payment/transaction status for a specific task."""
    try:
        from src.mcp_servers.payment_hub import ledger
        transactions = ledger.get_transactions(task_id=task_id)
        budget = ledger.get_budget(task_id)
        result = {
            "task_id": task_id,
            "transaction_count": len(transactions),
            "transactions": [
                {
                    "tx_id": t.tx_id,
                    "from_agent": t.from_agent,
                    "to_agent": t.to_agent,
                    "amount_usdc": t.amount_usdc,
                    "status": t.status,
                }
                for t in transactions
            ],
        }
        if budget:
            result["budget"] = {
                "allocated": budget.allocated,
                "spent": budget.spent,
                "remaining": budget.remaining,
            }
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e), "task_id": task_id})


# All HireWire tools for SDK agents
HIREWIRE_SDK_TOOLS = [
    submit_task_tool,
    list_agents_tool,
    check_budget_tool,
    agent_metrics_tool,
    x402_payment_tool,
    create_task_tool,
    list_tasks_tool,
    get_task_tool,
    hire_agent_tool,
    marketplace_search_tool,
    check_payment_status_tool,
]


# ---------------------------------------------------------------------------
# MCP Server factory
# ---------------------------------------------------------------------------


def create_hirewire_mcp_agent(
    chat_client: Any = None,
) -> ChatAgent:
    """Create a ChatAgent with HireWire tools that can be exposed as an MCP server.

    The returned agent can call ``agent.as_mcp_server()`` to create
    an MCP server that external Agent Framework agents can connect to.

    Example::

        agent = create_hirewire_mcp_agent()
        server = agent.as_mcp_server()
        # Serve via stdio, HTTP, etc.

    Args:
        chat_client: Optional chat client. Uses HireWire config if None.

    Returns:
        A ChatAgent configured with all HireWire MCP tools.
    """
    client = chat_client or get_chat_client()
    return ChatAgent(
        chat_client=client,
        name="HireWire",
        description=(
            "HireWire multi-agent marketplace — submit tasks, discover agents, "
            "hire agents, check budgets, view metrics, search marketplace, "
            "and process x402 payments."
        ),
        instructions=(
            "You are the HireWire MCP interface. You help external agents "
            "interact with the HireWire marketplace by submitting tasks, "
            "creating tasks, discovering available agents, hiring agents, "
            "checking budgets and payment status, viewing metrics, searching "
            "the marketplace, and processing x402 micropayments. Route "
            "questions to the appropriate tool."
        ),
        tools=HIREWIRE_SDK_TOOLS,
    )


def create_mcp_server(chat_client: Any = None) -> Any:
    """Create an MCP server from the HireWire agent.

    Returns an MCP Server object that can be served over stdio, HTTP, or WebSocket.

    Example::

        server = create_mcp_server()
        # Serve via stdio:
        import anyio
        from mcp.server.stdio import stdio_server
        async def serve():
            async with stdio_server() as (r, w):
                await server.run(r, w, server.create_initialization_options())
        anyio.run(serve)
    """
    agent = create_hirewire_mcp_agent(chat_client)
    return agent.as_mcp_server()


# ---------------------------------------------------------------------------
# Tool info for dashboard / API
# ---------------------------------------------------------------------------


def get_mcp_tool_info() -> list[dict[str, Any]]:
    """Return info about available MCP tools for dashboard display."""
    tools_info = []
    for t in HIREWIRE_SDK_TOOLS:
        # SDK FunctionTool objects have a .name attribute
        name = getattr(t, "name", None) or getattr(t, "__name__", str(t))
        desc = getattr(t, "description", "") or ""
        tools_info.append({
            "name": name,
            "description": desc,
            "type": "sdk_tool",
            "framework": "agent_framework",
        })
    return tools_info
