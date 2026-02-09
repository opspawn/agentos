"""Integration tests for the task execution engine.

Submits tasks via the API and verifies they run through
workflows to completion using the mock client.
"""

from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.api.server import _tasks, _background_tasks, app


@pytest.fixture(autouse=True)
def _clear_task_store():
    """Reset in-memory stores between tests."""
    _tasks.clear()
    _background_tasks.clear()
    yield
    _tasks.clear()
    _background_tasks.clear()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _submit_and_wait(client: AsyncClient, payload: dict, timeout: float = 5.0) -> dict:
    """Submit a task and poll until it reaches a terminal state."""
    resp = await client.post("/tasks", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    task_id = data["task_id"]

    # Wait for background task to finish
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        resp = await client.get(f"/tasks/{task_id}")
        assert resp.status_code == 200
        status = resp.json()["status"]
        if status in ("completed", "failed"):
            return resp.json()
        await asyncio.sleep(0.05)

    raise TimeoutError(f"Task {task_id} did not complete within {timeout}s")


class TestTaskExecution:
    """Test that submitted tasks actually run through workflows."""

    @pytest.mark.asyncio
    async def test_sequential_task_completes(self, client):
        result = await _submit_and_wait(client, {
            "description": "Build a hello world app",
            "workflow": "sequential",
            "budget_usd": 1.0,
        })
        assert result["status"] == "completed"
        assert result["result"] is not None
        assert result["result"]["workflow"] == "sequential"

    @pytest.mark.asyncio
    async def test_concurrent_task_completes(self, client):
        result = await _submit_and_wait(client, {
            "description": "Research and build in parallel",
            "workflow": "concurrent",
            "budget_usd": 2.0,
        })
        assert result["status"] == "completed"
        assert result["result"] is not None
        assert result["result"]["workflow"] == "concurrent"

    @pytest.mark.asyncio
    async def test_group_chat_task_completes(self, client):
        result = await _submit_and_wait(client, {
            "description": "Collaborate on a complex feature",
            "workflow": "group_chat",
            "budget_usd": 5.0,
        })
        assert result["status"] == "completed"
        assert result["result"] is not None
        assert result["result"]["workflow"] == "group_chat"

    @pytest.mark.asyncio
    async def test_task_returns_pending_immediately(self, client):
        """POST /tasks should return before the workflow finishes."""
        resp = await client.post("/tasks", json={
            "description": "Quick task",
            "workflow": "sequential",
        })
        assert resp.status_code == 200
        data = resp.json()
        # Status should be pending or running (background task may start instantly)
        assert data["status"] in ("pending", "running")

    @pytest.mark.asyncio
    async def test_result_contains_output(self, client):
        result = await _submit_and_wait(client, {
            "description": "Analyze market data",
            "workflow": "sequential",
        })
        assert result["status"] == "completed"
        output = result["result"]["output"]
        assert "MockLLM" in output

    @pytest.mark.asyncio
    async def test_task_not_found(self, client):
        resp = await client.get("/tasks/task_nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_multiple_tasks_run_concurrently(self, client):
        """Submit several tasks and verify all complete."""
        tasks = []
        for wf in ["sequential", "concurrent", "group_chat"]:
            resp = await client.post("/tasks", json={
                "description": f"Test {wf} workflow",
                "workflow": wf,
                "budget_usd": 1.0,
            })
            assert resp.status_code == 200
            tasks.append(resp.json()["task_id"])

        # Wait for all to complete
        for task_id in tasks:
            deadline = asyncio.get_event_loop().time() + 10.0
            while asyncio.get_event_loop().time() < deadline:
                resp = await client.get(f"/tasks/{task_id}")
                if resp.json()["status"] == "completed":
                    break
                await asyncio.sleep(0.05)
            else:
                raise TimeoutError(f"Task {task_id} did not complete")
            assert resp.json()["status"] == "completed"

    @pytest.mark.asyncio
    async def test_budget_allocated_for_task(self, client):
        resp = await client.post("/tasks", json={
            "description": "Budget test",
            "workflow": "sequential",
            "budget_usd": 42.0,
        })
        task_id = resp.json()["task_id"]
        budget_resp = await client.get(f"/budget/{task_id}")
        assert budget_resp.status_code == 200
        assert budget_resp.json()["allocated"] == 42.0

    @pytest.mark.asyncio
    async def test_list_tasks_shows_submitted(self, client):
        await client.post("/tasks", json={
            "description": "List test",
            "workflow": "concurrent",
        })
        resp = await client.get("/tasks")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    @pytest.mark.asyncio
    async def test_default_workflow_is_sequential(self, client):
        resp = await client.post("/tasks", json={
            "description": "Default workflow test",
        })
        assert resp.status_code == 200
        assert resp.json()["workflow"] == "sequential"
