"""Tests for the demo mode system (seeder, runner, and API endpoints).

Covers:
- seed_demo_data populates tasks, transactions, agents
- DemoRunner start/stop lifecycle
- /demo/start, /demo/stop, /demo/seed, /demo/status endpoints
- Auto-seed on startup with HIREWIRE_DEMO=1
- /activity and /stats endpoints
- Target: 20+ tests
"""

from __future__ import annotations

import asyncio
import os
import time

import pytest
import httpx

from src.api.main import app, _demo_runner, _running_tasks
from src.demo.runner import DemoRunner, DEMO_TASK_LIST
from src.demo.seeder import (
    seed_demo_data,
    DEMO_SCENARIOS,
    ACTIVE_TASKS,
    DEMO_AGENTS,
)
from src.mcp_servers.payment_hub import ledger
from src.mcp_servers.registry_server import registry
from src.storage import get_storage


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    """Async HTTP test client."""
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture(autouse=True)
def _clean_ledger():
    """Reset ledger between tests."""
    ledger.clear()
    yield
    ledger.clear()


@pytest.fixture(autouse=True)
def _clean_demo_runner():
    """Stop and reset demo runner between tests."""
    _demo_runner._running = False
    _demo_runner._task = None
    _demo_runner._tasks_submitted = 0
    _demo_runner._task_index = 0
    yield
    _demo_runner._running = False
    if _demo_runner._task is not None and not _demo_runner._task.done():
        _demo_runner._task.cancel()
    _demo_runner._task = None


@pytest.fixture(autouse=True)
def _clean_running_tasks():
    """Cancel stray background tasks."""
    _running_tasks.clear()
    yield
    for t in list(_running_tasks.values()):
        t.cancel()
    _running_tasks.clear()


@pytest.fixture(autouse=True)
def _clean_storage():
    """Clear all storage before each test to prevent cross-contamination."""
    get_storage().clear_all()
    yield


@pytest.fixture(autouse=True)
def _clean_demo_agents():
    """Remove demo agents after each test so they don't leak."""
    yield
    for a in DEMO_AGENTS:
        registry.unregister(a["name"])


# ---------------------------------------------------------------------------
# Seeder tests
# ---------------------------------------------------------------------------


class TestSeeder:
    def test_seed_creates_tasks(self):
        result = seed_demo_data()
        expected = len(DEMO_SCENARIOS) + len(ACTIVE_TASKS)
        assert result["tasks_created"] == expected

    def test_seed_creates_payments(self):
        result = seed_demo_data()
        assert result["payments_created"] >= len(DEMO_SCENARIOS)

    def test_seed_registers_agents(self):
        result = seed_demo_data()
        assert result["agents_registered"] == len(DEMO_AGENTS)

    def test_seed_tasks_in_storage(self):
        seed_demo_data()
        storage = get_storage()
        all_tasks = storage.list_tasks()
        assert len(all_tasks) >= len(DEMO_SCENARIOS) + len(ACTIVE_TASKS)

    def test_seed_completed_tasks_have_results(self):
        seed_demo_data()
        storage = get_storage()
        completed = storage.list_tasks(status="completed")
        assert len(completed) >= len(DEMO_SCENARIOS)
        for t in completed:
            assert t["result"] is not None

    def test_seed_completed_tasks_have_agent_response(self):
        """Completed tasks must have agent_response field in result."""
        seed_demo_data()
        storage = get_storage()
        completed = storage.list_tasks(status="completed")
        for t in completed:
            result = t["result"]
            assert "agent_response" in result
            assert len(result["agent_response"]) > 0

    def test_seed_completed_tasks_have_preview(self):
        """Completed tasks must have agent_response_preview."""
        seed_demo_data()
        storage = get_storage()
        completed = storage.list_tasks(status="completed")
        for t in completed:
            result = t["result"]
            assert "agent_response_preview" in result
            assert len(result["agent_response_preview"]) <= 150

    def test_seed_running_tasks_exist(self):
        seed_demo_data()
        storage = get_storage()
        running = storage.list_tasks(status="running")
        expected_running = sum(1 for t in ACTIVE_TASKS if t["status"] == "running")
        assert len(running) >= expected_running

    def test_seed_transactions_in_ledger(self):
        seed_demo_data()
        txs = ledger.get_transactions()
        assert len(txs) >= len(DEMO_SCENARIOS)

    def test_seed_agents_in_registry(self):
        seed_demo_data()
        for agent_def in DEMO_AGENTS:
            assert registry.get(agent_def["name"]) is not None

    def test_seed_idempotent_agents(self):
        """Calling seed twice doesn't duplicate agents."""
        r1 = seed_demo_data()
        r2 = seed_demo_data()
        # Second call should register 0 new agents
        assert r2["agents_registered"] == 0

    def test_seed_task_budgets_realistic(self):
        seed_demo_data()
        storage = get_storage()
        for t in storage.list_tasks():
            assert 0.50 <= t["budget_usd"] <= 5.00

    def test_seed_returns_gpt4o_count(self):
        """Seed result includes gpt4o_responses count."""
        result = seed_demo_data()
        assert "gpt4o_responses" in result
        # In test mode (mock), this will be 0
        assert result["gpt4o_responses"] >= 0


# ---------------------------------------------------------------------------
# DemoRunner tests
# ---------------------------------------------------------------------------


class TestDemoRunner:
    def test_runner_not_running_initially(self):
        runner = DemoRunner()
        assert runner.is_running is False

    @pytest.mark.asyncio
    async def test_runner_start_stop(self):
        runner = DemoRunner(interval=0.05)
        runner.start()
        assert runner.is_running is True
        await asyncio.sleep(0.15)
        runner.stop()
        assert runner.is_running is False

    @pytest.mark.asyncio
    async def test_runner_submits_tasks(self):
        runner = DemoRunner(interval=0.05)
        runner.start()
        await asyncio.sleep(0.15)
        runner.stop()
        assert runner._tasks_submitted >= 1

    @pytest.mark.asyncio
    async def test_runner_creates_db_tasks(self):
        storage = get_storage()
        before = len(storage.list_tasks())
        runner = DemoRunner(interval=0.05)
        runner.start()
        await asyncio.sleep(0.15)
        runner.stop()
        after = len(storage.list_tasks())
        assert after > before

    def test_runner_status_dict(self):
        runner = DemoRunner(interval=30.0)
        status = runner.status()
        assert "running" in status
        assert "tasks_submitted" in status
        assert "interval_seconds" in status

    @pytest.mark.asyncio
    async def test_runner_stop_idempotent(self):
        runner = DemoRunner()
        runner.stop()
        runner.stop()
        assert runner.is_running is False

    def test_demo_task_list_not_empty(self):
        assert len(DEMO_TASK_LIST) >= 10


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestDemoEndpoints:
    @pytest.mark.asyncio
    async def test_seed_endpoint_returns_200(self, client):
        resp = await client.get("/demo/seed")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "seeded"
        assert data["tasks_created"] > 0

    @pytest.mark.asyncio
    async def test_start_endpoint(self, client):
        resp = await client.get("/demo/start")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "started"
        assert data["running"] is True
        # Clean up
        _demo_runner.stop()

    @pytest.mark.asyncio
    async def test_start_already_running(self, client):
        await client.get("/demo/start")
        resp = await client.get("/demo/start")
        data = resp.json()
        assert data["status"] == "already_running"
        _demo_runner.stop()

    @pytest.mark.asyncio
    async def test_stop_endpoint(self, client):
        await client.get("/demo/start")
        resp = await client.get("/demo/stop")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "stopped"
        assert data["was_running"] is True

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self, client):
        resp = await client.get("/demo/stop")
        data = resp.json()
        assert data["status"] == "stopped"
        assert data["was_running"] is False

    @pytest.mark.asyncio
    async def test_status_endpoint(self, client):
        resp = await client.get("/demo/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "running" in data
        assert "tasks_submitted" in data

    @pytest.mark.asyncio
    async def test_seed_populates_dashboard_data(self, client):
        """After seeding, /health should show tasks and agents."""
        await client.get("/demo/seed")
        resp = await client.get("/health")
        data = resp.json()
        assert data["tasks_total"] >= len(DEMO_SCENARIOS)
        assert data["agents_count"] >= 3  # built-in + demo agents


# ---------------------------------------------------------------------------
# Activity and Stats endpoint tests
# ---------------------------------------------------------------------------


class TestActivityAndStats:
    @pytest.mark.asyncio
    async def test_activity_endpoint_empty(self, client):
        resp = await client.get("/activity")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_activity_endpoint_after_seed(self, client):
        await client.get("/demo/seed")
        resp = await client.get("/activity")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) > 0
        # Activity items have required fields
        for item in data:
            assert "type" in item
            assert "icon" in item
            assert "text" in item
            assert "time" in item

    @pytest.mark.asyncio
    async def test_stats_endpoint(self, client):
        await client.get("/demo/seed")
        resp = await client.get("/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_tasks" in data
        assert "completed" in data
        assert "total_spent_usdc" in data
        assert "agent_spend" in data
        assert "completion_rate" in data
        assert data["total_tasks"] > 0

    @pytest.mark.asyncio
    async def test_health_includes_gpt4o(self, client):
        """Health endpoint includes gpt4o_available field."""
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "gpt4o_available" in data
        assert "tasks_running" in data


# ---------------------------------------------------------------------------
# Startup auto-seed tests
# ---------------------------------------------------------------------------


class TestAutoSeed:
    @pytest.mark.asyncio
    async def test_startup_with_demo_env(self, client, monkeypatch):
        """With HIREWIRE_DEMO=1, startup should seed data."""
        monkeypatch.setenv("HIREWIRE_DEMO", "1")
        # Trigger the startup event manually
        from src.api.main import _on_startup
        await _on_startup()
        storage = get_storage()
        tasks = storage.list_tasks()
        assert len(tasks) >= len(DEMO_SCENARIOS)

    @pytest.mark.asyncio
    async def test_startup_without_demo_env(self, client, monkeypatch):
        """Without HIREWIRE_DEMO=1, startup should not seed."""
        monkeypatch.delenv("HIREWIRE_DEMO", raising=False)
        storage = get_storage()
        before = len(storage.list_tasks())
        from src.api.main import _on_startup
        await _on_startup()
        after = len(storage.list_tasks())
        # No new tasks should be created
        assert after == before
