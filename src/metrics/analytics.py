"""Cost analytics and ROI calculations for AgentOS.

CostAnalyzer — cost breakdowns, efficiency scores, trend analysis.
ROICalculator — per-task ROI, agent ranking, savings estimates.
"""

from __future__ import annotations

import statistics
import time
from typing import Any

from src.storage import get_storage, SQLiteStorage


class CostAnalyzer:
    """Analyses cost data from the metrics table."""

    def __init__(self, storage: SQLiteStorage | None = None) -> None:
        self._storage = storage or get_storage()

    def cost_by_agent(self) -> list[dict[str, Any]]:
        """Cost breakdown per agent, sorted by total cost descending."""
        rows = self._storage.get_metrics(event_type="task_completed")
        buckets: dict[str, list[float]] = {}
        for r in rows:
            aid = r["agent_id"] or "unknown"
            buckets.setdefault(aid, []).append(r["cost_usdc"])

        result = []
        for agent_id, costs in buckets.items():
            result.append({
                "agent_id": agent_id,
                "total_cost": round(sum(costs), 4),
                "avg_cost": round(statistics.mean(costs), 4),
                "task_count": len(costs),
            })
        result.sort(key=lambda x: x["total_cost"], reverse=True)
        return result

    def cost_by_task_type(self) -> list[dict[str, Any]]:
        """Cost breakdown per task type."""
        rows = self._storage.get_metrics(event_type="task_completed")
        buckets: dict[str, list[float]] = {}
        for r in rows:
            tt = r["task_type"] or "unknown"
            buckets.setdefault(tt, []).append(r["cost_usdc"])

        result = []
        for task_type, costs in buckets.items():
            result.append({
                "task_type": task_type,
                "total_cost": round(sum(costs), 4),
                "avg_cost": round(statistics.mean(costs), 4),
                "task_count": len(costs),
            })
        result.sort(key=lambda x: x["total_cost"], reverse=True)
        return result

    def efficiency_score(self) -> dict[str, Any]:
        """Tasks completed per dollar spent (higher = more efficient)."""
        rows = self._storage.get_metrics(event_type="task_completed")
        if not rows:
            return {"tasks_per_dollar": 0.0, "total_tasks": 0, "total_cost": 0.0}
        total_cost = sum(r["cost_usdc"] for r in rows)
        total_tasks = len(rows)
        tpd = round(total_tasks / total_cost, 4) if total_cost > 0 else 0.0
        return {
            "tasks_per_dollar": tpd,
            "total_tasks": total_tasks,
            "total_cost": round(total_cost, 4),
        }

    def trend_analysis(self, window_seconds: float = 3600.0) -> dict[str, Any]:
        """Cost trend over a rolling window (default 1 hour).

        Compares the recent half of the window to the earlier half.
        Returns direction: 'up', 'down', or 'stable'.
        """
        now = time.time()
        cutoff = now - window_seconds
        midpoint = now - window_seconds / 2.0

        rows = self._storage.get_metrics(event_type="task_completed", since=cutoff)
        if not rows:
            return {"direction": "stable", "recent_cost": 0.0, "earlier_cost": 0.0, "change_pct": 0.0}

        earlier = [r["cost_usdc"] for r in rows if r["timestamp"] < midpoint]
        recent = [r["cost_usdc"] for r in rows if r["timestamp"] >= midpoint]

        earlier_total = sum(earlier)
        recent_total = sum(recent)

        if earlier_total == 0:
            direction = "up" if recent_total > 0 else "stable"
            change_pct = 100.0 if recent_total > 0 else 0.0
        else:
            change_pct = round(((recent_total - earlier_total) / earlier_total) * 100, 2)
            if change_pct > 5:
                direction = "up"
            elif change_pct < -5:
                direction = "down"
            else:
                direction = "stable"

        return {
            "direction": direction,
            "recent_cost": round(recent_total, 4),
            "earlier_cost": round(earlier_total, 4),
            "change_pct": change_pct,
        }


class ROICalculator:
    """Estimates ROI for tasks and ranks agents by value."""

    # Assumed manual cost multiplier — a human doing the same work costs ~10x
    MANUAL_COST_MULTIPLIER = 10.0

    def __init__(self, storage: SQLiteStorage | None = None) -> None:
        self._storage = storage or get_storage()

    def calculate_roi(self, task_id: str) -> dict[str, Any]:
        """Compare agent cost to estimated manual cost for one task."""
        rows = self._storage.get_metrics(event_type="task_completed")
        task_rows = [r for r in rows if r["task_id"] == task_id]
        if not task_rows:
            return {"task_id": task_id, "roi": 0.0, "agent_cost": 0.0, "manual_estimate": 0.0}

        agent_cost = sum(r["cost_usdc"] for r in task_rows)
        manual_estimate = agent_cost * self.MANUAL_COST_MULTIPLIER
        roi = round(((manual_estimate - agent_cost) / manual_estimate) * 100, 2) if manual_estimate else 0.0

        return {
            "task_id": task_id,
            "agent_cost": round(agent_cost, 4),
            "manual_estimate": round(manual_estimate, 4),
            "savings": round(manual_estimate - agent_cost, 4),
            "roi": roi,
        }

    def best_value_agents(self) -> list[dict[str, Any]]:
        """Rank agents by efficiency: success-weighted tasks per dollar."""
        rows = self._storage.get_metrics(event_type="task_completed")
        buckets: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            aid = r["agent_id"] or "unknown"
            buckets.setdefault(aid, []).append(r)

        result = []
        for agent_id, agent_rows in buckets.items():
            total_cost = sum(r["cost_usdc"] for r in agent_rows)
            total_tasks = len(agent_rows)
            successes = sum(1 for r in agent_rows if r["status"] == "success")
            success_rate = round(successes / total_tasks, 4) if total_tasks else 0.0
            efficiency = round(successes / total_cost, 4) if total_cost > 0 else 0.0

            result.append({
                "agent_id": agent_id,
                "total_tasks": total_tasks,
                "successes": successes,
                "success_rate": success_rate,
                "total_cost": round(total_cost, 4),
                "efficiency": efficiency,
            })
        result.sort(key=lambda x: x["efficiency"], reverse=True)
        return result

    def savings_estimate(self) -> dict[str, Any]:
        """Estimate total savings vs manual labour across all tasks."""
        rows = self._storage.get_metrics(event_type="task_completed")
        if not rows:
            return {"total_agent_cost": 0.0, "total_manual_estimate": 0.0, "total_savings": 0.0, "savings_pct": 0.0}

        total_agent_cost = sum(r["cost_usdc"] for r in rows)
        total_manual = total_agent_cost * self.MANUAL_COST_MULTIPLIER
        savings = total_manual - total_agent_cost
        pct = round((savings / total_manual) * 100, 2) if total_manual > 0 else 0.0

        return {
            "total_agent_cost": round(total_agent_cost, 4),
            "total_manual_estimate": round(total_manual, 4),
            "total_savings": round(savings, 4),
            "savings_pct": pct,
        }
