"""Standalone MCP server entry point for HireWire.

Exposes HireWire's task management, agent hiring, marketplace, and x402
payment capabilities as MCP tools that external agents can discover and use.

Supports both stdio and SSE transports:

    # stdio (default) — for local MCP clients like Claude Desktop
    python -m src.mcp_server

    # SSE — for remote MCP clients over HTTP
    python -m src.mcp_server --transport sse --port 8090

Uses the native ``mcp`` library (not the SDK wrapper) so the server works
with any MCP-compatible client regardless of framework.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
import uuid
from typing import Any

from mcp.server import Server
from mcp.types import TextContent, Tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool definitions — each maps to a HireWire capability
# ---------------------------------------------------------------------------

MCP_TOOLS: list[Tool] = [
    Tool(
        name="create_task",
        description="Create a new task in HireWire's task engine.",
        inputSchema={
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "Task description"},
                "budget": {"type": "number", "description": "Budget in USDC", "default": 1.0},
                "workflow": {"type": "string", "description": "Workflow type", "default": "ceo"},
            },
            "required": ["description"],
        },
    ),
    Tool(
        name="get_task",
        description="Retrieve a task by its ID.",
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "The task ID to look up"},
            },
            "required": ["task_id"],
        },
    ),
    Tool(
        name="list_tasks",
        description="List tasks, optionally filtered by status.",
        inputSchema={
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Filter: pending, running, completed, failed, or 'all'",
                    "default": "all",
                },
            },
        },
    ),
    Tool(
        name="hire_agent",
        description="Hire an agent from the marketplace for a task. Runs the full 7-step hiring flow.",
        inputSchema={
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "Task description"},
                "required_skills": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Skills the agent must have",
                    "default": [],
                },
                "budget": {"type": "number", "description": "Max USDC budget", "default": 5.0},
            },
            "required": ["description"],
        },
    ),
    Tool(
        name="list_agents",
        description="List all registered agents in the HireWire marketplace.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="marketplace_search",
        description="Search agents by skill or capability.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Skill or capability to search for"},
                "max_price": {"type": "number", "description": "Maximum price in USDC", "default": 10.0},
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="check_budget",
        description="Check budget allocation and spending for a task.",
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID"},
            },
            "required": ["task_id"],
        },
    ),
    Tool(
        name="check_payment_status",
        description="Check payment/transaction status for a task.",
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID"},
            },
            "required": ["task_id"],
        },
    ),
    Tool(
        name="pay_agent",
        description="Process an x402 micropayment to an agent.",
        inputSchema={
            "type": "object",
            "properties": {
                "to_agent": {"type": "string", "description": "Agent to pay"},
                "amount": {"type": "number", "description": "Amount in USDC"},
                "task_id": {"type": "string", "description": "Associated task ID"},
            },
            "required": ["to_agent", "amount", "task_id"],
        },
    ),
    Tool(
        name="get_metrics",
        description="Get system-wide or per-agent performance metrics.",
        inputSchema={
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Agent name, or 'all' for system metrics",
                    "default": "all",
                },
            },
        },
    ),
]


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------


def _handle_create_task(arguments: dict[str, Any]) -> str:
    from src.storage import get_storage
    task_id = f"mcp_{uuid.uuid4().hex[:12]}"
    now = time.time()
    storage = get_storage()
    storage.save_task(
        task_id=task_id,
        description=arguments["description"],
        workflow=arguments.get("workflow", "ceo"),
        budget_usd=arguments.get("budget", 1.0),
        status="pending",
        created_at=now,
    )
    return json.dumps({
        "task_id": task_id,
        "description": arguments["description"],
        "budget_usd": arguments.get("budget", 1.0),
        "status": "pending",
        "created_at": now,
    })


def _handle_get_task(arguments: dict[str, Any]) -> str:
    from src.storage import get_storage
    task = get_storage().get_task(arguments["task_id"])
    if task is None:
        return json.dumps({"error": f"Task '{arguments['task_id']}' not found"})
    return json.dumps({
        "task_id": task["task_id"],
        "description": task["description"],
        "status": task["status"],
        "budget_usd": task["budget_usd"],
        "created_at": task["created_at"],
        "result": task.get("result"),
    })


def _handle_list_tasks(arguments: dict[str, Any]) -> str:
    from src.storage import get_storage
    status = arguments.get("status", "all")
    storage = get_storage()
    tasks = storage.list_tasks() if status == "all" else storage.list_tasks(status=status)
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


def _handle_hire_agent(arguments: dict[str, Any]) -> str:
    from src.marketplace.hiring import HiringManager, HireRequest
    from src.marketplace import marketplace, AgentListing

    if marketplace.count() == 0:
        marketplace.register_agent(AgentListing(
            name="builder", description="Writes code and deploys",
            skills=["code", "testing", "deployment"], price_per_unit=0.01, rating=4.5,
        ))
        marketplace.register_agent(AgentListing(
            name="research", description="Research and analysis",
            skills=["search", "analysis", "reports"], price_per_unit=0.02, rating=4.2,
        ))

    request = HireRequest(
        description=arguments["description"],
        required_skills=arguments.get("required_skills", []),
        budget=arguments.get("budget", 5.0),
    )
    manager = HiringManager()
    result = manager.hire(request)
    return json.dumps({
        "task_id": result.task_id,
        "status": result.status,
        "agent_name": result.agent_name,
        "agreed_price": result.agreed_price,
        "elapsed_s": result.elapsed_s,
        "error": result.error or None,
    })


def _handle_list_agents(arguments: dict[str, Any]) -> str:
    from src.mcp_servers.registry_server import registry
    from dataclasses import asdict
    agents = registry.list_all()
    return json.dumps([asdict(a) for a in agents], indent=2)


def _handle_marketplace_search(arguments: dict[str, Any]) -> str:
    from src.mcp_servers.registry_server import registry
    from dataclasses import asdict
    agents = registry.search(arguments["query"], max_price=arguments.get("max_price"))
    return json.dumps({
        "count": len(agents),
        "agents": [asdict(a) for a in agents],
    })


def _handle_check_budget(arguments: dict[str, Any]) -> str:
    from src.mcp_servers.payment_hub import ledger
    budget = ledger.get_budget(arguments["task_id"])
    if budget is None:
        return json.dumps({"error": "No budget allocated for this task"})
    return json.dumps({
        "task_id": budget.task_id,
        "allocated": budget.allocated,
        "spent": budget.spent,
        "remaining": budget.remaining,
    })


def _handle_check_payment_status(arguments: dict[str, Any]) -> str:
    from src.mcp_servers.payment_hub import ledger
    task_id = arguments["task_id"]
    transactions = ledger.get_transactions(task_id=task_id)
    budget = ledger.get_budget(task_id)
    result: dict[str, Any] = {
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


def _handle_pay_agent(arguments: dict[str, Any]) -> str:
    from src.mcp_servers.payment_hub import ledger
    record = ledger.record_payment(
        from_agent="mcp_client",
        to_agent=arguments["to_agent"],
        amount=arguments["amount"],
        task_id=arguments["task_id"],
    )
    return json.dumps({
        "tx_id": record.tx_id,
        "status": record.status,
        "amount_usdc": record.amount_usdc,
        "to_agent": record.to_agent,
        "network": "eip155:8453",
    })


def _handle_get_metrics(arguments: dict[str, Any]) -> str:
    try:
        from src.metrics.collector import get_metrics_collector
        mc = get_metrics_collector()
        agent_name = arguments.get("agent_name", "all")
        if agent_name == "all":
            return json.dumps(mc.get_system_metrics())
        summary = mc.get_agent_summary(agent_name)
        return json.dumps(summary) if summary else json.dumps({"error": f"No metrics for {agent_name}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# Dispatcher
_HANDLERS: dict[str, Any] = {
    "create_task": _handle_create_task,
    "get_task": _handle_get_task,
    "list_tasks": _handle_list_tasks,
    "hire_agent": _handle_hire_agent,
    "list_agents": _handle_list_agents,
    "marketplace_search": _handle_marketplace_search,
    "check_budget": _handle_check_budget,
    "check_payment_status": _handle_check_payment_status,
    "pay_agent": _handle_pay_agent,
    "get_metrics": _handle_get_metrics,
}


# ---------------------------------------------------------------------------
# MCP Server factory
# ---------------------------------------------------------------------------


def create_hirewire_mcp_server() -> Server:
    """Create a native MCP server with all HireWire tools registered.

    This server can be served over stdio or SSE and is compatible with
    any MCP client (Claude Desktop, Agent Framework MCPStdioTool, etc.).
    """
    server = Server("hirewire")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return MCP_TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        handler = _HANDLERS.get(name)
        if handler is None:
            return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]
        try:
            result = handler(arguments)
            return [TextContent(type="text", text=result)]
        except Exception as e:
            logger.exception("Tool %s failed", name)
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    return server


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


async def _run_stdio(server: Server) -> None:
    """Run the MCP server over stdio transport."""
    from mcp.server.stdio import stdio_server
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


async def _run_sse(server: Server, host: str, port: int) -> None:
    """Run the MCP server over SSE transport."""
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Route
    import uvicorn

    sse = SseServerTransport("/messages")

    async def handle_sse(request):
        async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await server.run(streams[0], streams[1], server.create_initialization_options())

    async def handle_messages(request):
        await sse.handle_post_message(request.scope, request.receive, request._send)

    app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Route("/messages", endpoint=handle_messages, methods=["POST"]),
        ],
    )

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    srv = uvicorn.Server(config)
    await srv.serve()


def main() -> None:
    """CLI entry point for ``python -m src.mcp_server``."""
    parser = argparse.ArgumentParser(description="HireWire MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport protocol (default: stdio)",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Host for SSE transport")
    parser.add_argument("--port", type=int, default=8090, help="Port for SSE transport")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    server = create_hirewire_mcp_server()

    if args.transport == "stdio":
        asyncio.run(_run_stdio(server))
    else:
        asyncio.run(_run_sse(server, args.host, args.port))


if __name__ == "__main__":
    main()
