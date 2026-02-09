"""A2A (Agent-to-Agent) Protocol Server for AgentOS.

Implements a JSON-RPC 2.0 endpoint following Google A2A spec patterns,
enabling external agents to discover and invoke AgentOS internal agents.

Endpoints:
- POST /a2a          — JSON-RPC 2.0 dispatch (tasks/send, tasks/get, agents/list)
- GET  /.well-known/agent.json — Agent card for A2A discovery
- GET  /a2a/health   — Health check

Uses the existing agent registry and payment hub for routing and billing.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.mcp_servers.registry_server import registry, AgentCard
from src.mcp_servers.payment_hub import ledger


# ---------------------------------------------------------------------------
# A2A Task State
# ---------------------------------------------------------------------------

class A2ATaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class A2ATask:
    """An A2A protocol task submitted by an external agent."""

    task_id: str
    agent_name: str
    description: str
    from_agent: str
    status: A2ATaskStatus = A2ATaskStatus.PENDING
    created_at: float = field(default_factory=time.time)
    result: dict[str, Any] | None = None
    x402_payment: str = ""


class A2ATaskStore:
    """In-memory store for A2A tasks."""

    def __init__(self) -> None:
        self._tasks: dict[str, A2ATask] = {}
        self._counter: int = 0

    def create_task(
        self,
        agent_name: str,
        description: str,
        from_agent: str = "anonymous",
        x402_payment: str = "",
    ) -> A2ATask:
        self._counter += 1
        task_id = f"a2a_{uuid.uuid4().hex[:8]}"
        task = A2ATask(
            task_id=task_id,
            agent_name=agent_name,
            description=description,
            from_agent=from_agent,
            x402_payment=x402_payment,
        )
        self._tasks[task_id] = task
        return task

    def get_task(self, task_id: str) -> A2ATask | None:
        return self._tasks.get(task_id)

    def list_tasks(self, agent_name: str | None = None) -> list[A2ATask]:
        tasks = list(self._tasks.values())
        if agent_name:
            tasks = [t for t in tasks if t.agent_name == agent_name]
        return tasks

    def clear(self) -> None:
        self._tasks.clear()
        self._counter = 0


# Global task store
task_store = A2ATaskStore()


# ---------------------------------------------------------------------------
# Agent Card Generation
# ---------------------------------------------------------------------------

def generate_agent_card(base_url: str = "") -> dict[str, Any]:
    """Generate the A2A agent card reflecting all registered agents."""
    agents = registry.list_all()
    skills = []
    for agent in agents:
        for skill in agent.skills:
            if skill not in skills:
                skills.append(skill)

    internal_agents = [a for a in agents if not a.is_external]
    agent_summaries = []
    for agent in internal_agents:
        agent_summaries.append({
            "name": agent.name,
            "description": agent.description,
            "skills": agent.skills,
        })

    return {
        "name": "AgentOS",
        "description": "Autonomous Agent Operating System with multi-agent orchestration and x402 micropayments",
        "version": "0.1.0",
        "url": base_url or "http://localhost:8080",
        "protocols": ["a2a", "json-rpc-2.0", "x402"],
        "skills": skills,
        "agents": agent_summaries,
        "pricing": {
            "model": "per-task",
            "currency": "USDC",
            "internal_agents": "free",
            "external_agents": "varies",
        },
        "authentication": {
            "schemes": ["x402", "none"],
        },
        "endpoints": {
            "jsonrpc": "/a2a",
            "agent_card": "/.well-known/agent.json",
            "health": "/a2a/health",
        },
    }


# ---------------------------------------------------------------------------
# Task Routing
# ---------------------------------------------------------------------------

def route_task_to_agent(agent_name: str, description: str) -> dict[str, Any]:
    """Route a task to the named agent and return a simulated result.

    In a production system this would invoke the actual agent via the
    workflow engine.  For now we return a structured mock result that
    reflects what the agent *would* produce.
    """
    agent = registry.get(agent_name)
    if agent is None:
        return {"error": f"Agent '{agent_name}' not found"}

    if agent.protocol == "internal":
        # Simulate internal agent execution
        return {
            "agent": agent_name,
            "description": agent.description,
            "output": f"Task processed by internal agent '{agent_name}': {description}",
            "skills_used": agent.skills,
        }

    # External agent — would normally HTTP POST to agent.endpoint
    return {
        "agent": agent_name,
        "description": agent.description,
        "output": f"Task routed to external agent '{agent_name}' at {agent.endpoint}",
        "endpoint": agent.endpoint,
        "protocol": agent.protocol,
    }


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 Handler
# ---------------------------------------------------------------------------

# Error codes per JSON-RPC 2.0 spec
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


def _jsonrpc_error(code: int, message: str, req_id: Any = None) -> dict:
    return {
        "jsonrpc": "2.0",
        "error": {"code": code, "message": message},
        "id": req_id,
    }


def _jsonrpc_result(result: Any, req_id: Any = None) -> dict:
    return {
        "jsonrpc": "2.0",
        "result": result,
        "id": req_id,
    }


def handle_tasks_send(params: dict[str, Any]) -> dict[str, Any]:
    """Handle tasks/send — submit a task to an AgentOS agent."""
    agent_name = params.get("agent")
    description = params.get("description")
    from_agent = params.get("from_agent", "anonymous")
    x402_payment = params.get("x402_payment", "")

    if not agent_name:
        return {"error": "Missing required parameter: 'agent'"}
    if not description:
        return {"error": "Missing required parameter: 'description'"}

    # Verify agent exists
    agent = registry.get(agent_name)
    if agent is None:
        return {"error": f"Unknown agent: '{agent_name}'"}

    # Create and execute task
    task = task_store.create_task(
        agent_name=agent_name,
        description=description,
        from_agent=from_agent,
        x402_payment=x402_payment,
    )

    # Route to the agent
    task.status = A2ATaskStatus.RUNNING
    result = route_task_to_agent(agent_name, description)

    if "error" in result:
        task.status = A2ATaskStatus.FAILED
        task.result = result
    else:
        task.status = A2ATaskStatus.COMPLETED
        task.result = result

    return {
        "task_id": task.task_id,
        "status": task.status.value,
        "agent": agent_name,
        "result": task.result,
        "created_at": task.created_at,
    }


def handle_tasks_get(params: dict[str, Any]) -> dict[str, Any]:
    """Handle tasks/get — check task status."""
    task_id = params.get("task_id")
    if not task_id:
        return {"error": "Missing required parameter: 'task_id'"}

    task = task_store.get_task(task_id)
    if task is None:
        return {"error": f"Task not found: '{task_id}'"}

    return {
        "task_id": task.task_id,
        "agent": task.agent_name,
        "status": task.status.value,
        "description": task.description,
        "from_agent": task.from_agent,
        "created_at": task.created_at,
        "result": task.result,
    }


def handle_agents_list(params: dict[str, Any]) -> dict[str, Any]:
    """Handle agents/list — list available agents and their skills."""
    capability = params.get("capability")
    include_external = params.get("include_external", True)

    if capability:
        agents = registry.search(capability)
    else:
        agents = registry.list_all()

    if not include_external:
        agents = [a for a in agents if not a.is_external]

    return {
        "total": len(agents),
        "agents": [
            {
                "name": a.name,
                "description": a.description,
                "skills": a.skills,
                "price_per_call": a.price_per_call,
                "protocol": a.protocol,
                "is_external": a.is_external,
            }
            for a in agents
        ],
    }


# Method dispatch table
_METHODS = {
    "tasks/send": handle_tasks_send,
    "tasks/get": handle_tasks_get,
    "agents/list": handle_agents_list,
}


def dispatch_jsonrpc(request_body: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a JSON-RPC 2.0 request to the appropriate handler."""
    # Validate JSON-RPC envelope
    if not isinstance(request_body, dict):
        return _jsonrpc_error(INVALID_REQUEST, "Request must be a JSON object")

    jsonrpc = request_body.get("jsonrpc")
    if jsonrpc != "2.0":
        return _jsonrpc_error(
            INVALID_REQUEST,
            "Invalid or missing 'jsonrpc' field (must be '2.0')",
            request_body.get("id"),
        )

    method = request_body.get("method")
    req_id = request_body.get("id")
    params = request_body.get("params", {})

    if not method or not isinstance(method, str):
        return _jsonrpc_error(INVALID_REQUEST, "Missing or invalid 'method' field", req_id)

    if not isinstance(params, dict):
        return _jsonrpc_error(INVALID_PARAMS, "'params' must be an object", req_id)

    handler = _METHODS.get(method)
    if handler is None:
        return _jsonrpc_error(
            METHOD_NOT_FOUND,
            f"Method not found: '{method}'",
            req_id,
        )

    try:
        result = handler(params)
        return _jsonrpc_result(result, req_id)
    except Exception as exc:
        return _jsonrpc_error(INTERNAL_ERROR, str(exc), req_id)


# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------

def create_a2a_app(base_url: str = "") -> FastAPI:
    """Create the A2A protocol server as a FastAPI application."""
    app = FastAPI(
        title="AgentOS A2A Server",
        description="A2A (Agent-to-Agent) protocol endpoint for AgentOS",
        version="0.1.0",
    )

    @app.get("/.well-known/agent.json")
    async def agent_card():
        """A2A agent card discovery endpoint."""
        return generate_agent_card(base_url)

    @app.post("/a2a")
    async def jsonrpc_endpoint(request: Request):
        """JSON-RPC 2.0 endpoint for A2A protocol methods."""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                content=_jsonrpc_error(PARSE_ERROR, "Invalid JSON"),
                status_code=200,  # JSON-RPC always returns 200
            )

        # Handle batch requests
        if isinstance(body, list):
            if not body:
                return JSONResponse(
                    content=_jsonrpc_error(INVALID_REQUEST, "Empty batch request"),
                    status_code=200,
                )
            responses = [dispatch_jsonrpc(req) for req in body]
            return JSONResponse(content=responses, status_code=200)

        response = dispatch_jsonrpc(body)
        return JSONResponse(content=response, status_code=200)

    @app.get("/a2a/health")
    async def health():
        """Health check for the A2A server."""
        return {
            "status": "healthy",
            "protocol": "a2a",
            "version": "0.1.0",
            "agents_available": len(registry.list_all()),
            "tasks_processed": len(task_store.list_tasks()),
        }

    return app
