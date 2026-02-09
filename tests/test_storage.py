"""Tests for SQLite storage layer.

Covers CRUD operations for all three tables (tasks, payments, agents)
plus budget tracking, WAL mode, and async operations.
"""

from __future__ import annotations

import asyncio
import os
import tempfile

import pytest
import pytest_asyncio

from src.storage import SQLiteStorage


@pytest.fixture
def storage():
    """Create a fresh SQLiteStorage with a temporary database."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_storage.db")
    return SQLiteStorage(db_path)


# ──────────────────────────────────────────────
# Tasks CRUD
# ──────────────────────────────────────────────

class TestTaskStorage:
    def test_save_and_get_task(self, storage):
        storage.save_task(
            task_id="t1",
            description="Build a REST API",
            workflow="sequential",
            budget_usd=5.0,
            status="pending",
            created_at=1700000000.0,
        )
        task = storage.get_task("t1")
        assert task is not None
        assert task["task_id"] == "t1"
        assert task["description"] == "Build a REST API"
        assert task["workflow"] == "sequential"
        assert task["budget_usd"] == 5.0
        assert task["status"] == "pending"
        assert task["created_at"] == 1700000000.0
        assert task["result"] is None

    def test_get_nonexistent_task(self, storage):
        assert storage.get_task("nope") is None

    def test_update_task_status(self, storage):
        storage.save_task(
            task_id="t2",
            description="Test task",
            workflow="concurrent",
            budget_usd=1.0,
        )
        storage.update_task_status("t2", "completed", {"output": "done"})
        task = storage.get_task("t2")
        assert task["status"] == "completed"
        assert task["result"] == {"output": "done"}

    def test_list_tasks_all(self, storage):
        for i in range(3):
            storage.save_task(
                task_id=f"t{i}",
                description=f"Task {i}",
                workflow="sequential",
                budget_usd=1.0,
                status="pending" if i < 2 else "completed",
            )
        all_tasks = storage.list_tasks()
        assert len(all_tasks) == 3

    def test_list_tasks_filtered(self, storage):
        storage.save_task(task_id="a", description="A", workflow="sequential", budget_usd=1.0, status="pending")
        storage.save_task(task_id="b", description="B", workflow="sequential", budget_usd=1.0, status="completed")
        storage.save_task(task_id="c", description="C", workflow="sequential", budget_usd=1.0, status="pending")

        pending = storage.list_tasks(status="pending")
        assert len(pending) == 2
        assert all(t["status"] == "pending" for t in pending)

    def test_count_tasks(self, storage):
        storage.save_task(task_id="x", description="X", workflow="sequential", budget_usd=1.0, status="running")
        storage.save_task(task_id="y", description="Y", workflow="sequential", budget_usd=1.0, status="running")
        assert storage.count_tasks() == 2
        assert storage.count_tasks(status="running") == 2
        assert storage.count_tasks(status="completed") == 0

    def test_clear_tasks(self, storage):
        storage.save_task(task_id="del1", description="D", workflow="sequential", budget_usd=1.0)
        storage.clear_tasks()
        assert storage.list_tasks() == []

    def test_task_result_json_roundtrip(self, storage):
        complex_result = {
            "output": "hello",
            "nested": {"key": [1, 2, 3]},
            "status": "completed",
        }
        storage.save_task(
            task_id="json1",
            description="JSON test",
            workflow="group_chat",
            budget_usd=2.0,
            result=complex_result,
        )
        task = storage.get_task("json1")
        assert task["result"] == complex_result


# ──────────────────────────────────────────────
# Payments CRUD
# ──────────────────────────────────────────────

class TestPaymentStorage:
    def test_save_and_get_payment(self, storage):
        storage.save_payment(
            tx_id="tx_000001",
            from_agent="ceo",
            to_agent="designer",
            amount_usdc=0.05,
            task_id="t1",
            timestamp=1700000000.0,
            status="completed",
        )
        payments = storage.get_payments("t1")
        assert len(payments) == 1
        assert payments[0]["tx_id"] == "tx_000001"
        assert payments[0]["from_agent"] == "ceo"
        assert payments[0]["to_agent"] == "designer"
        assert payments[0]["amount_usdc"] == 0.05
        assert payments[0]["status"] == "completed"

    def test_get_payments_all(self, storage):
        storage.save_payment(tx_id="tx1", from_agent="a", to_agent="b", amount_usdc=1.0, task_id="t1", status="completed")
        storage.save_payment(tx_id="tx2", from_agent="a", to_agent="c", amount_usdc=2.0, task_id="t2", status="completed")
        all_payments = storage.get_payments()
        assert len(all_payments) == 2

    def test_total_spent(self, storage):
        storage.save_payment(tx_id="tx1", from_agent="a", to_agent="b", amount_usdc=1.5, task_id="t1", status="completed")
        storage.save_payment(tx_id="tx2", from_agent="a", to_agent="c", amount_usdc=2.5, task_id="t2", status="completed")
        storage.save_payment(tx_id="tx3", from_agent="a", to_agent="d", amount_usdc=0.5, task_id="t3", status="pending")
        assert storage.total_spent() == 4.0  # only completed: 1.5 + 2.5

    def test_clear_payments(self, storage):
        storage.save_payment(tx_id="tx1", from_agent="a", to_agent="b", amount_usdc=1.0, task_id="t1", status="completed")
        storage.clear_payments()
        assert storage.get_payments() == []
        assert storage.total_spent() == 0.0

    def test_tx_count(self, storage):
        assert storage.get_tx_count() == 0
        storage.save_payment(tx_id="tx1", from_agent="a", to_agent="b", amount_usdc=1.0, task_id="t1")
        storage.save_payment(tx_id="tx2", from_agent="a", to_agent="c", amount_usdc=2.0, task_id="t2")
        assert storage.get_tx_count() == 2


# ──────────────────────────────────────────────
# Agent Registry CRUD
# ──────────────────────────────────────────────

class TestAgentStorage:
    def test_save_and_get_agent(self, storage):
        storage.save_agent(
            name="builder",
            description="Writes code",
            skills=["code", "testing"],
            price_per_call="$0.00",
            endpoint="internal://builder",
            protocol="internal",
            payment="none",
        )
        agent = storage.get_agent("builder")
        assert agent is not None
        assert agent["name"] == "builder"
        assert agent["description"] == "Writes code"
        assert agent["skills"] == ["code", "testing"]
        assert agent["is_external"] is False

    def test_get_nonexistent_agent(self, storage):
        assert storage.get_agent("nope") is None

    def test_remove_agent(self, storage):
        storage.save_agent(name="temp", description="Temp agent", skills=["test"])
        assert storage.remove_agent("temp") is True
        assert storage.get_agent("temp") is None
        assert storage.remove_agent("temp") is False

    def test_list_agents(self, storage):
        storage.save_agent(name="a1", description="Agent 1", skills=["s1"])
        storage.save_agent(name="a2", description="Agent 2", skills=["s2"])
        agents = storage.list_agents()
        assert len(agents) == 2
        names = {a["name"] for a in agents}
        assert names == {"a1", "a2"}

    def test_search_agents_by_skill(self, storage):
        storage.save_agent(name="designer", description="UI designer", skills=["design", "ui"])
        storage.save_agent(name="coder", description="Code writer", skills=["code", "python"])
        results = storage.search_agents("design")
        assert len(results) == 1
        assert results[0]["name"] == "designer"

    def test_search_agents_by_description(self, storage):
        storage.save_agent(name="analyzer", description="Data analysis expert", skills=["data"])
        results = storage.search_agents("analysis")
        assert len(results) == 1
        assert results[0]["name"] == "analyzer"

    def test_search_agents_with_max_price(self, storage):
        storage.save_agent(name="cheap", description="Cheap agent", skills=["general"], price_per_call="$0.01")
        storage.save_agent(name="expensive", description="Premium agent", skills=["general"], price_per_call="$1.00")
        results = storage.search_agents("general", max_price=0.10)
        assert len(results) == 1
        assert results[0]["name"] == "cheap"

    def test_external_agent_flag(self, storage):
        storage.save_agent(
            name="ext-001",
            description="External agent",
            skills=["design"],
            is_external=True,
            endpoint="http://localhost:9100",
        )
        agent = storage.get_agent("ext-001")
        assert agent["is_external"] is True
        assert agent["endpoint"] == "http://localhost:9100"

    def test_agent_metadata_json(self, storage):
        storage.save_agent(
            name="meta-agent",
            description="Agent with metadata",
            skills=["test"],
            metadata={"rating": 4.8, "tasks_completed": 142},
        )
        agent = storage.get_agent("meta-agent")
        assert agent["metadata"]["rating"] == 4.8
        assert agent["metadata"]["tasks_completed"] == 142

    def test_clear_agents(self, storage):
        storage.save_agent(name="a", description="A", skills=[])
        storage.clear_agents()
        assert storage.list_agents() == []


# ──────────────────────────────────────────────
# Budget CRUD
# ──────────────────────────────────────────────

class TestBudgetStorage:
    def test_save_and_get_budget(self, storage):
        storage.save_budget("t1", 10.0)
        budget = storage.get_budget("t1")
        assert budget is not None
        assert budget["task_id"] == "t1"
        assert budget["allocated"] == 10.0
        assert budget["spent"] == 0.0
        assert budget["remaining"] == 10.0

    def test_budget_not_found(self, storage):
        assert storage.get_budget("nonexistent") is None

    def test_update_budget_spent(self, storage):
        storage.save_budget("t2", 5.0)
        storage.update_budget_spent("t2", 1.5)
        budget = storage.get_budget("t2")
        assert budget["spent"] == 1.5
        assert budget["remaining"] == 3.5

        storage.update_budget_spent("t2", 0.5)
        budget = storage.get_budget("t2")
        assert budget["spent"] == 2.0
        assert budget["remaining"] == 3.0

    def test_clear_budgets(self, storage):
        storage.save_budget("t1", 5.0)
        storage.clear_budgets()
        assert storage.get_budget("t1") is None


# ──────────────────────────────────────────────
# WAL Mode & Database Init
# ──────────────────────────────────────────────

class TestDatabaseInit:
    def test_wal_mode_enabled(self, storage):
        """Verify WAL journal mode is active."""
        import sqlite3
        conn = sqlite3.connect(storage._db_path)
        result = conn.execute("PRAGMA journal_mode").fetchone()
        conn.close()
        assert result[0] == "wal"

    def test_tables_exist(self, storage):
        """Verify all required tables are created."""
        import sqlite3
        conn = sqlite3.connect(storage._db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()
        assert "tasks" in tables
        assert "payments" in tables
        assert "agents" in tables
        assert "budgets" in tables

    def test_clear_all(self, storage):
        storage.save_task(task_id="t1", description="T", workflow="sequential", budget_usd=1.0)
        storage.save_payment(tx_id="tx1", from_agent="a", to_agent="b", amount_usdc=1.0, task_id="t1")
        storage.save_agent(name="a1", description="A", skills=[])
        storage.save_budget("t1", 5.0)
        storage.clear_all()
        assert storage.list_tasks() == []
        assert storage.get_payments() == []
        assert storage.list_agents() == []
        assert storage.get_budget("t1") is None

    def test_auto_creates_directory(self):
        """Verify the storage creates the data directory if missing."""
        tmpdir = tempfile.mkdtemp()
        nested = os.path.join(tmpdir, "a", "b", "c", "test.db")
        storage = SQLiteStorage(nested)
        storage.save_task(task_id="t1", description="T", workflow="seq", budget_usd=1.0)
        assert storage.get_task("t1") is not None


# ──────────────────────────────────────────────
# Async Operations
# ──────────────────────────────────────────────

class TestAsyncStorage:
    @pytest.mark.asyncio
    async def test_async_save_and_get_task(self, storage):
        await storage.async_save_task(
            task_id="async1",
            description="Async test",
            workflow="sequential",
            budget_usd=3.0,
        )
        task = await storage.async_get_task("async1")
        assert task is not None
        assert task["task_id"] == "async1"
        assert task["description"] == "Async test"
        assert task["status"] == "pending"

    @pytest.mark.asyncio
    async def test_async_update_task_status(self, storage):
        await storage.async_save_task(
            task_id="async2",
            description="Status update test",
            workflow="concurrent",
            budget_usd=1.0,
        )
        await storage.async_update_task_status("async2", "completed", {"result": "success"})
        task = await storage.async_get_task("async2")
        assert task["status"] == "completed"
        assert task["result"] == {"result": "success"}

    @pytest.mark.asyncio
    async def test_async_get_nonexistent(self, storage):
        task = await storage.async_get_task("nope")
        assert task is None
