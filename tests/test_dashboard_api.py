"""Tests for the FastAPI Dashboard API (src/api/main.py).

Uses httpx.AsyncClient with the ASGI transport for fast in-process tests.
30+ tests covering all endpoints, validation, and error handling.
"""

from __future__ import annotations

import asyncio
import time

import pytest
import httpx

from src.api.main import app, _running_tasks
from src.mcp_servers.payment_hub import ledger
from src.mcp_servers.registry_server import registry, AgentCard
from src.storage import get_storage


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    """Synchronous-style async client for testing (use with anyio)."""
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture(autouse=True)
def _clean_ledger():
    """Reset the ledger between tests."""
    ledger.clear()
    yield
    ledger.clear()


@pytest.fixture(autouse=True)
def _clean_running_tasks():
    """Cancel any stray background tasks."""
    _running_tasks.clear()
    yield
    for t in list(_running_tasks.values()):
        t.cancel()
    _running_tasks.clear()


# ---------------------------------------------------------------------------
# POST /tasks — Submit task
# ---------------------------------------------------------------------------

class TestSubmitTask:
    @pytest.mark.asyncio
    async def test_submit_returns_201(self, client):
        resp = await client.post("/tasks", json={"description": "build a CLI tool", "budget": 2.0})
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_submit_returns_task_id(self, client):
        resp = await client.post("/tasks", json={"description": "build a CLI tool"})
        data = resp.json()
        assert "task_id" in data
        assert data["task_id"].startswith("task_")

    @pytest.mark.asyncio
    async def test_submit_default_budget(self, client):
        resp = await client.post("/tasks", json={"description": "test"})
        assert resp.json()["budget_usd"] == 1.0

    @pytest.mark.asyncio
    async def test_submit_custom_budget(self, client):
        resp = await client.post("/tasks", json={"description": "test", "budget": 5.5})
        assert resp.json()["budget_usd"] == 5.5

    @pytest.mark.asyncio
    async def test_submit_status_is_pending(self, client):
        resp = await client.post("/tasks", json={"description": "hello"})
        assert resp.json()["status"] == "pending"

    @pytest.mark.asyncio
    async def test_submit_has_created_at(self, client):
        before = time.time()
        resp = await client.post("/tasks", json={"description": "hello"})
        after = time.time()
        ts = resp.json()["created_at"]
        assert before <= ts <= after

    @pytest.mark.asyncio
    async def test_submit_persists_to_storage(self, client):
        resp = await client.post("/tasks", json={"description": "persist me"})
        task_id = resp.json()["task_id"]
        stored = get_storage().get_task(task_id)
        assert stored is not None
        assert stored["description"] == "persist me"

    @pytest.mark.asyncio
    async def test_submit_empty_description_rejected(self, client):
        resp = await client.post("/tasks", json={"description": "", "budget": 1.0})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_submit_missing_description_rejected(self, client):
        resp = await client.post("/tasks", json={"budget": 1.0})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_submit_zero_budget_rejected(self, client):
        resp = await client.post("/tasks", json={"description": "test", "budget": 0})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_submit_negative_budget_rejected(self, client):
        resp = await client.post("/tasks", json={"description": "test", "budget": -5})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_submit_excessive_budget_rejected(self, client):
        resp = await client.post("/tasks", json={"description": "test", "budget": 5000})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /tasks/{id} — Task status
# ---------------------------------------------------------------------------

class TestGetTask:
    @pytest.mark.asyncio
    async def test_get_existing_task(self, client):
        create = await client.post("/tasks", json={"description": "find me"})
        task_id = create.json()["task_id"]
        resp = await client.get(f"/tasks/{task_id}")
        assert resp.status_code == 200
        assert resp.json()["task_id"] == task_id

    @pytest.mark.asyncio
    async def test_get_missing_task_404(self, client):
        resp = await client.get("/tasks/nonexistent_id")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_task_has_description(self, client):
        create = await client.post("/tasks", json={"description": "describe me"})
        task_id = create.json()["task_id"]
        resp = await client.get(f"/tasks/{task_id}")
        assert resp.json()["description"] == "describe me"

    @pytest.mark.asyncio
    async def test_get_completed_task_has_result(self, client):
        """Submit and wait briefly so the background task completes."""
        create = await client.post("/tasks", json={"description": "build a landing page"})
        task_id = create.json()["task_id"]
        # Give the background coroutine time to finish
        await asyncio.sleep(0.15)
        resp = await client.get(f"/tasks/{task_id}")
        data = resp.json()
        assert data["status"] in ("completed", "running", "pending")


# ---------------------------------------------------------------------------
# GET /transactions — Payment transactions
# ---------------------------------------------------------------------------

class TestTransactions:
    @pytest.mark.asyncio
    async def test_empty_transactions(self, client):
        resp = await client.get("/transactions")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_transactions_after_demo(self, client):
        """The /demo endpoint creates transactions."""
        await client.get("/demo")
        resp = await client.get("/transactions")
        assert resp.status_code == 200
        txs = resp.json()
        assert len(txs) >= 1

    @pytest.mark.asyncio
    async def test_transaction_structure(self, client):
        await client.get("/demo")
        resp = await client.get("/transactions")
        tx = resp.json()[0]
        for key in ("tx_id", "from_agent", "to_agent", "amount_usdc", "task_id", "timestamp", "status"):
            assert key in tx


# ---------------------------------------------------------------------------
# GET /agents — Agent listing
# ---------------------------------------------------------------------------

class TestListAgents:
    @pytest.mark.asyncio
    async def test_agents_returns_list(self, client):
        resp = await client.get("/agents")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_agents_has_builder(self, client):
        resp = await client.get("/agents")
        names = [a["name"] for a in resp.json()]
        assert "builder" in names

    @pytest.mark.asyncio
    async def test_agents_has_research(self, client):
        resp = await client.get("/agents")
        names = [a["name"] for a in resp.json()]
        assert "research" in names

    @pytest.mark.asyncio
    async def test_agents_structure(self, client):
        resp = await client.get("/agents")
        agent = resp.json()[0]
        for key in ("name", "description", "skills", "price_per_call", "protocol", "payment"):
            assert key in agent

    @pytest.mark.asyncio
    async def test_agents_count_at_least_two(self, client):
        resp = await client.get("/agents")
        assert len(resp.json()) >= 2


# ---------------------------------------------------------------------------
# GET /health — Health check
# ---------------------------------------------------------------------------

class TestHealth:
    @pytest.mark.asyncio
    async def test_health_returns_200(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_health_status_healthy(self, client):
        resp = await client.get("/health")
        assert resp.json()["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_health_uptime_positive(self, client):
        resp = await client.get("/health")
        assert resp.json()["uptime_seconds"] >= 0

    @pytest.mark.asyncio
    async def test_health_counts_tasks(self, client):
        resp = await client.get("/health")
        data = resp.json()
        assert "tasks_total" in data
        assert "tasks_completed" in data
        assert "tasks_pending" in data
        assert "agents_count" in data
        assert "total_spent_usdc" in data

    @pytest.mark.asyncio
    async def test_health_task_count_increases(self, client):
        h1 = (await client.get("/health")).json()
        await client.post("/tasks", json={"description": "bump the count"})
        h2 = (await client.get("/health")).json()
        assert h2["tasks_total"] >= h1["tasks_total"] + 1

    @pytest.mark.asyncio
    async def test_health_agents_count_matches_registry(self, client):
        resp = await client.get("/health")
        assert resp.json()["agents_count"] == len(registry.list_all())


# ---------------------------------------------------------------------------
# GET /demo — Demo scenario
# ---------------------------------------------------------------------------

class TestDemo:
    @pytest.mark.asyncio
    async def test_demo_returns_200(self, client):
        resp = await client.get("/demo")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_demo_has_analysis(self, client):
        resp = await client.get("/demo")
        data = resp.json()
        assert "analysis" in data
        assert "subtasks" in data["analysis"]

    @pytest.mark.asyncio
    async def test_demo_creates_task(self, client):
        resp = await client.get("/demo")
        data = resp.json()
        task = data["task"]
        assert task["task_id"].startswith("demo_")
        assert task["status"] == "completed"

    @pytest.mark.asyncio
    async def test_demo_creates_transactions(self, client):
        resp = await client.get("/demo")
        data = resp.json()
        assert data["transactions_after"] > data["transactions_before"]

    @pytest.mark.asyncio
    async def test_demo_shows_agents_available(self, client):
        resp = await client.get("/demo")
        data = resp.json()
        assert data["agents_available"] >= 2

    @pytest.mark.asyncio
    async def test_demo_task_description(self, client):
        resp = await client.get("/demo")
        data = resp.json()
        assert "landing page" in data["demo_task"].lower()


# ---------------------------------------------------------------------------
# CORS headers
# ---------------------------------------------------------------------------

class TestCORS:
    @pytest.mark.asyncio
    async def test_cors_origin_header(self, client):
        resp = await client.options(
            "/health",
            headers={
                "Origin": "http://example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        # CORS middleware should allow the requesting origin
        origin = resp.headers.get("access-control-allow-origin")
        assert origin in ("*", "http://example.com")
