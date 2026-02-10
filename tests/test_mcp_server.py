"""Tests for HireWire MCP Server integration (Sprint 28).

Covers:
- MCP server creation and tool listing
- Individual tool handlers (create_task, get_task, list_tasks, etc.)
- Marketplace search and hiring tools
- Payment and budget tools
- REST API endpoints (/mcp/tools, /mcp/invoke)
- Error handling (invalid tool, bad arguments)
- SDK MCP tools (enhanced mcp_tools.py)
- Tool info and metadata
- End-to-end flows (create → get → list → pay → check)
"""

from __future__ import annotations

import json
import pytest
from fastapi.testclient import TestClient

from src.mcp_server import (
    create_hirewire_mcp_server,
    MCP_TOOLS,
    _HANDLERS,
    _handle_create_task,
    _handle_get_task,
    _handle_list_tasks,
    _handle_hire_agent,
    _handle_list_agents,
    _handle_marketplace_search,
    _handle_check_budget,
    _handle_check_payment_status,
    _handle_pay_agent,
    _handle_get_metrics,
)
from src.integrations.mcp_tools import (
    HIREWIRE_SDK_TOOLS,
    get_mcp_tool_info,
    create_task_tool,
    list_tasks_tool,
    get_task_tool,
    hire_agent_tool,
    marketplace_search_tool,
    check_payment_status_tool,
    submit_task_tool,
    list_agents_tool,
    check_budget_tool,
    agent_metrics_tool,
    x402_payment_tool,
    create_hirewire_mcp_agent,
    create_mcp_server,
)
from src.agents._mock_client import MockChatClient
from src.api.main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def _seed_task():
    """Seed a task into storage and return its ID."""
    from src.storage import get_storage
    import time
    storage = get_storage()
    task_id = "test_mcp_task_001"
    storage.save_task(
        task_id=task_id,
        description="Test task for MCP server",
        workflow="ceo",
        budget_usd=5.0,
        status="pending",
        created_at=time.time(),
    )
    return task_id


@pytest.fixture
def _seed_budget():
    """Seed a budget allocation."""
    from src.mcp_servers.payment_hub import ledger
    ledger.allocate_budget("test_budget_task", 10.0)
    return "test_budget_task"


@pytest.fixture
def _seed_payment():
    """Seed a payment transaction."""
    from src.mcp_servers.payment_hub import ledger
    ledger.allocate_budget("test_pay_task", 20.0)
    ledger.record_payment(
        from_agent="ceo",
        to_agent="builder",
        amount=1.5,
        task_id="test_pay_task",
    )
    return "test_pay_task"


# ===================================================================
# 1. MCP Server Creation
# ===================================================================


class TestMCPServerCreation:
    def test_create_server(self):
        server = create_hirewire_mcp_server()
        assert server is not None

    def test_server_name(self):
        server = create_hirewire_mcp_server()
        assert server.name == "hirewire"

    def test_mcp_tools_defined(self):
        assert len(MCP_TOOLS) == 10

    def test_tool_names(self):
        names = {t.name for t in MCP_TOOLS}
        expected = {
            "create_task", "get_task", "list_tasks", "hire_agent",
            "list_agents", "marketplace_search", "check_budget",
            "check_payment_status", "pay_agent", "get_metrics",
        }
        assert names == expected

    def test_all_tools_have_descriptions(self):
        for t in MCP_TOOLS:
            assert t.description, f"Tool {t.name} has no description"

    def test_all_tools_have_input_schemas(self):
        for t in MCP_TOOLS:
            assert t.inputSchema is not None
            assert t.inputSchema.get("type") == "object"

    def test_handlers_registered(self):
        assert len(_HANDLERS) == 10
        for t in MCP_TOOLS:
            assert t.name in _HANDLERS, f"No handler for tool: {t.name}"


# ===================================================================
# 2. create_task handler
# ===================================================================


class TestCreateTask:
    def test_create_basic_task(self):
        result = json.loads(_handle_create_task({"description": "Test task"}))
        assert result["task_id"].startswith("mcp_")
        assert result["description"] == "Test task"
        assert result["status"] == "pending"
        assert result["budget_usd"] == 1.0

    def test_create_task_with_budget(self):
        result = json.loads(_handle_create_task({"description": "Expensive task", "budget": 50.0}))
        assert result["budget_usd"] == 50.0

    def test_create_task_with_workflow(self):
        result = json.loads(_handle_create_task({
            "description": "Custom workflow",
            "workflow": "sequential",
        }))
        assert result["task_id"].startswith("mcp_")

    def test_create_task_has_timestamp(self):
        result = json.loads(_handle_create_task({"description": "Timestamped"}))
        assert "created_at" in result
        assert result["created_at"] > 0

    def test_created_task_persists(self):
        result = json.loads(_handle_create_task({"description": "Persistent task"}))
        task_id = result["task_id"]
        fetched = json.loads(_handle_get_task({"task_id": task_id}))
        assert fetched["task_id"] == task_id
        assert fetched["description"] == "Persistent task"


# ===================================================================
# 3. get_task handler
# ===================================================================


class TestGetTask:
    def test_get_existing_task(self, _seed_task):
        result = json.loads(_handle_get_task({"task_id": _seed_task}))
        assert result["task_id"] == _seed_task
        assert result["description"] == "Test task for MCP server"

    def test_get_nonexistent_task(self):
        result = json.loads(_handle_get_task({"task_id": "nonexistent_task_xyz"}))
        assert "error" in result

    def test_get_task_fields(self, _seed_task):
        result = json.loads(_handle_get_task({"task_id": _seed_task}))
        assert "task_id" in result
        assert "description" in result
        assert "status" in result
        assert "budget_usd" in result
        assert "created_at" in result


# ===================================================================
# 4. list_tasks handler
# ===================================================================


class TestListTasks:
    def test_list_all_tasks(self, _seed_task):
        result = json.loads(_handle_list_tasks({"status": "all"}))
        assert "count" in result
        assert "tasks" in result
        assert result["count"] >= 1

    def test_list_pending_tasks(self, _seed_task):
        result = json.loads(_handle_list_tasks({"status": "pending"}))
        assert result["count"] >= 1
        for t in result["tasks"]:
            assert t["status"] == "pending"

    def test_list_completed_tasks(self):
        result = json.loads(_handle_list_tasks({"status": "completed"}))
        assert result["count"] >= 0
        for t in result["tasks"]:
            assert t["status"] == "completed"

    def test_list_default_all(self):
        result = json.loads(_handle_list_tasks({}))
        assert "count" in result

    def test_task_fields_in_list(self, _seed_task):
        result = json.loads(_handle_list_tasks({"status": "all"}))
        if result["tasks"]:
            task = result["tasks"][0]
            assert "task_id" in task
            assert "description" in task
            assert "status" in task
            assert "budget_usd" in task


# ===================================================================
# 5. hire_agent handler
# ===================================================================


class TestHireAgent:
    def test_hire_basic(self):
        result = json.loads(_handle_hire_agent({
            "description": "Build a landing page",
            "required_skills": ["code"],
            "budget": 5.0,
        }))
        assert result["status"] in ("completed", "hired", "no_agents")
        assert "task_id" in result

    def test_hire_with_skills(self):
        result = json.loads(_handle_hire_agent({
            "description": "Research market trends",
            "required_skills": ["search", "analysis"],
            "budget": 3.0,
        }))
        assert "task_id" in result

    def test_hire_no_skills(self):
        result = json.loads(_handle_hire_agent({
            "description": "General task",
            "budget": 2.0,
        }))
        assert "task_id" in result

    def test_hire_very_low_budget(self):
        result = json.loads(_handle_hire_agent({
            "description": "Cheap task",
            "required_skills": ["code"],
            "budget": 0.001,
        }))
        assert "status" in result


# ===================================================================
# 6. list_agents handler
# ===================================================================


class TestListAgents:
    def test_list_agents(self):
        result = json.loads(_handle_list_agents({}))
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_agents_have_fields(self):
        result = json.loads(_handle_list_agents({}))
        for agent in result:
            assert "name" in agent
            assert "description" in agent
            assert "skills" in agent


# ===================================================================
# 7. marketplace_search handler
# ===================================================================


class TestMarketplaceSearch:
    def test_search_by_skill(self):
        result = json.loads(_handle_marketplace_search({"query": "code"}))
        assert "count" in result
        assert "agents" in result

    def test_search_by_design(self):
        result = json.loads(_handle_marketplace_search({"query": "design"}))
        assert "count" in result

    def test_search_with_max_price(self):
        result = json.loads(_handle_marketplace_search({
            "query": "code",
            "max_price": 0.001,
        }))
        assert "count" in result

    def test_search_no_results(self):
        result = json.loads(_handle_marketplace_search({"query": "quantum_teleportation_xyz"}))
        assert result["count"] == 0


# ===================================================================
# 8. check_budget handler
# ===================================================================


class TestCheckBudget:
    def test_check_existing_budget(self, _seed_budget):
        result = json.loads(_handle_check_budget({"task_id": _seed_budget}))
        assert result["allocated"] == 10.0
        assert result["remaining"] == 10.0

    def test_check_nonexistent_budget(self):
        result = json.loads(_handle_check_budget({"task_id": "no_budget_task"}))
        assert "error" in result


# ===================================================================
# 9. check_payment_status handler
# ===================================================================


class TestCheckPaymentStatus:
    def test_check_with_payment(self, _seed_payment):
        result = json.loads(_handle_check_payment_status({"task_id": _seed_payment}))
        assert result["task_id"] == _seed_payment
        assert result["transaction_count"] >= 1
        assert len(result["transactions"]) >= 1

    def test_check_no_payments(self):
        result = json.loads(_handle_check_payment_status({"task_id": "empty_task"}))
        assert result["transaction_count"] == 0

    def test_payment_fields(self, _seed_payment):
        result = json.loads(_handle_check_payment_status({"task_id": _seed_payment}))
        tx = result["transactions"][0]
        assert "tx_id" in tx
        assert "from_agent" in tx
        assert "to_agent" in tx
        assert "amount_usdc" in tx
        assert "status" in tx


# ===================================================================
# 10. pay_agent handler
# ===================================================================


class TestPayAgent:
    def test_pay_basic(self):
        result = json.loads(_handle_pay_agent({
            "to_agent": "builder",
            "amount": 0.5,
            "task_id": "pay_test_001",
        }))
        assert result["status"] == "completed"
        assert result["amount_usdc"] == 0.5
        assert result["to_agent"] == "builder"
        assert "tx_id" in result

    def test_pay_external_agent(self):
        result = json.loads(_handle_pay_agent({
            "to_agent": "designer-ext-001",
            "amount": 0.05,
            "task_id": "pay_test_002",
        }))
        assert result["status"] == "completed"
        assert result["network"] == "eip155:8453"


# ===================================================================
# 11. get_metrics handler
# ===================================================================


class TestGetMetrics:
    def test_system_metrics(self):
        result = json.loads(_handle_get_metrics({"agent_name": "all"}))
        assert isinstance(result, dict)

    def test_agent_metrics(self):
        result = json.loads(_handle_get_metrics({"agent_name": "builder"}))
        assert isinstance(result, dict)

    def test_default_all(self):
        result = json.loads(_handle_get_metrics({}))
        assert isinstance(result, dict)


# ===================================================================
# 12. REST API: GET /mcp/tools
# ===================================================================


class TestMCPToolsEndpoint:
    def test_list_tools(self, client):
        resp = client.get("/mcp/tools")
        assert resp.status_code == 200
        data = resp.json()
        assert data["server"] == "hirewire"
        assert data["tool_count"] == 10
        assert len(data["tools"]) == 10

    def test_tool_schema(self, client):
        resp = client.get("/mcp/tools")
        tools = resp.json()["tools"]
        for t in tools:
            assert "name" in t
            assert "description" in t
            assert "inputSchema" in t

    def test_tool_names_in_response(self, client):
        resp = client.get("/mcp/tools")
        names = {t["name"] for t in resp.json()["tools"]}
        assert "create_task" in names
        assert "hire_agent" in names
        assert "marketplace_search" in names
        assert "pay_agent" in names


# ===================================================================
# 13. REST API: POST /mcp/invoke
# ===================================================================


class TestMCPInvokeEndpoint:
    def test_invoke_create_task(self, client):
        resp = client.post("/mcp/invoke", json={
            "tool": "create_task",
            "arguments": {"description": "API-created task", "budget": 2.0},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["tool"] == "create_task"
        assert data["result"]["status"] == "pending"

    def test_invoke_list_tasks(self, client):
        resp = client.post("/mcp/invoke", json={
            "tool": "list_tasks",
            "arguments": {"status": "all"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "count" in data["result"]

    def test_invoke_list_agents(self, client):
        resp = client.post("/mcp/invoke", json={
            "tool": "list_agents",
            "arguments": {},
        })
        assert resp.status_code == 200

    def test_invoke_marketplace_search(self, client):
        resp = client.post("/mcp/invoke", json={
            "tool": "marketplace_search",
            "arguments": {"query": "code"},
        })
        assert resp.status_code == 200

    def test_invoke_unknown_tool(self, client):
        resp = client.post("/mcp/invoke", json={
            "tool": "nonexistent_tool",
            "arguments": {},
        })
        assert resp.status_code == 404
        assert "Unknown tool" in resp.json()["detail"]

    def test_invoke_missing_tool_field(self, client):
        resp = client.post("/mcp/invoke", json={"arguments": {}})
        assert resp.status_code == 400

    def test_invoke_pay_agent(self, client):
        resp = client.post("/mcp/invoke", json={
            "tool": "pay_agent",
            "arguments": {"to_agent": "builder", "amount": 0.1, "task_id": "api_pay"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"]["status"] == "completed"

    def test_invoke_get_metrics(self, client):
        resp = client.post("/mcp/invoke", json={
            "tool": "get_metrics",
            "arguments": {"agent_name": "all"},
        })
        assert resp.status_code == 200


# ===================================================================
# 14. SDK MCP Tools (enhanced mcp_tools.py)
# ===================================================================


class TestSDKMCPToolsEnhanced:
    def test_tool_count(self):
        assert len(HIREWIRE_SDK_TOOLS) == 11

    def test_new_tools_present(self):
        info = get_mcp_tool_info()
        names = [t["name"] for t in info]
        assert "hirewire_create_task" in names
        assert "hirewire_list_tasks" in names
        assert "hirewire_get_task" in names
        assert "hirewire_hire_agent" in names
        assert "hirewire_marketplace_search" in names
        assert "hirewire_check_payment_status" in names

    def test_all_tools_have_info(self):
        info = get_mcp_tool_info()
        assert len(info) == 11
        for t in info:
            assert "name" in t
            assert "description" in t
            assert t["type"] == "sdk_tool"
            assert t["framework"] == "agent_framework"

    def test_create_task_tool_function(self):
        # The SDK @tool function returns a string
        from src.integrations.mcp_tools import create_task_tool
        # Can't call directly with @tool decorator, but verify it's in the list
        assert create_task_tool in HIREWIRE_SDK_TOOLS

    def test_list_tasks_tool_in_list(self):
        assert list_tasks_tool in HIREWIRE_SDK_TOOLS

    def test_get_task_tool_in_list(self):
        assert get_task_tool in HIREWIRE_SDK_TOOLS

    def test_hire_agent_tool_in_list(self):
        assert hire_agent_tool in HIREWIRE_SDK_TOOLS

    def test_marketplace_search_tool_in_list(self):
        assert marketplace_search_tool in HIREWIRE_SDK_TOOLS

    def test_check_payment_status_tool_in_list(self):
        assert check_payment_status_tool in HIREWIRE_SDK_TOOLS

    def test_original_tools_still_present(self):
        assert submit_task_tool in HIREWIRE_SDK_TOOLS
        assert list_agents_tool in HIREWIRE_SDK_TOOLS
        assert check_budget_tool in HIREWIRE_SDK_TOOLS
        assert agent_metrics_tool in HIREWIRE_SDK_TOOLS
        assert x402_payment_tool in HIREWIRE_SDK_TOOLS


# ===================================================================
# 15. MCP Agent (SDK wrapper)
# ===================================================================


class TestMCPAgentEnhanced:
    def test_create_mcp_agent(self):
        agent = create_hirewire_mcp_agent(MockChatClient())
        assert agent.name == "HireWire"
        assert "marketplace" in agent.description.lower()
        assert "hire" in agent.description.lower()

    def test_mcp_server_creation(self):
        server = create_mcp_server(MockChatClient())
        assert server is not None


# ===================================================================
# 16. End-to-end flow: create → get → list → pay → check
# ===================================================================


class TestEndToEndMCPFlow:
    def test_full_task_lifecycle(self, client):
        # Step 1: Create a task
        resp = client.post("/mcp/invoke", json={
            "tool": "create_task",
            "arguments": {"description": "E2E test task", "budget": 10.0},
        })
        assert resp.status_code == 200
        task_id = resp.json()["result"]["task_id"]

        # Step 2: Get the task
        resp = client.post("/mcp/invoke", json={
            "tool": "get_task",
            "arguments": {"task_id": task_id},
        })
        assert resp.status_code == 200
        assert resp.json()["result"]["task_id"] == task_id
        assert resp.json()["result"]["status"] == "pending"

        # Step 3: List tasks includes our task
        resp = client.post("/mcp/invoke", json={
            "tool": "list_tasks",
            "arguments": {"status": "all"},
        })
        assert resp.status_code == 200
        task_ids = [t["task_id"] for t in resp.json()["result"]["tasks"]]
        assert task_id in task_ids

        # Step 4: Pay an agent for this task
        resp = client.post("/mcp/invoke", json={
            "tool": "pay_agent",
            "arguments": {"to_agent": "builder", "amount": 0.5, "task_id": task_id},
        })
        assert resp.status_code == 200
        assert resp.json()["result"]["status"] == "completed"

        # Step 5: Check payment status
        resp = client.post("/mcp/invoke", json={
            "tool": "check_payment_status",
            "arguments": {"task_id": task_id},
        })
        assert resp.status_code == 200
        payment_data = resp.json()["result"]
        assert payment_data["transaction_count"] >= 1

    def test_search_then_hire_flow(self, client):
        # Search for agents with code skills
        resp = client.post("/mcp/invoke", json={
            "tool": "marketplace_search",
            "arguments": {"query": "code"},
        })
        assert resp.status_code == 200

        # Hire an agent
        resp = client.post("/mcp/invoke", json={
            "tool": "hire_agent",
            "arguments": {
                "description": "Build a REST API",
                "required_skills": ["code", "testing"],
                "budget": 5.0,
            },
        })
        assert resp.status_code == 200
        hire_result = resp.json()["result"]
        assert hire_result["status"] in ("completed", "hired", "no_agents")


# ===================================================================
# 17. Error handling
# ===================================================================


class TestErrorHandling:
    def test_get_task_not_found(self):
        result = json.loads(_handle_get_task({"task_id": "does_not_exist_12345"}))
        assert "error" in result

    def test_check_budget_not_found(self):
        result = json.loads(_handle_check_budget({"task_id": "no_budget_here"}))
        assert "error" in result

    def test_invoke_empty_body(self, client):
        resp = client.post("/mcp/invoke", json={})
        assert resp.status_code == 400

    def test_invoke_invalid_tool(self, client):
        resp = client.post("/mcp/invoke", json={
            "tool": "definitely_not_a_tool",
            "arguments": {},
        })
        assert resp.status_code == 404
        assert "Available tools" in resp.json()["detail"]
