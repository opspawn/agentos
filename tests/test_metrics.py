"""Tests for the metrics and cost analytics system.

Covers MetricsCollector, CostAnalyzer, ROICalculator, API endpoints,
and dashboard rendering. 25+ tests.
"""

from __future__ import annotations

import time

import pytest
import httpx

from src.storage import get_storage
from src.metrics.collector import MetricsCollector, reset_metrics_collector
from src.metrics.analytics import CostAnalyzer, ROICalculator
from src.api.main import app
from src.mcp_servers.payment_hub import ledger


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_metrics():
    """Clear metrics data and reset collector between tests."""
    storage = get_storage()
    storage.clear_metrics()
    reset_metrics_collector(storage)
    yield
    storage.clear_metrics()


@pytest.fixture()
def storage():
    """Fresh storage instance from conftest (already reset per test)."""
    return get_storage()


@pytest.fixture()
def collector(storage):
    """MetricsCollector backed by the test storage."""
    return reset_metrics_collector(storage)


@pytest.fixture()
def cost_analyzer(storage):
    return CostAnalyzer(storage)


@pytest.fixture()
def roi_calculator(storage):
    return ROICalculator(storage)


@pytest.fixture()
def client():
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture(autouse=True)
def _clean_ledger():
    ledger.clear()
    yield
    ledger.clear()


def _seed_metrics(storage, n=5, agent_id="builder", task_type="build", status="success", cost=0.25):
    """Helper: insert n metric rows."""
    for i in range(n):
        storage.save_metric(
            event_type="task_completed",
            agent_id=agent_id,
            task_id=f"task_{i}",
            task_type=task_type,
            status=status,
            cost_usdc=cost,
            latency_ms=100.0 + i * 10,
            timestamp=time.time() - (n - i),
        )


# ---------------------------------------------------------------------------
# MetricsCollector — storing and retrieving
# ---------------------------------------------------------------------------

class TestMetricsCollectorStore:
    def test_update_metrics_stores_event(self, collector, storage):
        collector.update_metrics({
            "task_id": "t1",
            "agent_id": "builder",
            "task_type": "build",
            "status": "success",
            "cost_usdc": 0.10,
            "latency_ms": 200.0,
        })
        rows = storage.get_metrics(event_type="task_completed")
        assert len(rows) == 1
        assert rows[0]["agent_id"] == "builder"
        assert rows[0]["cost_usdc"] == 0.10

    def test_record_payment_stores_event(self, collector, storage):
        collector.record_payment({
            "to_agent": "builder",
            "task_id": "t1",
            "amount_usdc": 0.50,
            "status": "completed",
        })
        rows = storage.get_metrics(event_type="payment")
        assert len(rows) == 1
        assert rows[0]["cost_usdc"] == 0.50

    def test_update_metrics_extra_metadata(self, collector, storage):
        collector.update_metrics({
            "task_id": "t1",
            "agent_id": "research",
            "task_type": "research",
            "status": "success",
            "cost_usdc": 0.0,
            "latency_ms": 50.0,
            "custom_field": "hello",
        })
        rows = storage.get_metrics(event_type="task_completed")
        assert rows[0]["metadata"]["custom_field"] == "hello"

    def test_multiple_events(self, collector, storage):
        for i in range(3):
            collector.update_metrics({
                "task_id": f"t{i}",
                "agent_id": "builder",
                "status": "success",
                "cost_usdc": 0.1 * (i + 1),
                "latency_ms": 100.0,
            })
        rows = storage.get_metrics(event_type="task_completed")
        assert len(rows) == 3


# ---------------------------------------------------------------------------
# MetricsCollector — agent metrics
# ---------------------------------------------------------------------------

class TestMetricsCollectorAgent:
    def test_empty_agent_metrics(self, collector):
        m = collector.get_agent_metrics("nonexistent")
        assert m["total_tasks"] == 0
        assert m["success_rate"] == 0.0

    def test_agent_metrics_success_rate(self, storage, collector):
        _seed_metrics(storage, n=4, status="success")
        _seed_metrics(storage, n=1, status="failure")
        m = collector.get_agent_metrics("builder")
        assert m["total_tasks"] == 5
        assert m["success_rate"] == 0.8

    def test_agent_metrics_latency_percentiles(self, storage, collector):
        _seed_metrics(storage, n=10, status="success")
        m = collector.get_agent_metrics("builder")
        assert m["latency_p50"] > 0
        assert m["latency_p95"] >= m["latency_p50"]

    def test_agent_metrics_cost(self, storage, collector):
        _seed_metrics(storage, n=4, cost=0.25)
        m = collector.get_agent_metrics("builder")
        assert m["avg_cost"] == 0.25
        assert m["total_cost"] == 1.0


# ---------------------------------------------------------------------------
# MetricsCollector — system metrics
# ---------------------------------------------------------------------------

class TestMetricsCollectorSystem:
    def test_empty_system_metrics(self, collector):
        m = collector.get_system_metrics()
        assert m["total_tasks"] == 0
        assert m["active_agents"] == 0

    def test_system_metrics_aggregation(self, storage, collector):
        _seed_metrics(storage, n=3, agent_id="builder")
        _seed_metrics(storage, n=2, agent_id="research")
        m = collector.get_system_metrics()
        assert m["total_tasks"] == 5
        assert m["active_agents"] == 2

    def test_system_metrics_payment_volume(self, storage, collector):
        storage.save_metric(
            event_type="payment", agent_id="builder", task_id="t1",
            cost_usdc=1.5, timestamp=time.time(),
        )
        m = collector.get_system_metrics()
        assert m["total_payment_volume"] == 1.5

    def test_all_agent_summaries(self, storage, collector):
        _seed_metrics(storage, n=2, agent_id="builder")
        _seed_metrics(storage, n=3, agent_id="research")
        summaries = collector.get_all_agent_summaries()
        assert len(summaries) == 2
        names = {s["agent_id"] for s in summaries}
        assert names == {"builder", "research"}


# ---------------------------------------------------------------------------
# CostAnalyzer
# ---------------------------------------------------------------------------

class TestCostAnalyzer:
    def test_cost_by_agent_empty(self, cost_analyzer):
        assert cost_analyzer.cost_by_agent() == []

    def test_cost_by_agent(self, storage, cost_analyzer):
        _seed_metrics(storage, n=3, agent_id="builder", cost=0.30)
        _seed_metrics(storage, n=2, agent_id="research", cost=0.10)
        result = cost_analyzer.cost_by_agent()
        assert len(result) == 2
        assert result[0]["agent_id"] == "builder"  # highest cost first
        assert result[0]["total_cost"] == pytest.approx(0.90, abs=0.01)

    def test_cost_by_task_type(self, storage, cost_analyzer):
        _seed_metrics(storage, n=2, task_type="build", cost=0.50)
        _seed_metrics(storage, n=3, task_type="research", cost=0.10)
        result = cost_analyzer.cost_by_task_type()
        assert len(result) == 2
        types = {r["task_type"] for r in result}
        assert types == {"build", "research"}

    def test_efficiency_score_empty(self, cost_analyzer):
        r = cost_analyzer.efficiency_score()
        assert r["tasks_per_dollar"] == 0.0

    def test_efficiency_score(self, storage, cost_analyzer):
        _seed_metrics(storage, n=10, cost=0.50)
        r = cost_analyzer.efficiency_score()
        assert r["tasks_per_dollar"] == pytest.approx(2.0, abs=0.1)
        assert r["total_tasks"] == 10

    def test_trend_analysis_stable(self, storage, cost_analyzer):
        r = cost_analyzer.trend_analysis()
        assert r["direction"] == "stable"

    def test_trend_analysis_detects_change(self, storage, cost_analyzer):
        now = time.time()
        # Earlier half: low cost
        for i in range(3):
            storage.save_metric(
                event_type="task_completed", agent_id="a",
                cost_usdc=0.10, timestamp=now - 2500 + i,
            )
        # Recent half: high cost
        for i in range(3):
            storage.save_metric(
                event_type="task_completed", agent_id="a",
                cost_usdc=1.00, timestamp=now - 500 + i,
            )
        r = cost_analyzer.trend_analysis(window_seconds=3600)
        assert r["direction"] == "up"


# ---------------------------------------------------------------------------
# ROICalculator
# ---------------------------------------------------------------------------

class TestROICalculator:
    def test_calculate_roi_empty(self, roi_calculator):
        r = roi_calculator.calculate_roi("nope")
        assert r["roi"] == 0.0

    def test_calculate_roi(self, storage, roi_calculator):
        storage.save_metric(
            event_type="task_completed", agent_id="builder", task_id="t1",
            cost_usdc=0.50, timestamp=time.time(),
        )
        r = roi_calculator.calculate_roi("t1")
        assert r["agent_cost"] == 0.50
        assert r["manual_estimate"] == 5.0  # 10x multiplier
        assert r["savings"] == 4.5
        assert r["roi"] == 90.0

    def test_best_value_agents_empty(self, roi_calculator):
        assert roi_calculator.best_value_agents() == []

    def test_best_value_agents_ranking(self, storage, roi_calculator):
        # builder: 4 successes at $0.25 each = efficiency 4/1.0 = 4.0
        _seed_metrics(storage, n=4, agent_id="builder", cost=0.25, status="success")
        # research: 2 successes at $0.50 each = efficiency 2/1.0 = 2.0
        _seed_metrics(storage, n=2, agent_id="research", cost=0.50, status="success")
        result = roi_calculator.best_value_agents()
        assert len(result) == 2
        assert result[0]["agent_id"] == "builder"  # more efficient
        assert result[0]["efficiency"] > result[1]["efficiency"]

    def test_savings_estimate_empty(self, roi_calculator):
        r = roi_calculator.savings_estimate()
        assert r["total_savings"] == 0.0

    def test_savings_estimate(self, storage, roi_calculator):
        _seed_metrics(storage, n=5, cost=1.0)
        r = roi_calculator.savings_estimate()
        assert r["total_agent_cost"] == 5.0
        assert r["total_manual_estimate"] == 50.0
        assert r["total_savings"] == 45.0
        assert r["savings_pct"] == 90.0


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

class TestMetricsAPI:
    @pytest.mark.asyncio
    async def test_metrics_endpoint_200(self, client):
        resp = await client.get("/metrics")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_metrics_returns_system_data(self, client):
        resp = await client.get("/metrics")
        data = resp.json()
        assert "total_tasks" in data
        assert "success_rate" in data
        assert "active_agents" in data

    @pytest.mark.asyncio
    async def test_metrics_agents_endpoint_200(self, client):
        resp = await client.get("/metrics/agents")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_metrics_costs_endpoint_200(self, client):
        resp = await client.get("/metrics/costs")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_metrics_costs_structure(self, client):
        resp = await client.get("/metrics/costs")
        data = resp.json()
        assert "cost_by_agent" in data
        assert "cost_by_task_type" in data
        assert "efficiency" in data
        assert "trend" in data
        assert "savings" in data
        assert "best_value_agents" in data


# ---------------------------------------------------------------------------
# Dashboard rendering (HTML contains Metrics tab)
# ---------------------------------------------------------------------------

class TestDashboardMetricsTab:
    @pytest.mark.asyncio
    async def test_dashboard_has_metrics_tab(self, client):
        resp = await client.get("/")
        assert resp.status_code == 200
        html = resp.text
        assert "switchTab" in html
        assert "metrics" in html.lower()

    @pytest.mark.asyncio
    async def test_dashboard_has_leaderboard(self, client):
        resp = await client.get("/")
        html = resp.text
        assert "agent-leaderboard" in html

    @pytest.mark.asyncio
    async def test_dashboard_has_roi_panel(self, client):
        resp = await client.get("/")
        html = resp.text
        assert "roi-panel" in html
