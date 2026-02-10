"""Edge case tests for marketplace v2 + payment integration.

Covers boundary conditions, error paths, and integration edge cases.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.marketplace import AgentListing, MarketplaceRegistry
from src.marketplace.x402 import (
    PaymentConfig,
    PaymentProof,
    X402PaymentGate,
    AgentEscrow,
    PaymentLedger,
    PaymentManager,
)
from src.marketplace.hiring import HiringManager, HireRequest, BudgetTracker


def _make_listing(name: str, skills: list[str], price: float = 0.01, rating: float = 4.0, agent_id: str | None = None) -> AgentListing:
    listing = AgentListing(
        name=name, description=f"Test: {name}", skills=skills,
        pricing_model="per-task", price_per_unit=price, rating=rating,
    )
    if agent_id:
        listing.agent_id = agent_id
    return listing


# ===================================================================
# Agent listing edge cases
# ===================================================================


class TestAgentListingEdgeCases:
    def test_zero_price_display(self):
        listing = AgentListing(price_per_unit=0.0)
        assert "$0.0000/task" in listing.price_display

    def test_very_high_price(self):
        listing = AgentListing(price_per_unit=999999.99)
        assert "999999.99" in listing.price_display

    def test_empty_skills_no_match(self):
        listing = AgentListing(skills=[])
        assert listing.matches_skill("anything") is False

    def test_completion_rate_one_job_success(self):
        listing = AgentListing(total_jobs=1, completed_jobs=1)
        assert listing.completion_rate == 1.0

    def test_completion_rate_one_job_failure(self):
        listing = AgentListing(total_jobs=1, completed_jobs=0, failed_jobs=1)
        assert listing.completion_rate == 0.0

    def test_metadata_preserved(self):
        listing = AgentListing(metadata={"custom": True, "version": 2})
        d = listing.to_dict()
        assert d["metadata"]["custom"] is True
        assert d["metadata"]["version"] == 2


# ===================================================================
# Registry edge cases
# ===================================================================


class TestRegistryEdgeCases:
    def test_register_same_id_overwrites(self):
        reg = MarketplaceRegistry()
        l1 = _make_listing("Agent1", ["code"], agent_id="same-id")
        l2 = _make_listing("Agent2", ["design"], agent_id="same-id")
        reg.register_agent(l1)
        reg.register_agent(l2)
        assert reg.count() == 1
        assert reg.get_agent("same-id").name == "Agent2"

    def test_discover_case_insensitive(self):
        reg = MarketplaceRegistry()
        reg.register_agent(_make_listing("Coder", ["Python"]))
        results = reg.discover_agents("python")
        assert len(results) == 1

    def test_discover_empty_query(self):
        reg = MarketplaceRegistry()
        reg.register_agent(_make_listing("Coder", ["code"]))
        results = reg.discover_agents("")
        assert len(results) == 1  # empty string matches everything

    def test_sort_empty_registry(self):
        reg = MarketplaceRegistry()
        assert reg.sort_by_price() == []
        assert reg.sort_by_rating() == []

    def test_list_available_empty(self):
        reg = MarketplaceRegistry()
        assert reg.list_available() == []

    def test_record_job_earnings_accumulate(self):
        reg = MarketplaceRegistry()
        listing = _make_listing("Agent1", ["code"], agent_id="a1")
        reg.register_agent(listing)
        for i in range(5):
            reg.record_job_completion("a1", success=True, earnings=0.01)
        assert listing.total_earnings == pytest.approx(0.05)
        assert listing.total_jobs == 5
        assert listing.completed_jobs == 5


# ===================================================================
# PaymentManager edge cases
# ===================================================================


class TestPaymentManagerEdgeCases:
    def test_balance_unknown_agent_is_zero(self):
        pm = PaymentManager()
        assert pm.get_balance("unknown") == 0.0

    def test_credit_negative_amount(self):
        pm = PaymentManager()
        pm.credit("agent1", -5.0)
        assert pm.get_balance("agent1") == -5.0  # no validation on credit

    def test_double_release_returns_none(self):
        pm = PaymentManager()
        entry = pm.hold_escrow("ceo", "agent1", 0.05, "t1")
        pm.release_escrow(entry.escrow_id)
        assert pm.release_escrow(entry.escrow_id) is None

    def test_double_refund_returns_none(self):
        pm = PaymentManager()
        entry = pm.hold_escrow("ceo", "agent1", 0.05, "t1")
        pm.refund_escrow(entry.escrow_id)
        assert pm.refund_escrow(entry.escrow_id) is None

    def test_ledger_records_payment_details(self):
        gate = X402PaymentGate(PaymentConfig(price=0.0, pay_to=""))
        pm = PaymentManager(gate=gate)
        proof = PaymentProof(payer="a", payee="b", amount=0.01, tx_hash="0xabc123")
        pm.verify_payment(proof)
        entries = pm.ledger.get_entries(event_type="payment_verified")
        assert len(entries) == 1
        assert entries[0].metadata["tx_hash"] == "0xabc123"

    def test_escrow_hold_release_balance_flow(self):
        pm = PaymentManager()
        e = pm.hold_escrow("buyer", "seller", 1.0, "t1")
        assert pm.escrow.total_held() == 1.0
        pm.release_escrow(e.escrow_id)
        assert pm.escrow.total_held() == 0.0
        assert pm.get_balance("seller") == pytest.approx(1.0)

    def test_escrow_hold_refund_balance_flow(self):
        pm = PaymentManager()
        e = pm.hold_escrow("buyer", "seller", 1.0, "t1")
        pm.refund_escrow(e.escrow_id)
        assert pm.get_balance("buyer") == pytest.approx(1.0)
        assert pm.get_balance("seller") == 0.0


# ===================================================================
# Hiring edge cases
# ===================================================================


class TestHiringEdgeCases:
    def test_hire_with_exhausted_global_budget(self):
        reg = MarketplaceRegistry()
        reg.register_agent(_make_listing("Worker", ["code"], price=0.50))
        budget = BudgetTracker(total_budget=0.40)  # global budget < agent price
        manager = HiringManager(registry=reg, budget_tracker=budget)
        req = HireRequest(required_skills=["code"], budget=10.0)  # per-request budget is fine
        result = manager.hire(req)
        assert result.status == "budget_exceeded"

    def test_hire_free_agent(self):
        reg = MarketplaceRegistry()
        reg.register_agent(_make_listing("Free", ["code"], price=0.0))
        budget = BudgetTracker(total_budget=10.0)
        manager = HiringManager(registry=reg, budget_tracker=budget)
        req = HireRequest(required_skills=["code"], budget=1.0)
        result = manager.hire(req)
        assert result.status == "completed"
        assert result.agreed_price == 0.0

    def test_hire_multiple_sequential(self):
        reg = MarketplaceRegistry()
        reg.register_agent(_make_listing("Worker", ["code"], price=0.01))
        budget = BudgetTracker(total_budget=10.0)
        manager = HiringManager(registry=reg, budget_tracker=budget)
        results = []
        for _ in range(5):
            req = HireRequest(required_skills=["code"], budget=1.0)
            results.append(manager.hire(req))
        assert all(r.status == "completed" for r in results)
        assert len(manager.hire_history) == 5
