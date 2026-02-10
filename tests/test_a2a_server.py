"""Tests for A2A (Agent-to-Agent) Protocol Server.

Covers:
- Agent card generation and discovery endpoint
- JSON-RPC 2.0 dispatch (envelope validation, error codes)
- tasks/send: task submission and routing to internal/external agents
- tasks/get: task status retrieval
- agents/list: agent listing and filtering
- Batch requests
- Error handling (unknown agent, invalid format, missing params)
- FastAPI endpoint integration
- Task store operations
"""

from __future__ import annotations

import pytest
import httpx

from src.mcp_servers.a2a_server import (
    A2ATaskStore,
    A2ATaskStatus,
    generate_agent_card,
    route_task_to_agent,
    dispatch_jsonrpc,
    handle_tasks_send,
    handle_tasks_get,
    handle_agents_list,
    create_a2a_app,
    task_store,
    PARSE_ERROR,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    INVALID_PARAMS,
)
from src.mcp_servers.registry_server import registry


@pytest.fixture(autouse=True)
def _reset_task_store():
    """Clear A2A task store between tests."""
    task_store.clear()
    yield
    task_store.clear()


# ---------------------------------------------------------------------------
# Agent Card Tests
# ---------------------------------------------------------------------------

class TestAgentCard:
    """Test agent card generation and content."""

    def test_card_has_required_fields(self):
        card = generate_agent_card()
        assert card["name"] == "HireWire"
        assert "description" in card
        assert "version" in card
        assert "skills" in card
        assert "protocols" in card
        assert "endpoints" in card

    def test_card_includes_protocols(self):
        card = generate_agent_card()
        assert "a2a" in card["protocols"]
        assert "json-rpc-2.0" in card["protocols"]
        assert "x402" in card["protocols"]

    def test_card_includes_internal_agents(self):
        card = generate_agent_card()
        agent_names = [a["name"] for a in card["agents"]]
        assert "builder" in agent_names
        assert "research" in agent_names

    def test_card_excludes_external_agents(self):
        card = generate_agent_card()
        agent_names = [a["name"] for a in card["agents"]]
        # designer-ext-001 is external, should not appear in card["agents"]
        assert "designer-ext-001" not in agent_names

    def test_card_aggregates_skills(self):
        card = generate_agent_card()
        # Should have skills from all registered agents
        assert "code" in card["skills"]
        assert "search" in card["skills"]

    def test_card_has_pricing_info(self):
        card = generate_agent_card()
        assert card["pricing"]["currency"] == "USDC"
        assert card["pricing"]["model"] == "per-task"

    def test_card_has_auth_schemes(self):
        card = generate_agent_card()
        assert "x402" in card["authentication"]["schemes"]

    def test_card_uses_custom_base_url(self):
        card = generate_agent_card(base_url="https://hirewire.opspawn.com")
        assert card["url"] == "https://hirewire.opspawn.com"

    def test_card_default_base_url(self):
        card = generate_agent_card()
        assert card["url"] == "http://localhost:8080"


# ---------------------------------------------------------------------------
# Task Store Tests
# ---------------------------------------------------------------------------

class TestTaskStore:
    """Test the A2A task store."""

    def test_create_task(self):
        store = A2ATaskStore()
        task = store.create_task("builder", "Build something", "ext-agent")
        assert task.task_id.startswith("a2a_")
        assert task.agent_name == "builder"
        assert task.status == A2ATaskStatus.PENDING

    def test_get_task(self):
        store = A2ATaskStore()
        task = store.create_task("builder", "Build something")
        retrieved = store.get_task(task.task_id)
        assert retrieved is not None
        assert retrieved.task_id == task.task_id

    def test_get_nonexistent_task(self):
        store = A2ATaskStore()
        assert store.get_task("nonexistent") is None

    def test_list_tasks(self):
        store = A2ATaskStore()
        store.create_task("builder", "Task 1")
        store.create_task("research", "Task 2")
        tasks = store.list_tasks()
        assert len(tasks) == 2

    def test_list_tasks_filtered(self):
        store = A2ATaskStore()
        store.create_task("builder", "Task 1")
        store.create_task("research", "Task 2")
        store.create_task("builder", "Task 3")
        builder_tasks = store.list_tasks(agent_name="builder")
        assert len(builder_tasks) == 2

    def test_clear(self):
        store = A2ATaskStore()
        store.create_task("builder", "Task 1")
        store.clear()
        assert len(store.list_tasks()) == 0
        assert store._counter == 0


# ---------------------------------------------------------------------------
# Task Routing Tests
# ---------------------------------------------------------------------------

class TestTaskRouting:
    """Test task routing to agents."""

    def test_route_to_internal_agent(self):
        result = route_task_to_agent("builder", "Write tests")
        assert result["agent"] == "builder"
        assert "output" in result
        assert "skills_used" in result

    def test_route_to_research_agent(self):
        result = route_task_to_agent("research", "Search for trends")
        assert result["agent"] == "research"
        assert "search" in result["skills_used"]

    def test_route_to_external_agent(self):
        result = route_task_to_agent("designer-ext-001", "Design a logo")
        assert result["agent"] == "designer-ext-001"
        assert "endpoint" in result
        assert result["protocol"] == "a2a"

    def test_route_to_unknown_agent(self):
        result = route_task_to_agent("nonexistent-agent", "Do something")
        assert "error" in result
        assert "not found" in result["error"]


# ---------------------------------------------------------------------------
# JSON-RPC Dispatch Tests
# ---------------------------------------------------------------------------

class TestJSONRPCDispatch:
    """Test JSON-RPC 2.0 envelope validation and dispatch."""

    def test_valid_request(self):
        response = dispatch_jsonrpc({
            "jsonrpc": "2.0",
            "method": "agents/list",
            "params": {},
            "id": 1,
        })
        assert response["jsonrpc"] == "2.0"
        assert "result" in response
        assert response["id"] == 1

    def test_missing_jsonrpc_version(self):
        response = dispatch_jsonrpc({
            "method": "agents/list",
            "params": {},
            "id": 1,
        })
        assert "error" in response
        assert response["error"]["code"] == INVALID_REQUEST

    def test_wrong_jsonrpc_version(self):
        response = dispatch_jsonrpc({
            "jsonrpc": "1.0",
            "method": "agents/list",
            "id": 1,
        })
        assert "error" in response
        assert response["error"]["code"] == INVALID_REQUEST

    def test_missing_method(self):
        response = dispatch_jsonrpc({
            "jsonrpc": "2.0",
            "params": {},
            "id": 1,
        })
        assert "error" in response
        assert response["error"]["code"] == INVALID_REQUEST

    def test_unknown_method(self):
        response = dispatch_jsonrpc({
            "jsonrpc": "2.0",
            "method": "unknown/method",
            "params": {},
            "id": 2,
        })
        assert "error" in response
        assert response["error"]["code"] == METHOD_NOT_FOUND
        assert response["id"] == 2

    def test_invalid_params_type(self):
        response = dispatch_jsonrpc({
            "jsonrpc": "2.0",
            "method": "agents/list",
            "params": "not-an-object",
            "id": 3,
        })
        assert "error" in response
        assert response["error"]["code"] == INVALID_PARAMS

    def test_non_dict_request(self):
        response = dispatch_jsonrpc("not a dict")
        assert "error" in response
        assert response["error"]["code"] == INVALID_REQUEST

    def test_preserves_request_id(self):
        response = dispatch_jsonrpc({
            "jsonrpc": "2.0",
            "method": "agents/list",
            "params": {},
            "id": "my-request-42",
        })
        assert response["id"] == "my-request-42"

    def test_null_id(self):
        response = dispatch_jsonrpc({
            "jsonrpc": "2.0",
            "method": "agents/list",
            "params": {},
            "id": None,
        })
        assert response["id"] is None
        assert "result" in response

    def test_default_empty_params(self):
        response = dispatch_jsonrpc({
            "jsonrpc": "2.0",
            "method": "agents/list",
            "id": 1,
        })
        assert "result" in response
        assert response["result"]["total"] > 0


# ---------------------------------------------------------------------------
# tasks/send Tests
# ---------------------------------------------------------------------------

class TestTasksSend:
    """Test the tasks/send JSON-RPC method."""

    def test_send_task_to_builder(self):
        result = handle_tasks_send({
            "agent": "builder",
            "description": "Write unit tests",
            "from_agent": "external-client",
        })
        assert "task_id" in result
        assert result["status"] == "completed"
        assert result["agent"] == "builder"

    def test_send_task_missing_agent(self):
        result = handle_tasks_send({
            "description": "Do something",
        })
        assert "error" in result
        assert "agent" in result["error"]

    def test_send_task_missing_description(self):
        result = handle_tasks_send({
            "agent": "builder",
        })
        assert "error" in result
        assert "description" in result["error"]

    def test_send_task_unknown_agent(self):
        result = handle_tasks_send({
            "agent": "nonexistent-agent-xyz",
            "description": "Do something",
        })
        assert "error" in result
        assert "Unknown agent" in result["error"]

    def test_send_task_with_x402(self):
        result = handle_tasks_send({
            "agent": "builder",
            "description": "Build with payment",
            "x402_payment": "x402-token-here",
        })
        assert result["status"] == "completed"
        # Verify the task has x402 info stored
        task = task_store.get_task(result["task_id"])
        assert task.x402_payment == "x402-token-here"

    def test_send_task_stores_in_task_store(self):
        result = handle_tasks_send({
            "agent": "research",
            "description": "Search for data",
        })
        task = task_store.get_task(result["task_id"])
        assert task is not None
        assert task.agent_name == "research"
        assert task.status == A2ATaskStatus.COMPLETED

    def test_send_via_jsonrpc(self):
        response = dispatch_jsonrpc({
            "jsonrpc": "2.0",
            "method": "tasks/send",
            "params": {
                "agent": "builder",
                "description": "Full RPC test",
            },
            "id": 10,
        })
        assert "result" in response
        assert response["result"]["status"] == "completed"
        assert response["id"] == 10


# ---------------------------------------------------------------------------
# tasks/get Tests
# ---------------------------------------------------------------------------

class TestTasksGet:
    """Test the tasks/get JSON-RPC method."""

    def test_get_existing_task(self):
        send_result = handle_tasks_send({
            "agent": "builder",
            "description": "Build feature",
        })
        get_result = handle_tasks_get({"task_id": send_result["task_id"]})
        assert get_result["task_id"] == send_result["task_id"]
        assert get_result["status"] == "completed"
        assert get_result["agent"] == "builder"

    def test_get_missing_task_id(self):
        result = handle_tasks_get({})
        assert "error" in result
        assert "task_id" in result["error"]

    def test_get_nonexistent_task(self):
        result = handle_tasks_get({"task_id": "no-such-task"})
        assert "error" in result
        assert "not found" in result["error"]

    def test_get_via_jsonrpc(self):
        # First send a task
        send_resp = dispatch_jsonrpc({
            "jsonrpc": "2.0",
            "method": "tasks/send",
            "params": {"agent": "research", "description": "Analyze market"},
            "id": 20,
        })
        task_id = send_resp["result"]["task_id"]

        # Then get it
        get_resp = dispatch_jsonrpc({
            "jsonrpc": "2.0",
            "method": "tasks/get",
            "params": {"task_id": task_id},
            "id": 21,
        })
        assert get_resp["result"]["task_id"] == task_id
        assert get_resp["result"]["description"] == "Analyze market"


# ---------------------------------------------------------------------------
# agents/list Tests
# ---------------------------------------------------------------------------

class TestAgentsList:
    """Test the agents/list JSON-RPC method."""

    def test_list_all_agents(self):
        result = handle_agents_list({})
        assert result["total"] >= 3  # builder, research, designer-ext-001
        names = [a["name"] for a in result["agents"]]
        assert "builder" in names
        assert "research" in names

    def test_list_with_capability_filter(self):
        result = handle_agents_list({"capability": "code"})
        assert result["total"] >= 1
        assert any(a["name"] == "builder" for a in result["agents"])

    def test_list_excludes_external(self):
        result = handle_agents_list({"include_external": False})
        for agent in result["agents"]:
            assert agent["is_external"] is False

    def test_list_includes_external_by_default(self):
        result = handle_agents_list({})
        has_external = any(a["is_external"] for a in result["agents"])
        assert has_external

    def test_agent_entry_has_skills(self):
        result = handle_agents_list({})
        for agent in result["agents"]:
            assert "skills" in agent
            assert isinstance(agent["skills"], list)

    def test_list_via_jsonrpc(self):
        response = dispatch_jsonrpc({
            "jsonrpc": "2.0",
            "method": "agents/list",
            "params": {},
            "id": 30,
        })
        assert "result" in response
        assert response["result"]["total"] >= 2


# ---------------------------------------------------------------------------
# FastAPI Endpoint Integration Tests
# ---------------------------------------------------------------------------

class TestA2AEndpoints:
    """Test the FastAPI endpoints via ASGI transport."""

    @pytest.mark.asyncio
    async def test_agent_card_endpoint(self):
        app = create_a2a_app(base_url="https://test.example.com")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/.well-known/agent.json")
        assert resp.status_code == 200
        card = resp.json()
        assert card["name"] == "HireWire"
        assert card["url"] == "https://test.example.com"

    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        app = create_a2a_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/a2a/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["protocol"] == "a2a"
        assert data["agents_available"] >= 2

    @pytest.mark.asyncio
    async def test_jsonrpc_tasks_send(self):
        app = create_a2a_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post("/a2a", json={
                "jsonrpc": "2.0",
                "method": "tasks/send",
                "params": {
                    "agent": "builder",
                    "description": "Build feature via HTTP",
                },
                "id": 100,
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["jsonrpc"] == "2.0"
        assert data["result"]["status"] == "completed"
        assert data["id"] == 100

    @pytest.mark.asyncio
    async def test_jsonrpc_invalid_json(self):
        app = create_a2a_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/a2a",
                content=b"not json",
                headers={"content-type": "application/json"},
            )
        assert resp.status_code == 200  # JSON-RPC always returns 200
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == PARSE_ERROR

    @pytest.mark.asyncio
    async def test_jsonrpc_batch_request(self):
        app = create_a2a_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post("/a2a", json=[
                {
                    "jsonrpc": "2.0",
                    "method": "agents/list",
                    "params": {},
                    "id": 1,
                },
                {
                    "jsonrpc": "2.0",
                    "method": "tasks/send",
                    "params": {"agent": "builder", "description": "Batch task"},
                    "id": 2,
                },
            ])
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["id"] == 1
        assert data[1]["id"] == 2

    @pytest.mark.asyncio
    async def test_jsonrpc_empty_batch(self):
        app = create_a2a_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post("/a2a", json=[])
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == INVALID_REQUEST
