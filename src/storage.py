"""SQLite persistence layer for AgentOS.

Replaces in-memory dicts with durable storage using SQLite (WAL mode)
for tasks, payments, and agent registry. Uses aiosqlite for async access
with a synchronous fallback via sqlite3 for non-async call sites.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import aiosqlite

# Default database path (overridable via AGENTOS_DB_PATH env var)
_DEFAULT_DB_PATH = Path(
    os.environ.get("AGENTOS_DB_PATH", "")
    or str(Path(__file__).resolve().parent.parent / "data" / "agentos.db")
)

# SQL schema
_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    workflow TEXT NOT NULL,
    budget_usd REAL NOT NULL DEFAULT 1.0,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at REAL NOT NULL,
    result TEXT  -- JSON blob
);

CREATE TABLE IF NOT EXISTS payments (
    tx_id TEXT PRIMARY KEY,
    from_agent TEXT NOT NULL,
    to_agent TEXT NOT NULL,
    amount_usdc REAL NOT NULL,
    task_id TEXT NOT NULL,
    timestamp REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    tx_hash TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS agents (
    agent_id TEXT PRIMARY KEY,  -- same as name
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    skills TEXT NOT NULL DEFAULT '[]',  -- JSON array
    price_per_call TEXT NOT NULL DEFAULT '$0.00',
    endpoint TEXT NOT NULL DEFAULT '',
    protocol TEXT NOT NULL DEFAULT 'a2a',
    payment TEXT NOT NULL DEFAULT 'x402',
    is_external INTEGER NOT NULL DEFAULT 0,
    metadata TEXT NOT NULL DEFAULT '{}',  -- JSON blob
    registered_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS budgets (
    task_id TEXT PRIMARY KEY,
    allocated REAL NOT NULL,
    spent REAL NOT NULL DEFAULT 0.0
);
"""


class SQLiteStorage:
    """Unified SQLite storage for tasks, payments, and agent registry.

    Provides both synchronous and async methods. The synchronous methods
    use sqlite3 directly; async methods use aiosqlite.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = str(db_path or _DEFAULT_DB_PATH)
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Get a new synchronous connection with WAL mode."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        """Create tables if they don't exist."""
        conn = self._get_conn()
        try:
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------

    def save_task(
        self,
        task_id: str,
        description: str,
        workflow: str,
        budget_usd: float,
        status: str = "pending",
        created_at: float | None = None,
        result: dict[str, Any] | None = None,
    ) -> None:
        """Insert or replace a task record."""
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO tasks
                   (task_id, description, workflow, budget_usd, status, created_at, result)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    task_id,
                    description,
                    workflow,
                    budget_usd,
                    status,
                    created_at or time.time(),
                    json.dumps(result) if result is not None else None,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        """Retrieve a task by ID. Returns dict or None."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            if row is None:
                return None
            return self._row_to_task(row)
        finally:
            conn.close()

    def list_tasks(self, status: str | None = None) -> list[dict[str, Any]]:
        """List all tasks, optionally filtered by status."""
        conn = self._get_conn()
        try:
            if status is not None:
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE status = ?", (status,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM tasks").fetchall()
            return [self._row_to_task(r) for r in rows]
        finally:
            conn.close()

    def update_task_status(
        self, task_id: str, status: str, result: dict[str, Any] | None = None
    ) -> None:
        """Update a task's status and optionally its result."""
        conn = self._get_conn()
        try:
            if result is not None:
                conn.execute(
                    "UPDATE tasks SET status = ?, result = ? WHERE task_id = ?",
                    (status, json.dumps(result), task_id),
                )
            else:
                conn.execute(
                    "UPDATE tasks SET status = ? WHERE task_id = ?",
                    (status, task_id),
                )
            conn.commit()
        finally:
            conn.close()

    def count_tasks(self, status: str | None = None) -> int:
        """Count tasks, optionally filtered by status."""
        conn = self._get_conn()
        try:
            if status is not None:
                row = conn.execute(
                    "SELECT COUNT(*) FROM tasks WHERE status = ?", (status,)
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()
            return row[0]
        finally:
            conn.close()

    def clear_tasks(self) -> None:
        """Delete all tasks (for testing)."""
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM tasks")
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> dict[str, Any]:
        result_raw = row["result"]
        return {
            "task_id": row["task_id"],
            "description": row["description"],
            "workflow": row["workflow"],
            "budget_usd": row["budget_usd"],
            "status": row["status"],
            "created_at": row["created_at"],
            "result": json.loads(result_raw) if result_raw else None,
        }

    # ------------------------------------------------------------------
    # Payments / Ledger
    # ------------------------------------------------------------------

    def save_payment(
        self,
        tx_id: str,
        from_agent: str,
        to_agent: str,
        amount_usdc: float,
        task_id: str,
        timestamp: float | None = None,
        status: str = "pending",
        tx_hash: str = "",
    ) -> None:
        """Insert a payment record."""
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO payments
                   (tx_id, from_agent, to_agent, amount_usdc, task_id,
                    timestamp, status, tx_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    tx_id,
                    from_agent,
                    to_agent,
                    amount_usdc,
                    task_id,
                    timestamp or time.time(),
                    status,
                    tx_hash,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_payments(self, task_id: str | None = None) -> list[dict[str, Any]]:
        """Get payment records, optionally filtered by task_id."""
        conn = self._get_conn()
        try:
            if task_id is not None:
                rows = conn.execute(
                    "SELECT * FROM payments WHERE task_id = ?", (task_id,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM payments").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def total_spent(self) -> float:
        """Total USDC spent (completed transactions)."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT COALESCE(SUM(amount_usdc), 0) FROM payments WHERE status = 'completed'"
            ).fetchone()
            return row[0]
        finally:
            conn.close()

    def get_tx_count(self) -> int:
        """Get total number of transactions (for tx_id generation)."""
        conn = self._get_conn()
        try:
            row = conn.execute("SELECT COUNT(*) FROM payments").fetchone()
            return row[0]
        finally:
            conn.close()

    def clear_payments(self) -> None:
        """Delete all payments (for testing)."""
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM payments")
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Budget helpers (stored as tasks metadata — we track via payments)
    # We use a simple approach: budgets are kept in a separate table-like
    # structure. For simplicity, we add a budgets table.
    # ------------------------------------------------------------------

    def save_budget(self, task_id: str, allocated: float, spent: float = 0.0) -> None:
        """Save or update a budget allocation."""
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO budgets (task_id, allocated, spent)
                   VALUES (?, ?, ?)""",
                (task_id, allocated, spent),
            )
            conn.commit()
        finally:
            conn.close()

    def get_budget(self, task_id: str) -> dict[str, Any] | None:
        """Get budget for a task."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM budgets WHERE task_id = ?", (task_id,)
            ).fetchone()
            if row is None:
                return None
            return {
                "task_id": row["task_id"],
                "allocated": row["allocated"],
                "spent": row["spent"],
                "remaining": row["allocated"] - row["spent"],
            }
        finally:
            conn.close()

    def update_budget_spent(self, task_id: str, additional_spent: float) -> None:
        """Add to the spent amount for a budget."""
        conn = self._get_conn()
        try:
            conn.execute(
                "UPDATE budgets SET spent = spent + ? WHERE task_id = ?",
                (additional_spent, task_id),
            )
            conn.commit()
        finally:
            conn.close()

    def clear_budgets(self) -> None:
        """Delete all budgets (for testing)."""
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM budgets")
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Agents
    # ------------------------------------------------------------------

    def save_agent(
        self,
        name: str,
        description: str,
        skills: list[str],
        price_per_call: str = "$0.00",
        endpoint: str = "",
        protocol: str = "a2a",
        payment: str = "x402",
        is_external: bool = False,
        metadata: dict[str, Any] | None = None,
        registered_at: float | None = None,
    ) -> None:
        """Register or update an agent."""
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO agents
                   (agent_id, name, description, skills, price_per_call,
                    endpoint, protocol, payment, is_external, metadata, registered_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    name,  # agent_id = name
                    name,
                    description,
                    json.dumps(skills),
                    price_per_call,
                    endpoint,
                    protocol,
                    payment,
                    1 if is_external else 0,
                    json.dumps(metadata or {}),
                    registered_at or time.time(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_agent(self, name: str) -> dict[str, Any] | None:
        """Get an agent by name."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM agents WHERE agent_id = ?", (name,)
            ).fetchone()
            if row is None:
                return None
            return self._row_to_agent(row)
        finally:
            conn.close()

    def remove_agent(self, name: str) -> bool:
        """Remove an agent. Returns True if found and deleted."""
        conn = self._get_conn()
        try:
            cursor = conn.execute("DELETE FROM agents WHERE agent_id = ?", (name,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def list_agents(self) -> list[dict[str, Any]]:
        """List all agents."""
        conn = self._get_conn()
        try:
            rows = conn.execute("SELECT * FROM agents").fetchall()
            return [self._row_to_agent(r) for r in rows]
        finally:
            conn.close()

    def search_agents(
        self, capability: str, max_price: float | None = None
    ) -> list[dict[str, Any]]:
        """Search agents by capability (matches name, description, or skills)."""
        conn = self._get_conn()
        try:
            cap_lower = f"%{capability.lower()}%"
            rows = conn.execute(
                """SELECT * FROM agents
                   WHERE LOWER(name) LIKE ?
                      OR LOWER(description) LIKE ?
                      OR LOWER(skills) LIKE ?""",
                (cap_lower, cap_lower, cap_lower),
            ).fetchall()
            results = [self._row_to_agent(r) for r in rows]
            if max_price is not None:
                results = [
                    a for a in results
                    if float(a["price_per_call"].replace("$", "")) <= max_price
                ]
            return results
        finally:
            conn.close()

    def clear_agents(self) -> None:
        """Delete all agents (for testing)."""
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM agents")
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _row_to_agent(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "agent_id": row["agent_id"],
            "name": row["name"],
            "description": row["description"],
            "skills": json.loads(row["skills"]),
            "price_per_call": row["price_per_call"],
            "endpoint": row["endpoint"],
            "protocol": row["protocol"],
            "payment": row["payment"],
            "is_external": bool(row["is_external"]),
            "metadata": json.loads(row["metadata"]),
            "registered_at": row["registered_at"],
        }

    # ------------------------------------------------------------------
    # Async wrappers (via aiosqlite)
    # ------------------------------------------------------------------

    async def async_save_task(self, **kwargs: Any) -> None:
        """Async version of save_task."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA journal_mode=WAL")
            created_at = kwargs.get("created_at") or time.time()
            result = kwargs.get("result")
            await db.execute(
                """INSERT OR REPLACE INTO tasks
                   (task_id, description, workflow, budget_usd, status, created_at, result)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    kwargs["task_id"],
                    kwargs["description"],
                    kwargs["workflow"],
                    kwargs["budget_usd"],
                    kwargs.get("status", "pending"),
                    created_at,
                    json.dumps(result) if result is not None else None,
                ),
            )
            await db.commit()

    async def async_update_task_status(
        self, task_id: str, status: str, result: dict[str, Any] | None = None
    ) -> None:
        """Async version of update_task_status."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            if result is not None:
                await db.execute(
                    "UPDATE tasks SET status = ?, result = ? WHERE task_id = ?",
                    (status, json.dumps(result), task_id),
                )
            else:
                await db.execute(
                    "UPDATE tasks SET status = ? WHERE task_id = ?",
                    (status, task_id),
                )
            await db.commit()

    async def async_get_task(self, task_id: str) -> dict[str, Any] | None:
        """Async version of get_task."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA journal_mode=WAL")
            cursor = await db.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            result_raw = row["result"]
            return {
                "task_id": row["task_id"],
                "description": row["description"],
                "workflow": row["workflow"],
                "budget_usd": row["budget_usd"],
                "status": row["status"],
                "created_at": row["created_at"],
                "result": json.loads(result_raw) if result_raw else None,
            }

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def clear_all(self) -> None:
        """Clear all tables (for testing)."""
        self.clear_tasks()
        self.clear_payments()
        self.clear_budgets()
        self.clear_agents()

    def close(self) -> None:
        """No-op — connections are opened/closed per operation."""
        pass


# Module-level singleton
_storage: SQLiteStorage | None = None


def get_storage(db_path: str | Path | None = None) -> SQLiteStorage:
    """Get or create the global storage instance."""
    global _storage
    if _storage is None:
        _storage = SQLiteStorage(db_path)
    return _storage


def reset_storage(db_path: str | Path | None = None) -> SQLiteStorage:
    """Reset the global storage instance (for testing)."""
    global _storage
    _storage = SQLiteStorage(db_path)
    return _storage
