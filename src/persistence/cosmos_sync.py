"""Cosmos DB sync layer for HireWire.

Provides optional cloud persistence by syncing key operations (tasks, agents,
payments) to Azure Cosmos DB alongside the primary SQLite store. When Cosmos DB
is not configured, all methods are no-ops.

Usage:
    from src.persistence.cosmos_sync import get_cosmos_sync
    sync = get_cosmos_sync()
    sync.sync_task({...})   # silently no-ops if Cosmos not configured
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

log = logging.getLogger(__name__)


class CosmosSync:
    """Optional Cosmos DB sync — mirrors writes for cloud durability."""

    def __init__(self) -> None:
        self._store: Any = None
        self._enabled: bool = False
        self._init_attempted = False

    def _ensure_init(self) -> None:
        """Lazy-init the Cosmos store on first use."""
        if self._init_attempted:
            return
        self._init_attempted = True

        from src.persistence.cosmos import cosmos_available, CosmosDBStore

        if not cosmos_available():
            log.info("Cosmos DB not configured — sync disabled")
            return

        try:
            self._store = CosmosDBStore()
            # Verify connectivity
            check = self._store.check_connection()
            if check.get("connected"):
                self._enabled = True
                log.info("Cosmos DB sync enabled (%s)", self._store.endpoint)
            else:
                log.warning("Cosmos DB connection failed: %s", check.get("error"))
        except Exception as exc:
            log.warning("Cosmos DB init failed: %s", exc)

    @property
    def enabled(self) -> bool:
        self._ensure_init()
        return self._enabled

    def sync_task(self, task: dict[str, Any]) -> None:
        """Mirror a task record to Cosmos DB jobs container."""
        self._ensure_init()
        if not self._enabled:
            return
        try:
            job = {
                "id": task.get("task_id", task.get("id", "")),
                "description": task.get("description", ""),
                "workflow": task.get("workflow", ""),
                "budget_usd": task.get("budget_usd", 0.0),
                "status": task.get("status", "pending"),
                "created_at": task.get("created_at", time.time()),
                "result": task.get("result"),
            }
            self._store.save_job(job)
        except Exception as exc:
            log.warning("Cosmos sync_task failed: %s", exc)

    def sync_agent(self, agent: dict[str, Any]) -> None:
        """Mirror an agent record to Cosmos DB agents container."""
        self._ensure_init()
        if not self._enabled:
            return
        try:
            doc = {
                "id": agent.get("name", agent.get("id", "")),
                "name": agent.get("name", ""),
                "description": agent.get("description", ""),
                "skills": agent.get("skills", []),
                "price_per_call": agent.get("price_per_call", "$0.00"),
                "is_external": agent.get("is_external", False),
                "synced_at": time.time(),
            }
            self._store.save_agent(doc)
        except Exception as exc:
            log.warning("Cosmos sync_agent failed: %s", exc)

    def sync_payment(self, payment: dict[str, Any]) -> None:
        """Mirror a payment record to Cosmos DB payments container."""
        self._ensure_init()
        if not self._enabled:
            return
        try:
            doc = {
                "id": payment.get("tx_id", payment.get("id", "")),
                "from_agent": payment.get("from_agent", ""),
                "to_agent": payment.get("to_agent", ""),
                "amount_usdc": payment.get("amount_usdc", 0.0),
                "task_id": payment.get("task_id", ""),
                "status": payment.get("status", "pending"),
                "synced_at": time.time(),
            }
            self._store.save_payment(doc)
        except Exception as exc:
            log.warning("Cosmos sync_payment failed: %s", exc)

    def health(self) -> dict[str, Any]:
        """Return Cosmos DB health status."""
        self._ensure_init()
        if not self._enabled:
            return {"enabled": False, "reason": "not configured"}
        try:
            return {"enabled": True, **self._store.check_connection()}
        except Exception as exc:
            return {"enabled": True, "connected": False, "error": str(exc)}


_sync: CosmosSync | None = None


def get_cosmos_sync() -> CosmosSync:
    """Return the global CosmosSync singleton."""
    global _sync
    if _sync is None:
        _sync = CosmosSync()
    return _sync
