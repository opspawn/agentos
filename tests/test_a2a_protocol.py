"""Tests for A2A Protocol Integration (Sprint 29).

Comprehensive tests covering:
- A2AAgentCard generation and matching
- HireWire agent card generation
- A2AProtocolTask lifecycle
- A2AProtocolTaskStore operations
- A2AClient discovery, send, cancel, cache management
- A2AServer JSON-RPC dispatch (all methods)
- A2AServer task routing
- Batch JSON-RPC requests
- Error handling (invalid params, unknown methods, network errors)
- FastAPI endpoint integration (agent card, JSON-RPC, discover, delegate, agents)
- Delegation helper
- Info helper

Target: 50+ tests
"""

from __future__ import annotations

import pytest
import httpx
import respx

from src.integrations.a2a_protocol import (
    A2AAgentCard,
    A2AProtocolTask,
    A2AProtocolTaskStore,
    A2ATaskState,
    A2AClient,
    A2AServer,
    a2a_client,
    a2a_server,
    protocol_task_store,
    generate_hirewire_agent_card,
    delegate_to_remote_agent,
    get_a2a_info,
    PARSE_ERROR,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    INVALID_PARAMS,
    INTERNAL_ERROR,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_a2a_state():
    """Reset A2A state between tests."""
    protocol_task_store.clear()
    a2a_client.clear_discovered()
    yield
    protocol_task_store.clear()
    a2a_client.clear_discovered()


@pytest.fixture
def server():
    """Fresh A2A server instance."""
    return A2AServer(base_url="http://test:8000")


@pytest.fixture
def client():
    """Fresh A2A client instance."""
    return A2AClient(timeout=5.0)


# ---------------------------------------------------------------------------
# A2AAgentCard Tests
# ---------------------------------------------------------------------------


class TestA2AAgentCard:
    """Test agent card generation and matching."""

    def test_card_creation(self):
        card = A2AAgentCard(
            name="TestAgent",
            description="A test agent",
            url="http://test:9000",
        )
        assert card.name == "TestAgent"
        assert card.description == "A test agent"
        assert card.url == "http://test:9000"
        assert card.version == "1.0.0"

    def test_card_to_dict(self):
        card = A2AAgentCard(name="Test", description="desc")
        d = card.to_dict()
        assert d["name"] == "Test"
        assert d["description"] == "desc"
        assert isinstance(d["protocols"], list)
        assert isinstance(d["skills"], list)

    def test_card_default_protocols(self):
        card = A2AAgentCard(name="Test", description="")
        assert "a2a" in card.protocols
        assert "json-rpc-2.0" in card.protocols

    def test_card_default_auth(self):
        card = A2AAgentCard(name="Test", description="")
        assert card.authentication == {"schemes": ["none"]}

    def test_card_matches_skill_by_name(self):
        card = A2AAgentCard(
            name="Builder",
            description="Builds things",
            skills=[{"name": "code_generation", "description": "Generates code"}],
        )
        assert card.matches_skill("code_generation")
        assert card.matches_skill("CODE")  # case insensitive

    def test_card_matches_skill_by_description(self):
        card = A2AAgentCard(
            name="Builder",
            description="Builds things",
            skills=[{"name": "build", "description": "Writes and deploys code"}],
        )
        assert card.matches_skill("deploys")

    def test_card_matches_skill_by_agent_name(self):
        card = A2AAgentCard(name="DataAnalyst", description="Analyzes data")
        assert card.matches_skill("analyst")

    def test_card_matches_skill_by_agent_description(self):
        card = A2AAgentCard(name="Agent", description="Financial modeling expert")
        assert card.matches_skill("financial")

    def test_card_no_skill_match(self):
        card = A2AAgentCard(name="Builder", description="Builds", skills=[])
        assert not card.matches_skill("quantum_physics")

    def test_card_custom_pricing(self):
        card = A2AAgentCard(
            name="Premium",
            description="Premium agent",
            pricing={"model": "per-task", "rate": 0.05, "currency": "USDC"},
        )
        assert card.pricing["rate"] == 0.05


class TestHireWireAgentCard:
    """Test HireWire-specific agent card generation."""

    def test_hirewire_card_name(self):
        card = generate_hirewire_agent_card()
        assert card.name == "HireWire"

    def test_hirewire_card_protocols(self):
        card = generate_hirewire_agent_card()
        assert "a2a" in card.protocols
        assert "json-rpc-2.0" in card.protocols
        assert "x402" in card.protocols
        assert "mcp" in card.protocols

    def test_hirewire_card_skills(self):
        card = generate_hirewire_agent_card()
        skill_names = [s["name"] for s in card.skills]
        assert "task_management" in skill_names
        assert "agent_hiring" in skill_names
        assert "orchestration" in skill_names
        assert "x402_payments" in skill_names
        assert "marketplace" in skill_names
        assert "mcp_tools" in skill_names

    def test_hirewire_card_custom_url(self):
        card = generate_hirewire_agent_card(base_url="https://hirewire.opspawn.com")
        assert card.url == "https://hirewire.opspawn.com"
        assert "hirewire.opspawn.com" in card.endpoints["jsonrpc"]

    def test_hirewire_card_endpoints(self):
        card = generate_hirewire_agent_card(base_url="http://test:8000")
        assert card.endpoints["jsonrpc"] == "http://test:8000/a2a"
        assert card.endpoints["agent_card"] == "http://test:8000/.well-known/agent.json"

    def test_hirewire_card_capabilities(self):
        card = generate_hirewire_agent_card()
        assert card.capabilities["batch_requests"] is True
        assert card.capabilities["task_cancellation"] is True

    def test_hirewire_card_metadata(self):
        card = generate_hirewire_agent_card()
        assert card.metadata["built_by"] == "OpSpawn"
        assert "Microsoft" in card.metadata["framework"]

    def test_hirewire_card_auth_schemes(self):
        card = generate_hirewire_agent_card()
        assert "x402" in card.authentication["schemes"]

    def test_hirewire_card_pricing(self):
        card = generate_hirewire_agent_card()
        assert card.pricing["currency"] == "USDC"
        assert card.pricing["model"] == "per-task"


# ---------------------------------------------------------------------------
# A2AProtocolTask Tests
# ---------------------------------------------------------------------------


class TestA2AProtocolTask:
    """Test A2A protocol task lifecycle."""

    def test_task_creation(self):
        task = A2AProtocolTask(description="Build something")
        assert task.task_id.startswith("a2a_")
        assert task.state == A2ATaskState.SUBMITTED
        assert task.description == "Build something"

    def test_task_default_state(self):
        task = A2AProtocolTask()
        assert task.state == A2ATaskState.SUBMITTED

    def test_task_to_dict(self):
        task = A2AProtocolTask(
            description="Test task",
            from_agent="remote-agent",
            to_agent="HireWire",
        )
        d = task.to_dict()
        assert d["description"] == "Test task"
        assert d["from_agent"] == "remote-agent"
        assert d["to_agent"] == "HireWire"
        assert d["state"] == "submitted"
        assert "created_at" in d

    def test_task_states(self):
        assert A2ATaskState.SUBMITTED.value == "submitted"
        assert A2ATaskState.WORKING.value == "working"
        assert A2ATaskState.COMPLETED.value == "completed"
        assert A2ATaskState.FAILED.value == "failed"
        assert A2ATaskState.CANCELLED.value == "cancelled"


# ---------------------------------------------------------------------------
# A2AProtocolTaskStore Tests
# ---------------------------------------------------------------------------


class TestA2AProtocolTaskStore:
    """Test the protocol task store."""

    def test_create_task(self):
        store = A2AProtocolTaskStore()
        task = store.create("Build a feature", from_agent="ext")
        assert task.task_id.startswith("a2a_")
        assert task.description == "Build a feature"
        assert task.from_agent == "ext"

    def test_get_task(self):
        store = A2AProtocolTaskStore()
        task = store.create("Test")
        retrieved = store.get(task.task_id)
        assert retrieved is not None
        assert retrieved.task_id == task.task_id

    def test_get_nonexistent(self):
        store = A2AProtocolTaskStore()
        assert store.get("nope") is None

    def test_update_state_to_working(self):
        store = A2AProtocolTaskStore()
        task = store.create("Test")
        updated = store.update_state(task.task_id, A2ATaskState.WORKING)
        assert updated.state == A2ATaskState.WORKING

    def test_update_state_to_completed(self):
        store = A2AProtocolTaskStore()
        task = store.create("Test")
        result = {"output": "done"}
        updated = store.update_state(task.task_id, A2ATaskState.COMPLETED, result=result)
        assert updated.state == A2ATaskState.COMPLETED
        assert updated.result == result
        assert updated.completed_at is not None

    def test_update_state_to_failed(self):
        store = A2AProtocolTaskStore()
        task = store.create("Test")
        updated = store.update_state(task.task_id, A2ATaskState.FAILED, error="boom")
        assert updated.state == A2ATaskState.FAILED
        assert updated.error == "boom"
        assert updated.completed_at is not None

    def test_update_nonexistent(self):
        store = A2AProtocolTaskStore()
        assert store.update_state("nope", A2ATaskState.WORKING) is None

    def test_list_all(self):
        store = A2AProtocolTaskStore()
        store.create("Task 1")
        store.create("Task 2")
        store.create("Task 3")
        assert len(store.list_all()) == 3

    def test_list_filtered_by_state(self):
        store = A2AProtocolTaskStore()
        t1 = store.create("Task 1")
        t2 = store.create("Task 2")
        store.update_state(t1.task_id, A2ATaskState.COMPLETED)
        assert len(store.list_all(A2ATaskState.SUBMITTED)) == 1
        assert len(store.list_all(A2ATaskState.COMPLETED)) == 1

    def test_cancel_submitted_task(self):
        store = A2AProtocolTaskStore()
        task = store.create("Task")
        assert store.cancel(task.task_id) is True
        assert store.get(task.task_id).state == A2ATaskState.CANCELLED

    def test_cancel_working_task(self):
        store = A2AProtocolTaskStore()
        task = store.create("Task")
        store.update_state(task.task_id, A2ATaskState.WORKING)
        assert store.cancel(task.task_id) is True

    def test_cancel_completed_task_fails(self):
        store = A2AProtocolTaskStore()
        task = store.create("Task")
        store.update_state(task.task_id, A2ATaskState.COMPLETED)
        assert store.cancel(task.task_id) is False

    def test_cancel_nonexistent(self):
        store = A2AProtocolTaskStore()
        assert store.cancel("nope") is False

    def test_clear(self):
        store = A2AProtocolTaskStore()
        store.create("Task 1")
        store.create("Task 2")
        store.clear()
        assert len(store.list_all()) == 0


# ---------------------------------------------------------------------------
# A2AClient Tests
# ---------------------------------------------------------------------------


class TestA2AClient:
    """Test A2A client discovery and task sending."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_discover_agent(self, client):
        agent_card_data = {
            "name": "RemoteAgent",
            "description": "A remote test agent",
            "url": "http://remote:9000",
            "version": "1.0.0",
            "skills": [{"name": "testing", "description": "Runs tests"}],
            "protocols": ["a2a"],
        }
        respx.get("http://remote:9000/.well-known/agent.json").mock(
            return_value=httpx.Response(200, json=agent_card_data)
        )

        card = await client.discover("http://remote:9000")
        assert card is not None
        assert card.name == "RemoteAgent"
        assert card.url == "http://remote:9000"

    @pytest.mark.asyncio
    @respx.mock
    async def test_discover_agent_not_found(self, client):
        respx.get("http://remote:9000/.well-known/agent.json").mock(
            return_value=httpx.Response(404)
        )
        card = await client.discover("http://remote:9000")
        assert card is None

    @pytest.mark.asyncio
    @respx.mock
    async def test_discover_agent_network_error(self, client):
        respx.get("http://unreachable:9000/.well-known/agent.json").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        card = await client.discover("http://unreachable:9000")
        assert card is None

    @pytest.mark.asyncio
    @respx.mock
    async def test_discover_caches_agent(self, client):
        respx.get("http://remote:9000/.well-known/agent.json").mock(
            return_value=httpx.Response(200, json={
                "name": "CachedAgent",
                "description": "cached",
            })
        )
        await client.discover("http://remote:9000")
        discovered = client.get_discovered()
        assert len(discovered) == 1
        assert discovered[0].name == "CachedAgent"

    @pytest.mark.asyncio
    @respx.mock
    async def test_send_task(self, client):
        respx.post("http://remote:9000/a2a").mock(
            return_value=httpx.Response(200, json={
                "jsonrpc": "2.0",
                "result": {"task_id": "a2a_123", "state": "submitted"},
                "id": "test",
            })
        )
        result = await client.send_task("http://remote:9000", "Build something")
        assert "result" in result
        assert result["result"]["task_id"] == "a2a_123"

    @pytest.mark.asyncio
    @respx.mock
    async def test_send_task_network_error(self, client):
        respx.post("http://unreachable:9000/a2a").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        result = await client.send_task("http://unreachable:9000", "Test")
        assert "error" in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_task_status(self, client):
        respx.post("http://remote:9000/a2a").mock(
            return_value=httpx.Response(200, json={
                "jsonrpc": "2.0",
                "result": {"task_id": "a2a_123", "state": "completed"},
                "id": "test",
            })
        )
        result = await client.get_task_status("http://remote:9000", "a2a_123")
        assert result["result"]["state"] == "completed"

    @pytest.mark.asyncio
    @respx.mock
    async def test_cancel_task(self, client):
        respx.post("http://remote:9000/a2a").mock(
            return_value=httpx.Response(200, json={
                "jsonrpc": "2.0",
                "result": {"task_id": "a2a_123", "cancelled": True},
                "id": "test",
            })
        )
        result = await client.cancel_task("http://remote:9000", "a2a_123")
        assert result["result"]["cancelled"] is True

    def test_find_by_skill(self, client):
        card = A2AAgentCard(
            name="Designer",
            description="UI design",
            skills=[{"name": "ui_design", "description": "Creates UI mockups"}],
        )
        client.add_discovered(card)
        matches = client.find_by_skill("design")
        assert len(matches) == 1
        assert matches[0].name == "Designer"

    def test_find_by_skill_no_match(self, client):
        card = A2AAgentCard(name="Builder", description="Codes")
        client.add_discovered(card)
        assert len(client.find_by_skill("quantum")) == 0

    def test_add_discovered(self, client):
        card = A2AAgentCard(name="Manual", description="Manually added")
        client.add_discovered(card)
        assert len(client.get_discovered()) == 1

    def test_remove_discovered(self, client):
        card = A2AAgentCard(name="ToRemove", description="")
        client.add_discovered(card)
        assert client.remove_discovered("ToRemove") is True
        assert len(client.get_discovered()) == 0

    def test_remove_nonexistent(self, client):
        assert client.remove_discovered("nope") is False

    def test_clear_discovered(self, client):
        client.add_discovered(A2AAgentCard(name="A", description=""))
        client.add_discovered(A2AAgentCard(name="B", description=""))
        client.clear_discovered()
        assert len(client.get_discovered()) == 0

    @pytest.mark.asyncio
    @respx.mock
    async def test_discover_url_trailing_slash(self, client):
        """Ensure trailing slashes are handled correctly."""
        respx.get("http://remote:9000/.well-known/agent.json").mock(
            return_value=httpx.Response(200, json={
                "name": "SlashAgent",
                "description": "trailing slash",
            })
        )
        card = await client.discover("http://remote:9000/")
        assert card is not None
        assert card.name == "SlashAgent"


# ---------------------------------------------------------------------------
# A2AServer Tests
# ---------------------------------------------------------------------------


class TestA2AServer:
    """Test A2A server JSON-RPC dispatch and task handling."""

    def test_server_agent_card(self, server):
        card = server.get_agent_card_dict()
        assert card["name"] == "HireWire"
        assert card["url"] == "http://test:8000"

    def test_server_agent_card_object(self, server):
        card = server.agent_card
        assert isinstance(card, A2AAgentCard)
        assert card.name == "HireWire"

    # -- tasks/send --

    def test_tasks_send_success(self, server):
        result = server.handle_tasks_send({
            "description": "Write unit tests",
            "from_agent": "remote-agent",
        })
        assert "task_id" in result
        assert result["state"] in ("completed", "working")

    def test_tasks_send_missing_description(self, server):
        result = server.handle_tasks_send({"from_agent": "test"})
        assert "error" in result

    def test_tasks_send_default_from_agent(self, server):
        result = server.handle_tasks_send({"description": "Test task"})
        assert "task_id" in result
        task = server.task_store.get(result["task_id"])
        assert task.from_agent == "anonymous"

    def test_tasks_send_routes_to_builder(self, server):
        result = server.handle_tasks_send({
            "description": "Write code for the API",
        })
        assert result.get("result", {}).get("agent") == "builder"

    def test_tasks_send_routes_to_research(self, server):
        result = server.handle_tasks_send({
            "description": "Research competitive landscape",
        })
        assert result.get("result", {}).get("agent") == "research"

    def test_tasks_send_routes_to_designer(self, server):
        result = server.handle_tasks_send({
            "description": "Design a new landing page mockup",
        })
        assert result.get("result", {}).get("agent") == "designer-ext-001"

    # -- tasks/get --

    def test_tasks_get_success(self, server):
        send_result = server.handle_tasks_send({"description": "Build feature"})
        get_result = server.handle_tasks_get({"task_id": send_result["task_id"]})
        assert get_result["task_id"] == send_result["task_id"]

    def test_tasks_get_missing_task_id(self, server):
        result = server.handle_tasks_get({})
        assert "error" in result

    def test_tasks_get_nonexistent(self, server):
        result = server.handle_tasks_get({"task_id": "no-such-task"})
        assert "error" in result

    # -- tasks/cancel --

    def test_tasks_cancel_success(self, server):
        task = server.task_store.create("Cancelable task")
        result = server.handle_tasks_cancel({"task_id": task.task_id})
        assert result["cancelled"] is True
        assert result["state"] == "cancelled"

    def test_tasks_cancel_missing_id(self, server):
        result = server.handle_tasks_cancel({})
        assert "error" in result

    def test_tasks_cancel_completed_task(self, server):
        task = server.task_store.create("Done task")
        server.task_store.update_state(task.task_id, A2ATaskState.COMPLETED)
        result = server.handle_tasks_cancel({"task_id": task.task_id})
        assert result["cancelled"] is False

    # -- agents/info --

    def test_agents_info(self, server):
        result = server.handle_agents_info({})
        assert result["name"] == "HireWire"
        assert "skills" in result

    # -- agents/list --

    def test_agents_list(self, server):
        result = server.handle_agents_list({})
        assert result["total"] >= 2
        names = [a["name"] for a in result["agents"]]
        assert "builder" in names

    def test_agents_list_filter_capability(self, server):
        result = server.handle_agents_list({"capability": "code"})
        assert result["total"] >= 1

    def test_agents_list_exclude_external(self, server):
        result = server.handle_agents_list({"include_external": False})
        for agent in result["agents"]:
            assert agent["is_external"] is False

    # -- JSON-RPC dispatch --

    def test_dispatch_valid_request(self, server):
        resp = server.dispatch_jsonrpc({
            "jsonrpc": "2.0",
            "method": "agents/info",
            "params": {},
            "id": 1,
        })
        assert resp["jsonrpc"] == "2.0"
        assert "result" in resp
        assert resp["id"] == 1

    def test_dispatch_missing_jsonrpc(self, server):
        resp = server.dispatch_jsonrpc({
            "method": "agents/info",
            "params": {},
            "id": 1,
        })
        assert "error" in resp
        assert resp["error"]["code"] == INVALID_REQUEST

    def test_dispatch_wrong_jsonrpc_version(self, server):
        resp = server.dispatch_jsonrpc({
            "jsonrpc": "1.0",
            "method": "agents/info",
            "id": 1,
        })
        assert "error" in resp

    def test_dispatch_missing_method(self, server):
        resp = server.dispatch_jsonrpc({
            "jsonrpc": "2.0",
            "params": {},
            "id": 1,
        })
        assert resp["error"]["code"] == INVALID_REQUEST

    def test_dispatch_unknown_method(self, server):
        resp = server.dispatch_jsonrpc({
            "jsonrpc": "2.0",
            "method": "unknown/method",
            "params": {},
            "id": 2,
        })
        assert resp["error"]["code"] == METHOD_NOT_FOUND

    def test_dispatch_invalid_params_type(self, server):
        resp = server.dispatch_jsonrpc({
            "jsonrpc": "2.0",
            "method": "agents/info",
            "params": "not-an-object",
            "id": 3,
        })
        assert resp["error"]["code"] == INVALID_PARAMS

    def test_dispatch_non_dict_request(self, server):
        resp = server.dispatch_jsonrpc("not a dict")
        assert resp["error"]["code"] == INVALID_REQUEST

    def test_dispatch_preserves_request_id(self, server):
        resp = server.dispatch_jsonrpc({
            "jsonrpc": "2.0",
            "method": "agents/info",
            "params": {},
            "id": "custom-id-42",
        })
        assert resp["id"] == "custom-id-42"

    def test_dispatch_null_id(self, server):
        resp = server.dispatch_jsonrpc({
            "jsonrpc": "2.0",
            "method": "agents/info",
            "params": {},
            "id": None,
        })
        assert resp["id"] is None
        assert "result" in resp

    def test_dispatch_default_empty_params(self, server):
        resp = server.dispatch_jsonrpc({
            "jsonrpc": "2.0",
            "method": "agents/list",
            "id": 1,
        })
        assert "result" in resp

    # -- Batch dispatch --

    def test_dispatch_batch(self, server):
        results = server.dispatch_batch([
            {"jsonrpc": "2.0", "method": "agents/info", "params": {}, "id": 1},
            {"jsonrpc": "2.0", "method": "agents/list", "params": {}, "id": 2},
        ])
        assert len(results) == 2
        assert results[0]["id"] == 1
        assert results[1]["id"] == 2

    def test_dispatch_batch_with_errors(self, server):
        results = server.dispatch_batch([
            {"jsonrpc": "2.0", "method": "agents/info", "params": {}, "id": 1},
            {"jsonrpc": "2.0", "method": "unknown", "params": {}, "id": 2},
        ])
        assert "result" in results[0]
        assert "error" in results[1]

    # -- Agent detection --

    def test_detect_agent_builder(self):
        assert A2AServer._detect_agent("Write code for the API") == "builder"

    def test_detect_agent_research(self):
        assert A2AServer._detect_agent("Research the latest AI papers") == "research"

    def test_detect_agent_designer(self):
        assert A2AServer._detect_agent("Design a new logo") == "designer-ext-001"

    def test_detect_agent_analyst(self):
        assert A2AServer._detect_agent("Analyze financial data") == "analyst-ext-001"

    def test_detect_agent_default_builder(self):
        assert A2AServer._detect_agent("Do something generic") == "builder"


# ---------------------------------------------------------------------------
# FastAPI Endpoint Integration Tests
# ---------------------------------------------------------------------------


class TestA2AEndpoints:
    """Test the FastAPI A2A endpoints via ASGI transport."""

    @pytest.mark.asyncio
    async def test_agent_card_endpoint(self):
        from src.api.main import app
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/.well-known/agent.json")
        assert resp.status_code == 200
        card = resp.json()
        assert card["name"] == "HireWire"
        assert "skills" in card
        assert "protocols" in card

    @pytest.mark.asyncio
    async def test_a2a_jsonrpc_tasks_send(self):
        from src.api.main import app
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post("/a2a", json={
                "jsonrpc": "2.0",
                "method": "tasks/send",
                "params": {"description": "Build a landing page"},
                "id": 100,
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["jsonrpc"] == "2.0"
        assert "result" in data
        assert data["id"] == 100

    @pytest.mark.asyncio
    async def test_a2a_jsonrpc_agents_info(self):
        from src.api.main import app
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post("/a2a", json={
                "jsonrpc": "2.0",
                "method": "agents/info",
                "params": {},
                "id": 200,
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"]["name"] == "HireWire"

    @pytest.mark.asyncio
    async def test_a2a_jsonrpc_invalid_json(self):
        from src.api.main import app
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/a2a",
                content=b"not json at all",
                headers={"content-type": "application/json"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == PARSE_ERROR

    @pytest.mark.asyncio
    async def test_a2a_jsonrpc_batch(self):
        from src.api.main import app
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post("/a2a", json=[
                {"jsonrpc": "2.0", "method": "agents/info", "params": {}, "id": 1},
                {"jsonrpc": "2.0", "method": "agents/list", "params": {}, "id": 2},
            ])
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_a2a_jsonrpc_empty_batch(self):
        from src.api.main import app
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post("/a2a", json=[])
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data

    @pytest.mark.asyncio
    async def test_a2a_agents_endpoint(self):
        from src.api.main import app
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/a2a/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "agents" in data

    @pytest.mark.asyncio
    async def test_a2a_discover_missing_url(self):
        from src.api.main import app
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post("/a2a/discover", json={})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_a2a_delegate_missing_url(self):
        from src.api.main import app
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post("/a2a/delegate", json={"description": "test"})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_a2a_delegate_missing_description(self):
        from src.api.main import app
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post("/a2a/delegate", json={"url": "http://test"})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_a2a_info_endpoint(self):
        from src.api.main import app
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/a2a/info")
        assert resp.status_code == 200
        data = resp.json()
        assert data["protocol"] == "Google A2A"
        assert "capabilities" in data
        assert "methods" in data


# ---------------------------------------------------------------------------
# Delegation Helper Tests
# ---------------------------------------------------------------------------


class TestDelegation:
    """Test the delegation helper."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_delegate_success(self):
        respx.get("http://remote:9000/.well-known/agent.json").mock(
            return_value=httpx.Response(200, json={
                "name": "RemoteAgent",
                "description": "Remote helper",
            })
        )
        respx.post("http://remote:9000/a2a").mock(
            return_value=httpx.Response(200, json={
                "jsonrpc": "2.0",
                "result": {"task_id": "a2a_remote_1", "state": "completed"},
                "id": "test",
            })
        )

        result = await delegate_to_remote_agent(
            "http://remote:9000", "Build something"
        )
        assert "remote_agent" in result
        assert result["remote_agent"]["name"] == "RemoteAgent"
        assert "task_result" in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_delegate_discovery_fails(self):
        respx.get("http://unreachable:9000/.well-known/agent.json").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        result = await delegate_to_remote_agent(
            "http://unreachable:9000", "Test"
        )
        assert "error" in result


# ---------------------------------------------------------------------------
# Info Helper Tests
# ---------------------------------------------------------------------------


class TestA2AInfo:
    """Test the info helper."""

    def test_info_structure(self):
        info = get_a2a_info()
        assert info["version"] == "2.0.0"
        assert info["protocol"] == "Google A2A"
        assert "capabilities" in info
        assert "methods" in info
        assert "task_states" in info

    def test_info_capabilities(self):
        info = get_a2a_info()
        caps = info["capabilities"]
        assert caps["agent_card"] is True
        assert caps["task_lifecycle"] is True
        assert caps["json_rpc"] is True
        assert caps["remote_discovery"] is True

    def test_info_methods(self):
        info = get_a2a_info()
        assert "tasks/send" in info["methods"]
        assert "tasks/get" in info["methods"]
        assert "tasks/cancel" in info["methods"]
        assert "agents/info" in info["methods"]
        assert "agents/list" in info["methods"]

    def test_info_task_states(self):
        info = get_a2a_info()
        states = info["task_states"]
        assert "submitted" in states
        assert "working" in states
        assert "completed" in states
        assert "failed" in states
        assert "cancelled" in states

    def test_info_counters(self):
        info = get_a2a_info()
        assert "discovered_agents" in info
        assert "pending_tasks" in info
        assert "completed_tasks" in info
