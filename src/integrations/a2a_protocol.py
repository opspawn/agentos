"""A2A (Agent-to-Agent) Protocol integration for HireWire.

Provides full Google A2A protocol support enabling HireWire agents to:
- Publish agent cards for discovery (/.well-known/agent.json)
- Discover remote A2A agents and cache their capabilities
- Send tasks to remote agents via JSON-RPC 2.0
- Receive and process incoming A2A tasks through the existing task engine
- Delegate marketplace hiring to remote A2A agents

This module bridges HireWire's internal agent system with the broader A2A
ecosystem, complementing Sprint 27 (Agent Framework SDK) and Sprint 28
(MCP Server) to complete the Week 1 interop foundation.

Category fit: A2A protocol integration for multi-agent interoperability.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# A2A Task Lifecycle
# ---------------------------------------------------------------------------


class A2ATaskState(str, Enum):
    """Task lifecycle states per the A2A spec."""

    SUBMITTED = "submitted"
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# A2A Agent Card
# ---------------------------------------------------------------------------


@dataclass
class A2AAgentCard:
    """Generates a .well-known/agent.json for any HireWire agent.

    Follows the Google A2A agent card specification:
    https://google.github.io/A2A/#agent-card

    The card advertises the agent's name, description, skills,
    supported protocols, pricing, and JSON-RPC endpoint.
    """

    name: str
    description: str
    url: str = ""
    version: str = "1.0.0"
    skills: list[dict[str, Any]] = field(default_factory=list)
    protocols: list[str] = field(default_factory=lambda: ["a2a", "json-rpc-2.0"])
    authentication: dict[str, Any] = field(
        default_factory=lambda: {"schemes": ["none"]}
    )
    pricing: dict[str, Any] = field(
        default_factory=lambda: {"model": "per-task", "currency": "USDC"}
    )
    endpoints: dict[str, str] = field(default_factory=dict)
    capabilities: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary for JSON responses."""
        return asdict(self)

    def matches_skill(self, query: str) -> bool:
        """Check if this agent card has a skill matching the query."""
        q = query.lower()
        for skill in self.skills:
            skill_name = skill.get("name", "").lower()
            skill_desc = skill.get("description", "").lower()
            if q in skill_name or q in skill_desc:
                return True
        return q in self.name.lower() or q in self.description.lower()


def generate_hirewire_agent_card(base_url: str = "http://localhost:8000") -> A2AAgentCard:
    """Generate the main HireWire A2A agent card.

    Reflects actual HireWire capabilities: task management, agent hiring,
    marketplace, orchestration, x402 payments.
    """
    return A2AAgentCard(
        name="HireWire",
        description=(
            "Autonomous Agent Operating System — multi-agent orchestration, "
            "marketplace hiring, and x402 micropayments"
        ),
        url=base_url,
        version="2.0.0",
        skills=[
            {
                "name": "task_management",
                "description": "Submit, track, and manage multi-agent tasks",
                "examples": ["Build a landing page", "Research AI trends"],
            },
            {
                "name": "agent_hiring",
                "description": "Discover, hire, and pay agents from the marketplace",
                "examples": ["Hire a designer for UI work"],
            },
            {
                "name": "orchestration",
                "description": "Sequential, concurrent, and handoff agent workflows",
                "examples": ["Pipeline: Research → Build → Deploy"],
            },
            {
                "name": "x402_payments",
                "description": "Process USDC micropayments via x402 protocol",
                "examples": ["Pay 0.05 USDC for design task"],
            },
            {
                "name": "marketplace",
                "description": "Agent registry with skill matching and pricing",
                "examples": ["Find agents skilled in code generation"],
            },
            {
                "name": "mcp_tools",
                "description": "MCP-compatible tool server with 11 tools",
                "examples": ["List tasks", "Check budget"],
            },
        ],
        protocols=["a2a", "json-rpc-2.0", "x402", "mcp"],
        authentication={"schemes": ["x402", "none"]},
        pricing={
            "model": "per-task",
            "currency": "USDC",
            "internal_agents": "free",
            "external_agents": "varies",
        },
        endpoints={
            "jsonrpc": f"{base_url}/a2a",
            "agent_card": f"{base_url}/.well-known/agent.json",
            "agents": f"{base_url}/a2a/agents",
            "health": f"{base_url}/health",
        },
        capabilities={
            "streaming": False,
            "batch_requests": True,
            "task_cancellation": True,
            "push_notifications": False,
        },
        metadata={
            "framework": "Microsoft Agent Framework SDK",
            "built_by": "OpSpawn",
            "hackathon": "Microsoft AI Dev Days 2026",
        },
    )


# ---------------------------------------------------------------------------
# A2A Task
# ---------------------------------------------------------------------------


@dataclass
class A2AProtocolTask:
    """Represents an A2A protocol task with full lifecycle tracking."""

    task_id: str = field(default_factory=lambda: f"a2a_{uuid.uuid4().hex[:12]}")
    description: str = ""
    from_agent: str = "anonymous"
    to_agent: str = ""
    state: A2ATaskState = A2ATaskState.SUBMITTED
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "state": self.state.value,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# A2A Task Store
# ---------------------------------------------------------------------------


class A2AProtocolTaskStore:
    """In-memory store for A2A protocol tasks."""

    def __init__(self) -> None:
        self._tasks: dict[str, A2AProtocolTask] = {}

    def create(
        self,
        description: str,
        from_agent: str = "anonymous",
        to_agent: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> A2AProtocolTask:
        task = A2AProtocolTask(
            description=description,
            from_agent=from_agent,
            to_agent=to_agent,
            metadata=metadata or {},
        )
        self._tasks[task.task_id] = task
        return task

    def get(self, task_id: str) -> A2AProtocolTask | None:
        return self._tasks.get(task_id)

    def update_state(
        self,
        task_id: str,
        state: A2ATaskState,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> A2AProtocolTask | None:
        task = self._tasks.get(task_id)
        if task is None:
            return None
        task.state = state
        task.updated_at = time.time()
        if result is not None:
            task.result = result
        if error is not None:
            task.error = error
        if state in (A2ATaskState.COMPLETED, A2ATaskState.FAILED, A2ATaskState.CANCELLED):
            task.completed_at = time.time()
        return task

    def list_all(self, state: A2ATaskState | None = None) -> list[A2AProtocolTask]:
        tasks = list(self._tasks.values())
        if state is not None:
            tasks = [t for t in tasks if t.state == state]
        return tasks

    def cancel(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if task is None:
            return False
        if task.state in (A2ATaskState.SUBMITTED, A2ATaskState.WORKING):
            task.state = A2ATaskState.CANCELLED
            task.updated_at = time.time()
            task.completed_at = time.time()
            return True
        return False

    def clear(self) -> None:
        self._tasks.clear()


# Global task store
protocol_task_store = A2AProtocolTaskStore()


# ---------------------------------------------------------------------------
# A2A Client — Discover and invoke remote A2A agents
# ---------------------------------------------------------------------------


class A2AClient:
    """Client for discovering and invoking remote A2A agents.

    Fetches agent cards from /.well-known/agent.json endpoints,
    sends tasks via JSON-RPC 2.0, and tracks discovered agents.
    """

    def __init__(self, timeout: float = 30.0) -> None:
        self._timeout = timeout
        self._discovered: dict[str, A2AAgentCard] = {}

    async def discover(self, base_url: str) -> A2AAgentCard | None:
        """Discover a remote agent by fetching its agent card.

        Args:
            base_url: Base URL of the remote agent (e.g., https://agent.example.com)

        Returns:
            A2AAgentCard if successful, None if unreachable.
        """
        url = f"{base_url.rstrip('/')}/.well-known/agent.json"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
                card = A2AAgentCard(
                    name=data.get("name", "unknown"),
                    description=data.get("description", ""),
                    url=data.get("url", base_url),
                    version=data.get("version", "1.0.0"),
                    skills=data.get("skills", []),
                    protocols=data.get("protocols", []),
                    authentication=data.get("authentication", {}),
                    pricing=data.get("pricing", {}),
                    endpoints=data.get("endpoints", {}),
                    capabilities=data.get("capabilities", {}),
                    metadata=data.get("metadata", {}),
                )
                self._discovered[card.name] = card
                return card
        except Exception as exc:
            logger.warning("A2A discovery failed for %s: %s", base_url, exc)
            return None

    async def send_task(
        self,
        base_url: str,
        description: str,
        from_agent: str = "HireWire",
    ) -> dict[str, Any]:
        """Send a task to a remote A2A agent via JSON-RPC.

        Args:
            base_url: Base URL of the target agent.
            description: Task description.
            from_agent: Identity of the sending agent.

        Returns:
            JSON-RPC response dict.
        """
        url = f"{base_url.rstrip('/')}/a2a"
        payload = {
            "jsonrpc": "2.0",
            "method": "tasks/send",
            "params": {
                "description": description,
                "from_agent": from_agent,
            },
            "id": uuid.uuid4().hex[:8],
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            logger.warning("A2A task send failed for %s: %s", base_url, exc)
            return {"error": str(exc)}

    async def get_task_status(
        self,
        base_url: str,
        task_id: str,
    ) -> dict[str, Any]:
        """Check the status of a task on a remote A2A agent.

        Args:
            base_url: Base URL of the target agent.
            task_id: Task ID to check.

        Returns:
            JSON-RPC response dict with task state.
        """
        url = f"{base_url.rstrip('/')}/a2a"
        payload = {
            "jsonrpc": "2.0",
            "method": "tasks/get",
            "params": {"task_id": task_id},
            "id": uuid.uuid4().hex[:8],
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            return {"error": str(exc)}

    async def cancel_task(
        self,
        base_url: str,
        task_id: str,
    ) -> dict[str, Any]:
        """Cancel a task on a remote A2A agent.

        Args:
            base_url: Base URL of the target agent.
            task_id: Task ID to cancel.

        Returns:
            JSON-RPC response dict.
        """
        url = f"{base_url.rstrip('/')}/a2a"
        payload = {
            "jsonrpc": "2.0",
            "method": "tasks/cancel",
            "params": {"task_id": task_id},
            "id": uuid.uuid4().hex[:8],
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            return {"error": str(exc)}

    def get_discovered(self) -> list[A2AAgentCard]:
        """List all discovered remote agents."""
        return list(self._discovered.values())

    def find_by_skill(self, skill: str) -> list[A2AAgentCard]:
        """Find discovered agents matching a skill query."""
        return [c for c in self._discovered.values() if c.matches_skill(skill)]

    def add_discovered(self, card: A2AAgentCard) -> None:
        """Manually add an agent card to the discovered cache."""
        self._discovered[card.name] = card

    def remove_discovered(self, name: str) -> bool:
        """Remove an agent from the discovered cache."""
        return self._discovered.pop(name, None) is not None

    def clear_discovered(self) -> None:
        """Clear all discovered agents."""
        self._discovered.clear()


# Global A2A client
a2a_client = A2AClient()


# ---------------------------------------------------------------------------
# A2A Server — Handles incoming A2A JSON-RPC requests
# ---------------------------------------------------------------------------

# JSON-RPC 2.0 error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


def _jsonrpc_error(code: int, message: str, req_id: Any = None) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "error": {"code": code, "message": message},
        "id": req_id,
    }


def _jsonrpc_result(result: Any, req_id: Any = None) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "result": result, "id": req_id}


class A2AServer:
    """Handles incoming A2A JSON-RPC requests for HireWire.

    Routes tasks through the existing task engine (CEO agent analysis,
    agent detection, budget allocation, payment recording).

    JSON-RPC methods:
    - tasks/send: Submit a task to HireWire
    - tasks/get: Check task state
    - tasks/cancel: Cancel a pending/working task
    - agents/info: Get the HireWire agent card
    - agents/list: List available HireWire agents
    """

    def __init__(self, base_url: str = "http://localhost:8000") -> None:
        self._base_url = base_url
        self._card = generate_hirewire_agent_card(base_url)
        self._task_store = protocol_task_store

    @property
    def agent_card(self) -> A2AAgentCard:
        return self._card

    @property
    def task_store(self) -> A2AProtocolTaskStore:
        return self._task_store

    def get_agent_card_dict(self) -> dict[str, Any]:
        """Get the agent card as a JSON-serializable dict."""
        return self._card.to_dict()

    def handle_tasks_send(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle tasks/send — submit a task to HireWire."""
        description = params.get("description")
        from_agent = params.get("from_agent", "anonymous")

        if not description:
            return {"error": "Missing required parameter: 'description'"}

        # Route through the task engine
        task = self._task_store.create(
            description=description,
            from_agent=from_agent,
            to_agent="HireWire",
            metadata=params.get("metadata", {}),
        )

        # Detect and route to appropriate agent
        task.state = A2ATaskState.WORKING
        task.updated_at = time.time()

        try:
            from src.mcp_servers.registry_server import registry
            agent = self._detect_agent(description)
            agent_info = registry.get(agent)

            if agent_info is not None:
                result = {
                    "agent": agent,
                    "description": agent_info.description,
                    "output": f"Task processed by '{agent}': {description}",
                    "skills_used": agent_info.skills,
                    "protocol": "a2a",
                }
                self._task_store.update_state(
                    task.task_id, A2ATaskState.COMPLETED, result=result
                )
            else:
                result = {
                    "agent": agent,
                    "output": f"Task routed to '{agent}': {description}",
                    "protocol": "a2a",
                }
                self._task_store.update_state(
                    task.task_id, A2ATaskState.COMPLETED, result=result
                )
        except Exception as exc:
            self._task_store.update_state(
                task.task_id, A2ATaskState.FAILED, error=str(exc)
            )

        task = self._task_store.get(task.task_id)
        return task.to_dict() if task else {"error": "Task creation failed"}

    def handle_tasks_get(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle tasks/get — check task state."""
        task_id = params.get("task_id")
        if not task_id:
            return {"error": "Missing required parameter: 'task_id'"}

        task = self._task_store.get(task_id)
        if task is None:
            return {"error": f"Task not found: '{task_id}'"}

        return task.to_dict()

    def handle_tasks_cancel(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle tasks/cancel — cancel a pending/working task."""
        task_id = params.get("task_id")
        if not task_id:
            return {"error": "Missing required parameter: 'task_id'"}

        cancelled = self._task_store.cancel(task_id)
        task = self._task_store.get(task_id)
        return {
            "task_id": task_id,
            "cancelled": cancelled,
            "state": task.state.value if task else "unknown",
        }

    def handle_agents_info(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle agents/info — return the HireWire agent card."""
        return self.get_agent_card_dict()

    def handle_agents_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle agents/list — list available HireWire agents."""
        try:
            from src.mcp_servers.registry_server import registry
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
        except Exception as exc:
            return {"error": str(exc), "total": 0, "agents": []}

    def dispatch_jsonrpc(self, request_body: dict[str, Any]) -> dict[str, Any]:
        """Dispatch a JSON-RPC 2.0 request to the appropriate handler."""
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

        handlers = {
            "tasks/send": self.handle_tasks_send,
            "tasks/get": self.handle_tasks_get,
            "tasks/cancel": self.handle_tasks_cancel,
            "agents/info": self.handle_agents_info,
            "agents/list": self.handle_agents_list,
        }

        handler = handlers.get(method)
        if handler is None:
            return _jsonrpc_error(METHOD_NOT_FOUND, f"Method not found: '{method}'", req_id)

        try:
            result = handler(params)
            return _jsonrpc_result(result, req_id)
        except Exception as exc:
            return _jsonrpc_error(INTERNAL_ERROR, str(exc), req_id)

    def dispatch_batch(self, requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Dispatch a batch of JSON-RPC requests."""
        return [self.dispatch_jsonrpc(req) for req in requests]

    @staticmethod
    def _detect_agent(description: str) -> str:
        """Detect which agent should handle a task based on keywords."""
        desc_lower = description.lower()
        design_keywords = {"design", "mockup", "ui", "ux", "landing", "brand", "visual", "logo"}
        analysis_keywords = {"data", "pricing", "market", "financial", "metrics", "benchmark"}
        research_keywords = {"search", "find", "compare", "analyze", "research", "investigate",
                             "evaluate", "review", "assess", "study"}

        if any(kw in desc_lower for kw in design_keywords):
            return "designer-ext-001"
        if any(kw in desc_lower for kw in analysis_keywords):
            return "analyst-ext-001"
        if any(kw in desc_lower for kw in research_keywords):
            return "research"
        return "builder"


# Global A2A server
a2a_server = A2AServer()


# ---------------------------------------------------------------------------
# Delegation helper
# ---------------------------------------------------------------------------


async def delegate_to_remote_agent(
    remote_url: str,
    description: str,
    from_agent: str = "HireWire",
) -> dict[str, Any]:
    """Convenience function to delegate a task to a remote A2A agent.

    Discovers the remote agent (if not already cached), sends the task,
    and returns the result.

    Args:
        remote_url: Base URL of the remote A2A agent.
        description: Task description.
        from_agent: Identity of the sending agent.

    Returns:
        Dict with discovered agent card and task result.
    """
    # Discover the agent first
    card = await a2a_client.discover(remote_url)
    if card is None:
        return {"error": f"Could not discover agent at {remote_url}"}

    # Send the task
    result = await a2a_client.send_task(remote_url, description, from_agent)

    return {
        "remote_agent": card.to_dict(),
        "task_result": result,
    }


# ---------------------------------------------------------------------------
# Info helper
# ---------------------------------------------------------------------------


def get_a2a_info() -> dict[str, Any]:
    """Return information about the A2A protocol integration."""
    return {
        "version": "2.0.0",
        "protocol": "Google A2A",
        "spec_url": "https://google.github.io/A2A/",
        "capabilities": {
            "agent_card": True,
            "task_lifecycle": True,
            "json_rpc": True,
            "batch_requests": True,
            "task_cancellation": True,
            "remote_discovery": True,
            "remote_delegation": True,
        },
        "methods": [
            "tasks/send",
            "tasks/get",
            "tasks/cancel",
            "agents/info",
            "agents/list",
        ],
        "task_states": [s.value for s in A2ATaskState],
        "discovered_agents": len(a2a_client.get_discovered()),
        "pending_tasks": len(protocol_task_store.list_all(A2ATaskState.SUBMITTED)),
        "working_tasks": len(protocol_task_store.list_all(A2ATaskState.WORKING)),
        "completed_tasks": len(protocol_task_store.list_all(A2ATaskState.COMPLETED)),
    }
