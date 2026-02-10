"""Metrics collector for HireWire.

Aggregates task completion rates, costs, latency, and budget utilisation.
All data is persisted via the SQLite metrics table in storage.py.
"""

from __future__ import annotations

import statistics
import time
from typing import Any

from src.storage import get_storage, SQLiteStorage


class MetricsCollector:
    """Collects and queries agent / system metrics."""

    def __init__(self, storage: SQLiteStorage | None = None) -> None:
        self._storage = storage or get_storage()

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def update_metrics(self, task_result: dict[str, Any]) -> None:
        """Record a metrics event from a completed task result.

        Expected keys in *task_result*:
            task_id, agent_id, task_type, status, cost_usdc, latency_ms
        Any extra data is stored in the metadata JSON blob.
        """
        core_keys = {"task_id", "agent_id", "task_type", "status", "cost_usdc", "latency_ms"}
        extra = {k: v for k, v in task_result.items() if k not in core_keys and k != "event_type"}
        self._storage.save_metric(
            event_type=task_result.get("event_type", "task_completed"),
            agent_id=task_result.get("agent_id", ""),
            task_id=task_result.get("task_id", ""),
            task_type=task_result.get("task_type", ""),
            status=task_result.get("status", ""),
            cost_usdc=float(task_result.get("cost_usdc", 0.0)),
            latency_ms=float(task_result.get("latency_ms", 0.0)),
            metadata=extra if extra else None,
        )

    def record_payment(self, payment_info: dict[str, Any]) -> None:
        """Record a payment event in the metrics table."""
        self._storage.save_metric(
            event_type="payment",
            agent_id=payment_info.get("to_agent", ""),
            task_id=payment_info.get("task_id", ""),
            cost_usdc=float(payment_info.get("amount_usdc", 0.0)),
            status=payment_info.get("status", "completed"),
            metadata={k: v for k, v in payment_info.items()
                      if k not in ("to_agent", "task_id", "amount_usdc", "status")},
        )

    # ------------------------------------------------------------------
    # Per-agent queries
    # ------------------------------------------------------------------

    def get_agent_metrics(self, agent_id: str) -> dict[str, Any]:
        """Return a performance summary for a single agent."""
        rows = self._storage.get_metrics(event_type="task_completed", agent_id=agent_id)
        if not rows:
            return {
                "agent_id": agent_id,
                "total_tasks": 0,
                "success_rate": 0.0,
                "fail_rate": 0.0,
                "timeout_rate": 0.0,
                "avg_cost": 0.0,
                "total_cost": 0.0,
                "latency_p50": 0.0,
                "latency_p95": 0.0,
            }

        total = len(rows)
        successes = sum(1 for r in rows if r["status"] == "success")
        failures = sum(1 for r in rows if r["status"] == "failure")
        timeouts = sum(1 for r in rows if r["status"] == "timeout")

        costs = [r["cost_usdc"] for r in rows]
        latencies = sorted(r["latency_ms"] for r in rows)

        return {
            "agent_id": agent_id,
            "total_tasks": total,
            "success_rate": round(successes / total, 4) if total else 0.0,
            "fail_rate": round(failures / total, 4) if total else 0.0,
            "timeout_rate": round(timeouts / total, 4) if total else 0.0,
            "avg_cost": round(statistics.mean(costs), 4) if costs else 0.0,
            "total_cost": round(sum(costs), 4),
            "latency_p50": round(_percentile(latencies, 50), 2),
            "latency_p95": round(_percentile(latencies, 95), 2),
        }

    # ------------------------------------------------------------------
    # System-wide queries
    # ------------------------------------------------------------------

    def get_system_metrics(self) -> dict[str, Any]:
        """Return overall platform health metrics."""
        all_tasks = self._storage.get_metrics(event_type="task_completed")
        all_payments = self._storage.get_metrics(event_type="payment")

        total = len(all_tasks)
        successes = sum(1 for r in all_tasks if r["status"] == "success")
        failures = sum(1 for r in all_tasks if r["status"] == "failure")
        timeouts = sum(1 for r in all_tasks if r["status"] == "timeout")

        costs = [r["cost_usdc"] for r in all_tasks]
        latencies = sorted(r["latency_ms"] for r in all_tasks)

        # Unique agents
        agent_ids = {r["agent_id"] for r in all_tasks if r["agent_id"]}

        total_payment_volume = sum(r["cost_usdc"] for r in all_payments)

        return {
            "total_tasks": total,
            "success_rate": round(successes / total, 4) if total else 0.0,
            "failure_rate": round(failures / total, 4) if total else 0.0,
            "timeout_rate": round(timeouts / total, 4) if total else 0.0,
            "total_cost": round(sum(costs), 4),
            "avg_cost_per_task": round(statistics.mean(costs), 4) if costs else 0.0,
            "latency_p50": round(_percentile(latencies, 50), 2),
            "latency_p95": round(_percentile(latencies, 95), 2),
            "active_agents": len(agent_ids),
            "total_payment_volume": round(total_payment_volume, 4),
        }

    def get_all_agent_summaries(self) -> list[dict[str, Any]]:
        """Return metrics for every agent that has recorded task events."""
        all_rows = self._storage.get_metrics(event_type="task_completed")
        agent_ids = {r["agent_id"] for r in all_rows if r["agent_id"]}
        return [self.get_agent_metrics(aid) for aid in sorted(agent_ids)]


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _percentile(sorted_data: list[float], pct: float) -> float:
    """Compute percentile from pre-sorted list."""
    if not sorted_data:
        return 0.0
    k = (len(sorted_data) - 1) * (pct / 100.0)
    f = int(k)
    c = f + 1
    if c >= len(sorted_data):
        return sorted_data[-1]
    d = k - f
    return sorted_data[f] + d * (sorted_data[c] - sorted_data[f])


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------

_collector: MetricsCollector | None = None


def get_metrics_collector(storage: SQLiteStorage | None = None) -> MetricsCollector:
    """Get or create the global MetricsCollector instance."""
    global _collector
    if _collector is None:
        _collector = MetricsCollector(storage)
    return _collector


def reset_metrics_collector(storage: SQLiteStorage | None = None) -> MetricsCollector:
    """Reset the global MetricsCollector (for testing)."""
    global _collector
    _collector = MetricsCollector(storage)
    return _collector
