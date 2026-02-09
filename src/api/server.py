"""FastAPI server for AgentOS.

Provides REST endpoints for:
- Task submission and status tracking
- Agent registry browsing
- Spending/budget dashboard
- Health checks
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.config import get_chat_client, get_settings
from src.mcp_servers.registry_server import registry
from src.mcp_servers.payment_hub import ledger
from src.workflows.sequential import run_sequential
from src.workflows.concurrent import run_concurrent
from src.workflows.group_chat import run_group_chat

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AgentOS",
    description="Autonomous Agent Operating System - Microsoft AI Dev Days Hackathon",
    version="0.1.0",
)


# --- Models ---

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowType(str, Enum):
    SEQUENTIAL = "sequential"
    CONCURRENT = "concurrent"
    GROUP_CHAT = "group_chat"


class TaskSubmission(BaseModel):
    description: str
    workflow: WorkflowType = WorkflowType.SEQUENTIAL
    budget_usd: float = 1.0


class TaskResponse(BaseModel):
    task_id: str
    status: TaskStatus
    description: str
    workflow: WorkflowType
    budget_usd: float
    created_at: float
    result: dict[str, Any] | None = None


# --- In-memory task store ---

@dataclass
class TaskRecord:
    task_id: str
    description: str
    workflow: WorkflowType
    budget_usd: float
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = field(default_factory=time.time)
    result: dict[str, Any] | None = None


_tasks: dict[str, TaskRecord] = {}
_background_tasks: dict[str, asyncio.Task] = {}

_WORKFLOW_RUNNERS = {
    WorkflowType.SEQUENTIAL: run_sequential,
    WorkflowType.CONCURRENT: run_concurrent,
    WorkflowType.GROUP_CHAT: run_group_chat,
}


async def _execute_task(record: TaskRecord) -> None:
    """Run the workflow for a task in the background, updating status."""
    record.status = TaskStatus.RUNNING
    try:
        runner = _WORKFLOW_RUNNERS[record.workflow]
        chat_client = get_chat_client()
        result = await runner(record.description, chat_client=chat_client)
        record.result = result
        record.status = TaskStatus.COMPLETED
    except Exception as exc:
        logger.exception("Task %s failed", record.task_id)
        record.status = TaskStatus.FAILED
        record.result = {"error": str(exc)}
    finally:
        _background_tasks.pop(record.task_id, None)


# --- Endpoints ---

@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "name": "AgentOS",
        "version": "0.1.0",
        "description": "Autonomous Agent Operating System",
        "endpoints": {
            "tasks": "/tasks",
            "agents": "/agents",
            "budget": "/budget",
            "health": "/health",
            "docs": "/docs",
        },
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    settings = get_settings()
    return {
        "status": "healthy",
        "model_provider": settings.model_provider.value,
        "agents_registered": len(registry.list_all()),
        "tasks_total": len(_tasks),
        "total_spent_usdc": ledger.total_spent(),
    }


@app.post("/tasks", response_model=TaskResponse)
async def submit_task(submission: TaskSubmission):
    """Submit a new task for processing.

    The task will be analyzed by the CEO agent and delegated
    to the appropriate workflow and agents.
    """
    task_id = f"task_{uuid.uuid4().hex[:8]}"

    record = TaskRecord(
        task_id=task_id,
        description=submission.description,
        workflow=submission.workflow,
        budget_usd=submission.budget_usd,
    )
    _tasks[task_id] = record

    # Allocate budget in the payment ledger
    ledger.allocate_budget(task_id, submission.budget_usd)

    # Launch workflow execution in the background
    bg = asyncio.create_task(_execute_task(record))
    _background_tasks[task_id] = bg

    return TaskResponse(
        task_id=record.task_id,
        status=record.status,
        description=record.description,
        workflow=record.workflow,
        budget_usd=record.budget_usd,
        created_at=record.created_at,
    )


@app.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str):
    """Get task status and result."""
    record = _tasks.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    return TaskResponse(
        task_id=record.task_id,
        status=record.status,
        description=record.description,
        workflow=record.workflow,
        budget_usd=record.budget_usd,
        created_at=record.created_at,
        result=record.result,
    )


@app.get("/tasks")
async def list_tasks(status: TaskStatus | None = None):
    """List all tasks, optionally filtered by status."""
    tasks = list(_tasks.values())
    if status is not None:
        tasks = [t for t in tasks if t.status == status]

    return {
        "total": len(tasks),
        "tasks": [
            TaskResponse(
                task_id=t.task_id,
                status=t.status,
                description=t.description,
                workflow=t.workflow,
                budget_usd=t.budget_usd,
                created_at=t.created_at,
                result=t.result,
            )
            for t in tasks
        ],
    }


@app.get("/agents")
async def list_agents():
    """List all registered agents in the marketplace."""
    from dataclasses import asdict

    agents = registry.list_all()
    return {
        "total": len(agents),
        "agents": [asdict(a) for a in agents],
    }


@app.get("/agents/search")
async def search_agents(capability: str, max_price: float | None = None):
    """Search for agents by capability."""
    from dataclasses import asdict

    agents = registry.search(capability, max_price)
    return {
        "capability": capability,
        "max_price": max_price,
        "total": len(agents),
        "agents": [asdict(a) for a in agents],
    }


@app.get("/budget")
async def budget_dashboard():
    """Get overall spending dashboard."""
    settings = get_settings()
    return {
        "wallet_address": settings.wallet_address,
        "max_budget_usd": settings.max_budget_usd,
        "total_spent_usdc": ledger.total_spent(),
        "total_transactions": len(ledger.get_transactions()),
        "active_tasks": sum(1 for t in _tasks.values() if t.status == TaskStatus.RUNNING),
    }


@app.get("/budget/{task_id}")
async def task_budget(task_id: str):
    """Get budget details for a specific task."""
    budget = ledger.get_budget(task_id)
    if budget is None:
        raise HTTPException(status_code=404, detail=f"No budget for task {task_id}")

    transactions = ledger.get_transactions(task_id)
    return {
        "task_id": task_id,
        "allocated": budget.allocated,
        "spent": budget.spent,
        "remaining": budget.remaining,
        "transactions": len(transactions),
    }


@app.get("/.well-known/agent-card.json")
async def agent_card():
    """A2A discovery endpoint for AgentOS."""
    settings = get_settings()
    return {
        "name": "AgentOS",
        "description": "Autonomous Agent Operating System with x402 micropayments",
        "version": "0.1.0",
        "capabilities": ["task-execution", "agent-hiring", "budget-management"],
        "authentication": {
            "schemes": ["x402"],
            "x402": {
                "network": settings.x402_network,
                "facilitator": settings.x402_facilitator_url,
            },
        },
        "endpoints": {
            "tasks": "/tasks",
            "agents": "/agents",
            "budget": "/budget",
        },
    }
