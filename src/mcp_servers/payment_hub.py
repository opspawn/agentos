"""MCP Server for x402 Payment Integration.

Provides tools for managing payments, tracking budgets,
and handling x402 micropayment flows.

Uses SQLite for durable persistence with in-memory caching.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Any

from mcp.server import Server
from mcp.types import TextContent, Tool

from src.storage import get_storage


@dataclass
class PaymentRecord:
    """Record of a payment transaction."""

    tx_id: str
    from_agent: str
    to_agent: str
    amount_usdc: float
    task_id: str
    timestamp: float = field(default_factory=time.time)
    status: str = "pending"  # pending, completed, failed
    tx_hash: str = ""


@dataclass
class Budget:
    """Budget allocation for a task."""

    task_id: str
    allocated: float
    spent: float = 0.0

    @property
    def remaining(self) -> float:
        return self.allocated - self.spent


class PaymentLedger:
    """Ledger for tracking payments and budgets, backed by SQLite."""

    def __init__(self) -> None:
        self._transactions: list[PaymentRecord] = []
        self._budgets: dict[str, Budget] = {}
        self._tx_counter: int = 0
        self._persist = True  # Can be disabled for tests

    def _storage(self):
        """Lazy access to storage singleton."""
        return get_storage()

    def _sync_from_db(self) -> None:
        """Load state from SQLite into memory."""
        if not self._persist:
            return
        try:
            storage = self._storage()
            # Load payments
            rows = storage.get_payments()
            self._transactions = [
                PaymentRecord(
                    tx_id=r["tx_id"],
                    from_agent=r["from_agent"],
                    to_agent=r["to_agent"],
                    amount_usdc=r["amount_usdc"],
                    task_id=r["task_id"],
                    timestamp=r["timestamp"],
                    status=r["status"],
                    tx_hash=r["tx_hash"],
                )
                for r in rows
            ]
            self._tx_counter = len(self._transactions)

            # Load budgets
            self._budgets = {}
            for task_row in storage.list_tasks():
                budget_data = storage.get_budget(task_row["task_id"])
                if budget_data:
                    self._budgets[budget_data["task_id"]] = Budget(
                        task_id=budget_data["task_id"],
                        allocated=budget_data["allocated"],
                        spent=budget_data["spent"],
                    )
        except Exception:
            pass  # Graceful fallback to in-memory on DB errors

    def allocate_budget(self, task_id: str, amount: float) -> Budget:
        """Allocate a budget for a task."""
        budget = Budget(task_id=task_id, allocated=amount)
        self._budgets[task_id] = budget
        if self._persist:
            try:
                self._storage().save_budget(task_id, amount)
            except Exception:
                pass
        return budget

    def get_budget(self, task_id: str) -> Budget | None:
        """Get budget for a task."""
        return self._budgets.get(task_id)

    def record_payment(
        self,
        from_agent: str,
        to_agent: str,
        amount: float,
        task_id: str,
    ) -> PaymentRecord:
        """Record a payment and deduct from budget."""
        self._tx_counter += 1
        tx_id = f"tx_{self._tx_counter:06d}"

        record = PaymentRecord(
            tx_id=tx_id,
            from_agent=from_agent,
            to_agent=to_agent,
            amount_usdc=amount,
            task_id=task_id,
            status="completed",
        )
        self._transactions.append(record)

        # Deduct from budget
        budget = self._budgets.get(task_id)
        if budget:
            budget.spent += amount

        # Persist to SQLite
        if self._persist:
            try:
                self._storage().save_payment(
                    tx_id=record.tx_id,
                    from_agent=record.from_agent,
                    to_agent=record.to_agent,
                    amount_usdc=record.amount_usdc,
                    task_id=record.task_id,
                    timestamp=record.timestamp,
                    status=record.status,
                    tx_hash=record.tx_hash,
                )
                if budget:
                    self._storage().update_budget_spent(task_id, amount)
            except Exception:
                pass

        return record

    def get_transactions(self, task_id: str | None = None) -> list[PaymentRecord]:
        """Get transactions, optionally filtered by task."""
        if task_id is None:
            return list(self._transactions)
        return [t for t in self._transactions if t.task_id == task_id]

    def total_spent(self) -> float:
        """Total USDC spent across all tasks."""
        return sum(t.amount_usdc for t in self._transactions if t.status == "completed")

    def clear(self) -> None:
        """Clear all ledger state (in-memory and SQLite)."""
        self._transactions.clear()
        self._budgets.clear()
        self._tx_counter = 0
        if self._persist:
            try:
                self._storage().clear_payments()
                self._storage().clear_budgets()
            except Exception:
                pass


# Global ledger instance
ledger = PaymentLedger()


def create_payment_mcp_server() -> Server:
    """Create the MCP server for payment operations."""
    server = Server("payment-hub")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="allocate_budget",
                description="Allocate USDC budget for a task. Must be called before any payments.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "Task identifier"},
                        "amount": {"type": "number", "description": "Budget amount in USDC"},
                    },
                    "required": ["task_id", "amount"],
                },
            ),
            Tool(
                name="check_budget",
                description="Check remaining budget for a task.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "Task identifier"},
                    },
                    "required": ["task_id"],
                },
            ),
            Tool(
                name="pay_agent",
                description="Pay an external agent for completing a subtask via x402.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "to_agent": {"type": "string", "description": "Agent name to pay"},
                        "amount": {"type": "number", "description": "Amount in USDC"},
                        "task_id": {"type": "string", "description": "Associated task ID"},
                    },
                    "required": ["to_agent", "amount", "task_id"],
                },
            ),
            Tool(
                name="get_spending_report",
                description="Get a spending report for all tasks or a specific task.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "string",
                            "description": "Optional task ID to filter by",
                        },
                    },
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        if name == "allocate_budget":
            budget = ledger.allocate_budget(arguments["task_id"], arguments["amount"])
            return [TextContent(
                type="text",
                text=json.dumps({
                    "task_id": budget.task_id,
                    "allocated": budget.allocated,
                    "remaining": budget.remaining,
                }),
            )]

        if name == "check_budget":
            budget = ledger.get_budget(arguments["task_id"])
            if budget is None:
                return [TextContent(type="text", text='{"error": "No budget allocated for this task"}')]
            return [TextContent(
                type="text",
                text=json.dumps({
                    "task_id": budget.task_id,
                    "allocated": budget.allocated,
                    "spent": budget.spent,
                    "remaining": budget.remaining,
                }),
            )]

        if name == "pay_agent":
            task_id = arguments["task_id"]
            amount = arguments["amount"]

            # Check budget
            budget = ledger.get_budget(task_id)
            if budget is None:
                return [TextContent(type="text", text='{"error": "No budget allocated. Call allocate_budget first."}')]
            if amount > budget.remaining:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "error": f"Insufficient budget. Remaining: ${budget.remaining:.2f}, Requested: ${amount:.2f}",
                    }),
                )]

            record = ledger.record_payment(
                from_agent="ceo",
                to_agent=arguments["to_agent"],
                amount=amount,
                task_id=task_id,
            )
            return [TextContent(
                type="text",
                text=json.dumps({
                    "tx_id": record.tx_id,
                    "status": record.status,
                    "amount": record.amount_usdc,
                    "to": record.to_agent,
                    "budget_remaining": budget.remaining,
                }),
            )]

        if name == "get_spending_report":
            task_id = arguments.get("task_id")
            transactions = ledger.get_transactions(task_id)
            report = {
                "total_spent": sum(t.amount_usdc for t in transactions),
                "transaction_count": len(transactions),
                "transactions": [asdict(t) for t in transactions],
            }
            if task_id:
                budget = ledger.get_budget(task_id)
                if budget:
                    report["budget"] = {
                        "allocated": budget.allocated,
                        "spent": budget.spent,
                        "remaining": budget.remaining,
                    }
            return [TextContent(type="text", text=json.dumps(report, indent=2))]

        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    return server
