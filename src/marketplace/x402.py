"""x402 Payment Layer — HTTP 402 payment gate and escrow for agent marketplace.

Implements the x402 V2 protocol:
- 402 Payment Required responses with structured accepts array
- Payment verification
- Escrow for hire-complete-release lifecycle

x402 V2 response format:
  HTTP 402 Payment Required
  Header: X-Payment: required
  Body: {
    "error": "Payment Required",
    "accepts": [{
      "scheme": "exact",
      "network": "eip155:8453",
      "maxAmountRequired": "0",
      "resource": "<url>",
      "description": "...",
      "mimeType": "application/json",
      "payTo": "0x...",
      "requiredDeadlineSeconds": 300,
      "outputSchema": null,
      "extra": {
        "name": "...",
        "facilitatorUrl": "https://facilitator.payai.network"
      }
    }]
  }
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class PaymentConfig:
    """Configuration for x402 payment requirements."""

    network: str = "eip155:8453"  # Base mainnet
    price: float = 0.0  # USDC amount
    pay_to: str = ""  # Receiver wallet address
    asset: str = "USDC"
    facilitator_url: str = "https://facilitator.payai.network"
    deadline_seconds: int = 300

    def to_accepts_entry(self, resource: str = "", description: str = "") -> dict[str, Any]:
        """Generate a single entry for the x402 'accepts' array."""
        # Convert price to smallest unit string (USDC has 6 decimals)
        amount_micro = str(int(self.price * 1_000_000))
        return {
            "scheme": "exact",
            "network": self.network,
            "maxAmountRequired": amount_micro,
            "resource": resource,
            "description": description,
            "mimeType": "application/json",
            "payTo": self.pay_to,
            "requiredDeadlineSeconds": self.deadline_seconds,
            "outputSchema": None,
            "extra": {
                "name": self.asset,
                "facilitatorUrl": self.facilitator_url,
            },
        }


@dataclass
class PaymentProof:
    """Proof of payment from a payer."""

    payment_id: str = field(default_factory=lambda: f"pay_{uuid.uuid4().hex[:12]}")
    payer: str = ""
    payee: str = ""
    amount: float = 0.0
    network: str = "eip155:8453"
    tx_hash: str = ""
    timestamp: float = field(default_factory=time.time)
    verified: bool = False


class X402PaymentGate:
    """Generates 402 responses and verifies payment proofs.

    Used by marketplace endpoints to gate access behind x402 payment.
    """

    def __init__(self, config: PaymentConfig | None = None) -> None:
        self._config = config or PaymentConfig()
        self._payments: list[PaymentProof] = []
        self._verified_resources: dict[str, PaymentProof] = {}

    @property
    def config(self) -> PaymentConfig:
        return self._config

    def create_402_response(
        self,
        resource: str = "",
        description: str = "Payment required to access this agent service",
        price_override: float | None = None,
    ) -> dict[str, Any]:
        """Generate a 402 Payment Required response body.

        Matches the x402 V2 spec format with accepts array.
        """
        config = self._config
        if price_override is not None:
            # Temporary config with overridden price
            config = PaymentConfig(
                network=self._config.network,
                price=price_override,
                pay_to=self._config.pay_to,
                asset=self._config.asset,
                facilitator_url=self._config.facilitator_url,
                deadline_seconds=self._config.deadline_seconds,
            )

        return {
            "error": "Payment Required",
            "accepts": [config.to_accepts_entry(resource, description)],
        }

    def verify_payment(self, proof: PaymentProof) -> bool:
        """Verify a payment proof.

        In production, this would verify on-chain. For testing,
        we check amount and payee match.
        """
        expected_payee = self._config.pay_to
        if expected_payee and proof.payee != expected_payee:
            return False
        if proof.amount < self._config.price:
            return False

        proof.verified = True
        self._payments.append(proof)
        return True

    def record_verified_payment(self, resource: str, proof: PaymentProof) -> None:
        """Record a verified payment for a resource."""
        self._verified_resources[resource] = proof

    def is_paid(self, resource: str) -> bool:
        """Check if a resource has been paid for."""
        return resource in self._verified_resources

    def payment_history(self, payer: str | None = None) -> list[PaymentProof]:
        """Get payment history, optionally filtered by payer."""
        if payer is None:
            return list(self._payments)
        return [p for p in self._payments if p.payer == payer]

    def total_collected(self) -> float:
        """Total USDC collected from verified payments."""
        return sum(p.amount for p in self._payments if p.verified)


@dataclass
class EscrowEntry:
    """An escrow hold for an agent hiring."""

    escrow_id: str = field(default_factory=lambda: f"escrow_{uuid.uuid4().hex[:12]}")
    payer: str = ""
    payee: str = ""
    amount: float = 0.0
    task_id: str = ""
    status: str = "held"  # "held", "released", "refunded"
    created_at: float = field(default_factory=time.time)
    resolved_at: float | None = None


class AgentEscrow:
    """Escrow system for agent marketplace payments.

    Flow: hold_payment() -> work happens -> release_on_completion() or refund_on_failure()
    """

    def __init__(self) -> None:
        self._entries: dict[str, EscrowEntry] = {}

    def hold_payment(
        self,
        payer: str,
        payee: str,
        amount: float,
        task_id: str,
    ) -> EscrowEntry:
        """Create an escrow hold for a task payment."""
        entry = EscrowEntry(
            payer=payer,
            payee=payee,
            amount=amount,
            task_id=task_id,
            status="held",
        )
        self._entries[entry.escrow_id] = entry
        return entry

    def release_on_completion(self, escrow_id: str) -> EscrowEntry | None:
        """Release escrowed funds to the payee on task completion."""
        entry = self._entries.get(escrow_id)
        if entry is None or entry.status != "held":
            return None
        entry.status = "released"
        entry.resolved_at = time.time()
        return entry

    def refund_on_failure(self, escrow_id: str) -> EscrowEntry | None:
        """Refund escrowed funds to the payer on task failure."""
        entry = self._entries.get(escrow_id)
        if entry is None or entry.status != "held":
            return None
        entry.status = "refunded"
        entry.resolved_at = time.time()
        return entry

    def get_entry(self, escrow_id: str) -> EscrowEntry | None:
        """Get an escrow entry by ID."""
        return self._entries.get(escrow_id)

    def get_entries_for_task(self, task_id: str) -> list[EscrowEntry]:
        """Get all escrow entries for a task."""
        return [e for e in self._entries.values() if e.task_id == task_id]

    def list_held(self) -> list[EscrowEntry]:
        """List all currently held escrow entries."""
        return [e for e in self._entries.values() if e.status == "held"]

    def list_all(self) -> list[EscrowEntry]:
        """List all escrow entries."""
        return list(self._entries.values())

    def total_held(self) -> float:
        """Total USDC currently held in escrow."""
        return sum(e.amount for e in self._entries.values() if e.status == "held")

    def total_released(self) -> float:
        """Total USDC released from escrow."""
        return sum(e.amount for e in self._entries.values() if e.status == "released")

    def clear(self) -> None:
        """Clear all escrow entries."""
        self._entries.clear()


@dataclass
class LedgerEntry:
    """A single entry in the payment ledger (full audit trail)."""

    entry_id: str = field(default_factory=lambda: f"ledger_{uuid.uuid4().hex[:12]}")
    event_type: str = ""  # "payment_request", "payment_verified", "escrow_hold", "escrow_release", "escrow_refund"
    payer: str = ""
    payee: str = ""
    amount: float = 0.0
    task_id: str = ""
    escrow_id: str = ""
    payment_id: str = ""
    network: str = "eip155:8453"
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PaymentLedger:
    """Full audit trail of all payment-related events.

    Records payment requests, verifications, escrow holds, releases, and refunds.
    Provides query and filtering capabilities for the audit trail.
    """

    def __init__(self) -> None:
        self._entries: list[LedgerEntry] = []

    def record(
        self,
        event_type: str,
        payer: str = "",
        payee: str = "",
        amount: float = 0.0,
        task_id: str = "",
        escrow_id: str = "",
        payment_id: str = "",
        network: str = "eip155:8453",
        metadata: dict[str, Any] | None = None,
    ) -> LedgerEntry:
        """Record a ledger event."""
        entry = LedgerEntry(
            event_type=event_type,
            payer=payer,
            payee=payee,
            amount=amount,
            task_id=task_id,
            escrow_id=escrow_id,
            payment_id=payment_id,
            network=network,
            metadata=metadata or {},
        )
        self._entries.append(entry)
        return entry

    def get_entries(
        self,
        event_type: str | None = None,
        agent_id: str | None = None,
        task_id: str | None = None,
    ) -> list[LedgerEntry]:
        """Query ledger entries with optional filters."""
        results = self._entries
        if event_type is not None:
            results = [e for e in results if e.event_type == event_type]
        if agent_id is not None:
            results = [e for e in results if e.payer == agent_id or e.payee == agent_id]
        if task_id is not None:
            results = [e for e in results if e.task_id == task_id]
        return results

    def get_all(self) -> list[LedgerEntry]:
        """Return all ledger entries."""
        return list(self._entries)

    def count(self) -> int:
        return len(self._entries)

    def total_volume(self) -> float:
        """Total USDC volume across all events."""
        return sum(e.amount for e in self._entries)

    def clear(self) -> None:
        self._entries.clear()


class PaymentManager:
    """Manages x402 payment flows: request creation, verification, balance tracking.

    Integrates X402PaymentGate, AgentEscrow, and PaymentLedger into a single
    management layer for the marketplace API.
    """

    def __init__(
        self,
        gate: X402PaymentGate | None = None,
        escrow: AgentEscrow | None = None,
        ledger: PaymentLedger | None = None,
    ) -> None:
        self._gate = gate or X402PaymentGate()
        self._escrow = escrow or AgentEscrow()
        self._ledger = ledger or PaymentLedger()
        self._balances: dict[str, float] = {}  # agent_id -> balance

    @property
    def gate(self) -> X402PaymentGate:
        return self._gate

    @property
    def escrow(self) -> AgentEscrow:
        return self._escrow

    @property
    def ledger(self) -> PaymentLedger:
        return self._ledger

    def create_payment_request(
        self,
        resource: str,
        amount: float,
        payee: str,
        description: str = "Payment required",
    ) -> dict[str, Any]:
        """Create a 402 payment request and log it."""
        resp = self._gate.create_402_response(
            resource=resource,
            description=description,
            price_override=amount,
        )
        self._ledger.record(
            event_type="payment_request",
            payee=payee,
            amount=amount,
            metadata={"resource": resource, "description": description},
        )
        return resp

    def verify_payment(self, proof: PaymentProof) -> bool:
        """Verify a payment proof and record the result."""
        ok = self._gate.verify_payment(proof)
        self._ledger.record(
            event_type="payment_verified" if ok else "payment_rejected",
            payer=proof.payer,
            payee=proof.payee,
            amount=proof.amount,
            payment_id=proof.payment_id,
            network=proof.network,
            metadata={"tx_hash": proof.tx_hash, "verified": ok},
        )
        if ok:
            self._balances[proof.payee] = self._balances.get(proof.payee, 0.0) + proof.amount
        return ok

    def hold_escrow(
        self,
        payer: str,
        payee: str,
        amount: float,
        task_id: str,
    ) -> EscrowEntry:
        """Create an escrow hold and record it in the ledger."""
        entry = self._escrow.hold_payment(payer, payee, amount, task_id)
        self._ledger.record(
            event_type="escrow_hold",
            payer=payer,
            payee=payee,
            amount=amount,
            task_id=task_id,
            escrow_id=entry.escrow_id,
        )
        return entry

    def release_escrow(self, escrow_id: str) -> EscrowEntry | None:
        """Release escrow and credit the payee's balance."""
        entry = self._escrow.release_on_completion(escrow_id)
        if entry is None:
            return None
        self._balances[entry.payee] = self._balances.get(entry.payee, 0.0) + entry.amount
        self._ledger.record(
            event_type="escrow_release",
            payer=entry.payer,
            payee=entry.payee,
            amount=entry.amount,
            task_id=entry.task_id,
            escrow_id=escrow_id,
        )
        return entry

    def refund_escrow(self, escrow_id: str) -> EscrowEntry | None:
        """Refund escrow and credit the payer's balance."""
        entry = self._escrow.refund_on_failure(escrow_id)
        if entry is None:
            return None
        self._balances[entry.payer] = self._balances.get(entry.payer, 0.0) + entry.amount
        self._ledger.record(
            event_type="escrow_refund",
            payer=entry.payer,
            payee=entry.payee,
            amount=entry.amount,
            task_id=entry.task_id,
            escrow_id=escrow_id,
        )
        return entry

    def get_balance(self, agent_id: str) -> float:
        """Get an agent's current balance."""
        return self._balances.get(agent_id, 0.0)

    def get_all_balances(self) -> dict[str, float]:
        """Get all agent balances."""
        return dict(self._balances)

    def credit(self, agent_id: str, amount: float) -> float:
        """Manually credit an agent's balance. Returns new balance."""
        self._balances[agent_id] = self._balances.get(agent_id, 0.0) + amount
        return self._balances[agent_id]

    def debit(self, agent_id: str, amount: float) -> bool:
        """Debit an agent's balance. Returns False if insufficient."""
        current = self._balances.get(agent_id, 0.0)
        if amount > current:
            return False
        self._balances[agent_id] = current - amount
        return True


# Module-level singleton
payment_manager = PaymentManager()


__all__ = [
    "PaymentConfig",
    "PaymentProof",
    "X402PaymentGate",
    "EscrowEntry",
    "AgentEscrow",
    "LedgerEntry",
    "PaymentLedger",
    "PaymentManager",
    "payment_manager",
]
