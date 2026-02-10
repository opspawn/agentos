"""Tests for Agent Marketplace v2 — Sprint 30.

Covers:
- Agent reputation tracking (completion rate, earnings, availability)
- Agent registration via API
- Sorting and filtering (by price, rating, availability)
- PaymentManager (request, verify, escrow, balance)
- PaymentLedger (audit trail, filtering)
- Hire status tracking via API
- Payment API endpoints (/payments/request, /verify, /balance, /ledger)
- End-to-end marketplace + payment flows
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.marketplace import (
    AgentListing,
    MarketplaceRegistry,
    SkillMatcher,
)
from src.marketplace.x402 import (
    PaymentConfig,
    PaymentProof,
    X402PaymentGate,
    EscrowEntry,
    AgentEscrow,
    LedgerEntry,
    PaymentLedger,
    PaymentManager,
)
from src.marketplace.hiring import (
    HireRequest,
    HireResult,
    BudgetTracker,
    HiringManager,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_listing(
    name: str = "TestAgent",
    skills: list[str] | None = None,
    price: float = 0.01,
    rating: float = 4.0,
    agent_id: str | None = None,
    availability: str = "available",
) -> AgentListing:
    listing = AgentListing(
        name=name,
        description=f"A test agent: {name}",
        skills=skills or ["code", "testing"],
        pricing_model="per-task",
        price_per_unit=price,
        rating=rating,
        endpoint=f"http://localhost:9000/{name.lower()}",
        availability=availability,
    )
    if agent_id:
        listing.agent_id = agent_id
    return listing


def _seeded_registry() -> MarketplaceRegistry:
    reg = MarketplaceRegistry()
    reg.register_agent(_make_listing("Coder", ["code", "python", "testing"], 0.02, 4.5))
    reg.register_agent(_make_listing("Designer", ["design", "ui", "ux"], 0.05, 4.8))
    reg.register_agent(_make_listing("Researcher", ["research", "analysis"], 0.01, 4.2))
    reg.register_agent(_make_listing("DevOps", ["deployment", "docker"], 0.03, 3.9))
    reg.register_agent(_make_listing("Writer", ["writing", "docs"], 0.00, 4.0))
    return reg


# ===================================================================
# 1. Agent Reputation — New fields and methods
# ===================================================================


class TestAgentReputation:
    def test_default_reputation_fields(self):
        listing = AgentListing()
        assert listing.completed_jobs == 0
        assert listing.failed_jobs == 0
        assert listing.total_earnings == 0.0
        assert listing.availability == "available"

    def test_completion_rate_no_jobs(self):
        listing = AgentListing()
        assert listing.completion_rate == 0.0

    def test_completion_rate_all_success(self):
        listing = AgentListing(total_jobs=10, completed_jobs=10, failed_jobs=0)
        assert listing.completion_rate == 1.0

    def test_completion_rate_mixed(self):
        listing = AgentListing(total_jobs=10, completed_jobs=7, failed_jobs=3)
        assert listing.completion_rate == pytest.approx(0.7)

    def test_completion_rate_all_failed(self):
        listing = AgentListing(total_jobs=5, completed_jobs=0, failed_jobs=5)
        assert listing.completion_rate == 0.0

    def test_to_dict_includes_completion_rate(self):
        listing = AgentListing(total_jobs=4, completed_jobs=3, failed_jobs=1)
        d = listing.to_dict()
        assert "completion_rate" in d
        assert d["completion_rate"] == pytest.approx(0.75)

    def test_to_dict_includes_availability(self):
        listing = AgentListing(availability="busy")
        d = listing.to_dict()
        assert d["availability"] == "busy"

    def test_to_dict_includes_earnings(self):
        listing = AgentListing(total_earnings=12.5)
        d = listing.to_dict()
        assert d["total_earnings"] == 12.5


class TestRegistryReputation:
    def test_record_job_completion_success(self):
        reg = MarketplaceRegistry()
        listing = _make_listing("Agent1", agent_id="a1")
        reg.register_agent(listing)
        assert reg.record_job_completion("a1", success=True, earnings=0.05) is True
        assert listing.total_jobs == 1
        assert listing.completed_jobs == 1
        assert listing.total_earnings == pytest.approx(0.05)

    def test_record_job_completion_failure(self):
        reg = MarketplaceRegistry()
        listing = _make_listing("Agent1", agent_id="a1")
        reg.register_agent(listing)
        assert reg.record_job_completion("a1", success=False) is True
        assert listing.total_jobs == 1
        assert listing.failed_jobs == 1
        assert listing.total_earnings == 0.0

    def test_record_job_completion_not_found(self):
        reg = MarketplaceRegistry()
        assert reg.record_job_completion("nope", success=True) is False

    def test_record_multiple_jobs(self):
        reg = MarketplaceRegistry()
        listing = _make_listing("Agent1", agent_id="a1")
        reg.register_agent(listing)
        reg.record_job_completion("a1", success=True, earnings=0.10)
        reg.record_job_completion("a1", success=True, earnings=0.05)
        reg.record_job_completion("a1", success=False)
        assert listing.total_jobs == 3
        assert listing.completed_jobs == 2
        assert listing.failed_jobs == 1
        assert listing.total_earnings == pytest.approx(0.15)
        assert listing.completion_rate == pytest.approx(2 / 3)

    def test_update_agent_rating_rolling(self):
        reg = MarketplaceRegistry()
        listing = _make_listing("Agent1", agent_id="a1", rating=4.0)
        reg.register_agent(listing)
        listing.total_jobs = 5  # more than 1, so rolling average applies
        reg.update_agent_rating("a1", 5.0)
        assert listing.rating == pytest.approx(4.0 * 0.7 + 5.0 * 0.3)

    def test_update_agent_rating_first_job(self):
        reg = MarketplaceRegistry()
        listing = _make_listing("Agent1", agent_id="a1", rating=0.0)
        reg.register_agent(listing)
        listing.total_jobs = 1
        reg.update_agent_rating("a1", 4.5)
        assert listing.rating == 4.5

    def test_update_agent_rating_clamped(self):
        reg = MarketplaceRegistry()
        listing = _make_listing("Agent1", agent_id="a1", rating=4.0)
        reg.register_agent(listing)
        listing.total_jobs = 1
        reg.update_agent_rating("a1", 10.0)
        assert listing.rating == 5.0

    def test_update_agent_rating_not_found(self):
        reg = MarketplaceRegistry()
        assert reg.update_agent_rating("nope", 4.0) is False

    def test_set_availability(self):
        reg = MarketplaceRegistry()
        listing = _make_listing("Agent1", agent_id="a1")
        reg.register_agent(listing)
        assert reg.set_availability("a1", "busy") is True
        assert listing.availability == "busy"

    def test_set_availability_offline(self):
        reg = MarketplaceRegistry()
        listing = _make_listing("Agent1", agent_id="a1")
        reg.register_agent(listing)
        assert reg.set_availability("a1", "offline") is True
        assert listing.availability == "offline"

    def test_set_availability_invalid(self):
        reg = MarketplaceRegistry()
        listing = _make_listing("Agent1", agent_id="a1")
        reg.register_agent(listing)
        assert reg.set_availability("a1", "sleeping") is False

    def test_set_availability_not_found(self):
        reg = MarketplaceRegistry()
        assert reg.set_availability("nope", "busy") is False

    def test_list_available(self):
        reg = MarketplaceRegistry()
        reg.register_agent(_make_listing("A1", agent_id="a1", availability="available"))
        reg.register_agent(_make_listing("A2", agent_id="a2", availability="busy"))
        reg.register_agent(_make_listing("A3", agent_id="a3", availability="available"))
        available = reg.list_available()
        assert len(available) == 2

    def test_sort_by_price(self):
        reg = _seeded_registry()
        sorted_agents = reg.sort_by_price(ascending=True)
        prices = [a.price_per_unit for a in sorted_agents]
        assert prices == sorted(prices)

    def test_sort_by_price_descending(self):
        reg = _seeded_registry()
        sorted_agents = reg.sort_by_price(ascending=False)
        prices = [a.price_per_unit for a in sorted_agents]
        assert prices == sorted(prices, reverse=True)

    def test_sort_by_rating(self):
        reg = _seeded_registry()
        sorted_agents = reg.sort_by_rating()
        ratings = [a.rating for a in sorted_agents]
        assert ratings == sorted(ratings, reverse=True)

    def test_get_reputation(self):
        reg = MarketplaceRegistry()
        listing = _make_listing("Agent1", agent_id="a1", rating=4.5)
        listing.total_jobs = 10
        listing.completed_jobs = 8
        listing.failed_jobs = 2
        listing.total_earnings = 1.5
        reg.register_agent(listing)
        rep = reg.get_reputation("a1")
        assert rep is not None
        assert rep["agent_id"] == "a1"
        assert rep["rating"] == 4.5
        assert rep["total_jobs"] == 10
        assert rep["completion_rate"] == pytest.approx(0.8)
        assert rep["total_earnings"] == 1.5

    def test_get_reputation_not_found(self):
        reg = MarketplaceRegistry()
        assert reg.get_reputation("nope") is None


# ===================================================================
# 2. PaymentLedger
# ===================================================================


class TestPaymentLedger:
    def test_record_event(self):
        ledger = PaymentLedger()
        entry = ledger.record("payment_request", payee="agent1", amount=0.05)
        assert entry.event_type == "payment_request"
        assert entry.payee == "agent1"
        assert entry.amount == 0.05
        assert entry.entry_id.startswith("ledger_")

    def test_get_all(self):
        ledger = PaymentLedger()
        ledger.record("payment_request", amount=0.01)
        ledger.record("escrow_hold", amount=0.02)
        assert len(ledger.get_all()) == 2

    def test_count(self):
        ledger = PaymentLedger()
        ledger.record("a")
        ledger.record("b")
        assert ledger.count() == 2

    def test_filter_by_event_type(self):
        ledger = PaymentLedger()
        ledger.record("payment_request", amount=0.01)
        ledger.record("escrow_hold", amount=0.02)
        ledger.record("payment_request", amount=0.03)
        results = ledger.get_entries(event_type="payment_request")
        assert len(results) == 2

    def test_filter_by_agent_id(self):
        ledger = PaymentLedger()
        ledger.record("escrow_hold", payer="agent1", payee="agent2")
        ledger.record("escrow_hold", payer="agent3", payee="agent4")
        results = ledger.get_entries(agent_id="agent1")
        assert len(results) == 1
        results2 = ledger.get_entries(agent_id="agent2")
        assert len(results2) == 1

    def test_filter_by_task_id(self):
        ledger = PaymentLedger()
        ledger.record("escrow_hold", task_id="task1")
        ledger.record("escrow_hold", task_id="task2")
        results = ledger.get_entries(task_id="task1")
        assert len(results) == 1

    def test_total_volume(self):
        ledger = PaymentLedger()
        ledger.record("a", amount=0.05)
        ledger.record("b", amount=0.10)
        assert ledger.total_volume() == pytest.approx(0.15)

    def test_clear(self):
        ledger = PaymentLedger()
        ledger.record("a")
        ledger.clear()
        assert ledger.count() == 0

    def test_ledger_entry_to_dict(self):
        entry = LedgerEntry(
            event_type="escrow_hold",
            payer="ceo",
            payee="builder",
            amount=0.05,
            task_id="task1",
        )
        d = entry.to_dict()
        assert d["event_type"] == "escrow_hold"
        assert d["payer"] == "ceo"
        assert d["amount"] == 0.05

    def test_combined_filters(self):
        ledger = PaymentLedger()
        ledger.record("escrow_hold", payer="agent1", task_id="t1")
        ledger.record("escrow_release", payer="agent1", task_id="t1")
        ledger.record("escrow_hold", payer="agent2", task_id="t2")
        results = ledger.get_entries(event_type="escrow_hold", agent_id="agent1")
        assert len(results) == 1


# ===================================================================
# 3. PaymentManager
# ===================================================================


class TestPaymentManager:
    def _make_manager(self) -> PaymentManager:
        gate = X402PaymentGate(PaymentConfig(price=0.01, pay_to="0xPayee"))
        escrow = AgentEscrow()
        ledger = PaymentLedger()
        return PaymentManager(gate=gate, escrow=escrow, ledger=ledger)

    def test_create_payment_request(self):
        pm = self._make_manager()
        resp = pm.create_payment_request("/test", 0.10, "agent1")
        assert resp["error"] == "Payment Required"
        assert len(resp["accepts"]) == 1
        assert pm.ledger.count() == 1

    def test_verify_payment_success(self):
        pm = self._make_manager()
        proof = PaymentProof(payer="0xP", payee="0xPayee", amount=0.01)
        assert pm.verify_payment(proof) is True
        assert pm.get_balance("0xPayee") == pytest.approx(0.01)
        entries = pm.ledger.get_entries(event_type="payment_verified")
        assert len(entries) == 1

    def test_verify_payment_failure(self):
        pm = self._make_manager()
        proof = PaymentProof(payer="0xP", payee="0xWrong", amount=0.01)
        assert pm.verify_payment(proof) is False
        entries = pm.ledger.get_entries(event_type="payment_rejected")
        assert len(entries) == 1

    def test_hold_and_release_escrow(self):
        pm = self._make_manager()
        entry = pm.hold_escrow("ceo", "builder", 0.05, "task1")
        assert entry.status == "held"
        assert pm.ledger.count() == 1  # escrow_hold event

        released = pm.release_escrow(entry.escrow_id)
        assert released is not None
        assert released.status == "released"
        assert pm.get_balance("builder") == pytest.approx(0.05)
        assert pm.ledger.count() == 2  # + escrow_release

    def test_hold_and_refund_escrow(self):
        pm = self._make_manager()
        entry = pm.hold_escrow("ceo", "builder", 0.05, "task1")
        refunded = pm.refund_escrow(entry.escrow_id)
        assert refunded is not None
        assert refunded.status == "refunded"
        assert pm.get_balance("ceo") == pytest.approx(0.05)
        assert pm.ledger.count() == 2

    def test_release_nonexistent_escrow(self):
        pm = self._make_manager()
        assert pm.release_escrow("fake") is None

    def test_refund_nonexistent_escrow(self):
        pm = self._make_manager()
        assert pm.refund_escrow("fake") is None

    def test_get_all_balances(self):
        pm = self._make_manager()
        pm.credit("a1", 0.10)
        pm.credit("a2", 0.20)
        balances = pm.get_all_balances()
        assert balances["a1"] == pytest.approx(0.10)
        assert balances["a2"] == pytest.approx(0.20)

    def test_credit_and_debit(self):
        pm = self._make_manager()
        pm.credit("agent1", 1.00)
        assert pm.get_balance("agent1") == pytest.approx(1.00)
        assert pm.debit("agent1", 0.30) is True
        assert pm.get_balance("agent1") == pytest.approx(0.70)

    def test_debit_insufficient(self):
        pm = self._make_manager()
        pm.credit("agent1", 0.10)
        assert pm.debit("agent1", 0.50) is False
        assert pm.get_balance("agent1") == pytest.approx(0.10)

    def test_debit_zero_balance(self):
        pm = self._make_manager()
        assert pm.debit("agent1", 0.01) is False

    def test_multiple_escrow_flows(self):
        pm = self._make_manager()
        e1 = pm.hold_escrow("ceo", "a1", 0.05, "t1")
        e2 = pm.hold_escrow("ceo", "a2", 0.10, "t2")
        pm.release_escrow(e1.escrow_id)
        pm.refund_escrow(e2.escrow_id)
        assert pm.get_balance("a1") == pytest.approx(0.05)
        assert pm.get_balance("ceo") == pytest.approx(0.10)
        assert pm.ledger.count() == 4  # 2 holds + 1 release + 1 refund


# ===================================================================
# 4. Marketplace API v2 — new endpoints
# ===================================================================


@pytest.fixture
def api_client():
    """Create a test client with marketplace routes mounted."""
    import src.api.marketplace_routes as routes_mod
    from fastapi import FastAPI

    # Create fresh state
    fresh_marketplace = MarketplaceRegistry()
    fresh_marketplace.register_agent(_make_listing("APICoder", ["code", "python"], 0.01, 4.5, "api-coder-001"))
    fresh_marketplace.register_agent(_make_listing("APIDesigner", ["design", "ui"], 0.05, 4.8, "api-designer-001"))
    fresh_marketplace.register_agent(_make_listing("APIWriter", ["writing", "docs"], 0.02, 3.5, "api-writer-001", availability="busy"))

    fresh_escrow = AgentEscrow()
    fresh_budget = BudgetTracker(total_budget=100.0)
    fresh_hiring = HiringManager(
        registry=fresh_marketplace,
        escrow=fresh_escrow,
        budget_tracker=fresh_budget,
    )
    fresh_gate = X402PaymentGate(PaymentConfig(pay_to="0xTest", price=0.0))
    fresh_payment_manager = PaymentManager(
        gate=fresh_gate,
        escrow=fresh_escrow,
        ledger=PaymentLedger(),
    )

    # Patch module-level singletons
    old = {
        "marketplace": routes_mod.marketplace,
        "_escrow": routes_mod._escrow,
        "_budget": routes_mod._budget,
        "_hiring_manager": routes_mod._hiring_manager,
        "_payment_gate": routes_mod._payment_gate,
        "_payment_manager": routes_mod._payment_manager,
    }

    routes_mod.marketplace = fresh_marketplace
    routes_mod._escrow = fresh_escrow
    routes_mod._budget = fresh_budget
    routes_mod._hiring_manager = fresh_hiring
    routes_mod._payment_gate = fresh_gate
    routes_mod._payment_manager = fresh_payment_manager

    app = FastAPI()
    app.include_router(routes_mod.router)
    client = TestClient(app)
    yield client

    # Restore originals
    for k, v in old.items():
        setattr(routes_mod, k, v)


class TestMarketplaceAPIv2:
    # -- Agent listing with new fields --

    def test_list_agents_has_reputation_fields(self, api_client):
        resp = api_client.get("/marketplace/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3
        agent = data[0]
        assert "completed_jobs" in agent
        assert "failed_jobs" in agent
        assert "completion_rate" in agent
        assert "total_earnings" in agent
        assert "availability" in agent

    def test_list_agents_sort_by_price(self, api_client):
        resp = api_client.get("/marketplace/agents?sort_by=price")
        data = resp.json()
        prices = [a["price_per_unit"] for a in data]
        assert prices == sorted(prices)

    def test_list_agents_sort_by_rating(self, api_client):
        resp = api_client.get("/marketplace/agents?sort_by=rating")
        data = resp.json()
        ratings = [a["rating"] for a in data]
        assert ratings == sorted(ratings, reverse=True)

    def test_list_agents_available_only(self, api_client):
        resp = api_client.get("/marketplace/agents?available_only=true")
        data = resp.json()
        # APIWriter is busy, should be filtered out
        assert len(data) == 2
        names = [a["name"] for a in data]
        assert "APIWriter" not in names

    # -- Agent registration --

    def test_register_agent(self, api_client):
        resp = api_client.post("/marketplace/agents", json={
            "name": "NewAgent",
            "description": "A brand new agent",
            "skills": ["ml", "data"],
            "price_per_unit": 0.03,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "NewAgent"
        assert data["skills"] == ["ml", "data"]
        assert data["price_per_unit"] == 0.03
        assert data["agent_id"].startswith("agent_")

    def test_register_agent_minimal(self, api_client):
        resp = api_client.post("/marketplace/agents", json={"name": "Minimal"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Minimal"
        assert data["skills"] == []
        assert data["price_per_unit"] == 0.0

    def test_register_agent_no_name_fails(self, api_client):
        resp = api_client.post("/marketplace/agents", json={})
        assert resp.status_code == 422

    def test_register_agent_appears_in_list(self, api_client):
        api_client.post("/marketplace/agents", json={
            "name": "RegisteredAgent",
            "skills": ["test"],
        })
        resp = api_client.get("/marketplace/agents")
        names = [a["name"] for a in resp.json()]
        assert "RegisteredAgent" in names

    # -- Agent details + reputation --

    def test_get_agent_details(self, api_client):
        resp = api_client.get("/marketplace/agents/api-coder-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "APICoder"
        assert data["availability"] == "available"
        assert data["completion_rate"] == 0.0

    # -- Hire status --

    def test_hire_and_check_status(self, api_client):
        # First, hire an agent
        hire_resp = api_client.post("/marketplace/hire", json={
            "description": "Write tests",
            "required_skills": ["code"],
            "budget": 1.0,
        })
        assert hire_resp.status_code == 200
        task_id = hire_resp.json()["task_id"]

        # Check status
        status_resp = api_client.get(f"/marketplace/hire/{task_id}/status")
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["task_id"] == task_id
        assert data["status"] == "completed"
        assert data["escrow_status"] == "released"

    def test_hire_status_not_found(self, api_client):
        resp = api_client.get("/marketplace/hire/nonexistent/status")
        assert resp.status_code == 404


class TestPaymentAPIEndpoints:
    # -- Payment request --

    def test_payment_request(self, api_client):
        resp = api_client.post("/payments/request", json={
            "resource": "/marketplace/hire",
            "amount": 0.05,
            "payee": "agent1",
            "description": "Hire agent",
        })
        assert resp.status_code == 402
        assert resp.headers["x-payment"] == "required"
        data = resp.json()
        assert data["error"] == "Payment Required"
        assert len(data["accepts"]) == 1

    def test_payment_request_missing_fields(self, api_client):
        resp = api_client.post("/payments/request", json={})
        assert resp.status_code == 422

    # -- Payment verify --

    def test_payment_verify_success(self, api_client):
        resp = api_client.post("/payments/verify", json={
            "payer": "0xPayer",
            "payee": "0xTest",
            "amount": 0.01,
            "tx_hash": "0xabc",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["verified"] is True
        assert data["amount"] == 0.01

    def test_payment_verify_wrong_payee(self, api_client):
        resp = api_client.post("/payments/verify", json={
            "payer": "0xPayer",
            "payee": "0xWrong",
            "amount": 0.01,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["verified"] is False

    # -- Balance --

    def test_balance_default_zero(self, api_client):
        resp = api_client.get("/payments/balance/unknown-agent")
        assert resp.status_code == 200
        assert resp.json()["balance"] == 0.0

    def test_balance_after_verified_payment(self, api_client):
        api_client.post("/payments/verify", json={
            "payer": "0xP",
            "payee": "0xTest",
            "amount": 0.50,
        })
        resp = api_client.get("/payments/balance/0xTest")
        assert resp.status_code == 200
        assert resp.json()["balance"] == pytest.approx(0.50)

    # -- Ledger --

    def test_ledger_empty(self, api_client):
        resp = api_client.get("/payments/ledger")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_ledger_after_request_and_verify(self, api_client):
        api_client.post("/payments/request", json={
            "resource": "/test",
            "amount": 0.01,
            "payee": "agent1",
        })
        api_client.post("/payments/verify", json={
            "payer": "0xP",
            "payee": "0xTest",
            "amount": 0.01,
        })
        resp = api_client.get("/payments/ledger")
        data = resp.json()
        assert len(data) == 2
        event_types = [e["event_type"] for e in data]
        assert "payment_request" in event_types
        assert "payment_verified" in event_types

    def test_ledger_filter_by_event_type(self, api_client):
        api_client.post("/payments/request", json={
            "resource": "/a", "amount": 0.01, "payee": "a1",
        })
        api_client.post("/payments/request", json={
            "resource": "/b", "amount": 0.02, "payee": "a2",
        })
        api_client.post("/payments/verify", json={
            "payer": "0xP", "payee": "0xTest", "amount": 0.01,
        })
        resp = api_client.get("/payments/ledger?event_type=payment_request")
        data = resp.json()
        assert len(data) == 2
        assert all(e["event_type"] == "payment_request" for e in data)


# ===================================================================
# 5. End-to-end marketplace + payment flows
# ===================================================================


class TestEndToEndFlows:
    def test_register_hire_and_check_payment(self, api_client):
        """Full flow: register agent → hire → check status → check ledger."""
        # Register
        reg_resp = api_client.post("/marketplace/agents", json={
            "name": "E2EAgent",
            "skills": ["e2e-testing"],
            "price_per_unit": 0.03,
        })
        assert reg_resp.status_code == 201

        # Hire
        hire_resp = api_client.post("/marketplace/hire", json={
            "description": "Run e2e tests",
            "required_skills": ["e2e-testing"],
            "budget": 1.0,
        })
        assert hire_resp.status_code == 200
        task_id = hire_resp.json()["task_id"]
        assert hire_resp.json()["status"] == "completed"

        # Check status
        status_resp = api_client.get(f"/marketplace/hire/{task_id}/status")
        assert status_resp.status_code == 200
        assert status_resp.json()["escrow_status"] == "released"

    def test_multiple_hires_budget_tracking(self, api_client):
        """Hire multiple agents, verify budget decreases."""
        r1 = api_client.post("/marketplace/hire", json={
            "description": "Code task",
            "required_skills": ["code"],
            "budget": 50.0,
        })
        remaining1 = r1.json()["budget_remaining"]

        r2 = api_client.post("/marketplace/hire", json={
            "description": "Another code task",
            "required_skills": ["code"],
            "budget": 50.0,
        })
        remaining2 = r2.json()["budget_remaining"]
        assert remaining2 < remaining1

    def test_payment_flow_request_then_verify(self, api_client):
        """Request payment → verify → check balance."""
        # Create request
        req_resp = api_client.post("/payments/request", json={
            "resource": "/hire/agent1",
            "amount": 0.25,
            "payee": "agent1",
        })
        assert req_resp.status_code == 402

        # Verify
        verify_resp = api_client.post("/payments/verify", json={
            "payer": "ceo",
            "payee": "0xTest",
            "amount": 0.25,
        })
        assert verify_resp.json()["verified"] is True

        # Check balance
        bal_resp = api_client.get("/payments/balance/0xTest")
        assert bal_resp.json()["balance"] == pytest.approx(0.25)

    def test_jobs_list_after_multiple_hires(self, api_client):
        """Multiple hires should all appear in jobs list."""
        api_client.post("/marketplace/hire", json={
            "description": "Task A",
            "required_skills": ["code"],
            "budget": 10.0,
        })
        api_client.post("/marketplace/hire", json={
            "description": "Task B",
            "required_skills": ["design"],
            "budget": 10.0,
        })
        resp = api_client.get("/marketplace/jobs")
        assert resp.status_code == 200
        assert len(resp.json()) == 2
