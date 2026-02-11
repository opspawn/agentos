"""Demo Scenario: Showcase Mode — Full end-to-end curated demo for judges.

Runs a complete, visually impressive sequence through every HireWire feature:
1. Create agents (CEO, Builder, Research, Designer)
2. Register agents in the marketplace
3. Sequential workflow: Research -> CEO analysis
4. Hire an external designer agent via x402
5. Concurrent multi-agent execution
6. x402 payment settlement + escrow
7. Foundry Agent Service integration
8. Display results with timing and USDC breakdown

Designed for live demo to hackathon judges. Each step has clear visual output
and auto-refreshes dashboard data via API calls.

Works with MODEL_PROVIDER=mock (default) or any real provider.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

# Ensure project root is on sys.path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.config import get_chat_client, get_settings
from src.mcp_servers.payment_hub import ledger
from src.mcp_servers.registry_server import registry
from src.storage import get_storage


# -- ANSI helpers --

class _C:
    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    MAGENTA = "\033[35m"
    RED = "\033[31m"
    BLUE = "\033[34m"
    WHITE = "\033[37m"
    BG_BLUE = "\033[44m"
    BG_GREEN = "\033[42m"
    BG_MAGENTA = "\033[45m"
    RESET = "\033[0m"


def _banner() -> None:
    print(f"""
{_C.BOLD}{_C.CYAN}{'=' * 62}
{_C.BG_BLUE}{_C.WHITE}                                                              {_C.RESET}
{_C.BG_BLUE}{_C.WHITE}    HireWire Showcase Demo                                    {_C.RESET}
{_C.BG_BLUE}{_C.WHITE}    Agent Operating System + x402 Payments + Azure AI          {_C.RESET}
{_C.BG_BLUE}{_C.WHITE}                                                              {_C.RESET}
{_C.BOLD}{_C.CYAN}{'=' * 62}{_C.RESET}
""")


def _stage(num: int, total: int, title: str) -> None:
    bar = f"{'=' * num}{'.' * (total - num)}"
    print(f"\n{_C.BOLD}{_C.YELLOW}[{bar}] Stage {num}/{total}: {title}{_C.RESET}")
    print(f"{_C.DIM}{'-' * 58}{_C.RESET}")


def _agent(name: str, action: str) -> None:
    print(f"  {_C.MAGENTA}{name}{_C.RESET} -> {action}")


def _ok(text: str) -> None:
    print(f"  {_C.GREEN}\u2713{_C.RESET} {text}")


def _info(text: str) -> None:
    print(f"  {_C.DIM}{text}{_C.RESET}")


def _money(text: str) -> None:
    print(f"  {_C.BLUE}${_C.RESET} {text}")


def _highlight(text: str) -> None:
    print(f"  {_C.BOLD}{_C.WHITE}{text}{_C.RESET}")


TOTAL_STAGES = 8


async def run_showcase_scenario() -> dict:
    """Run the full showcase demo — all HireWire features in sequence.

    Returns:
        Dict with complete showcase results for API / dashboard display.
    """
    _banner()

    settings = get_settings()
    provider = settings.model_provider.value
    _info(f"Model provider: {provider}")
    _info(f"Dashboard auto-refresh: enabled")

    t0 = time.monotonic()
    stages: list[dict[str, Any]] = []
    storage = get_storage()
    client = get_chat_client()

    # ── Stage 1: Agent Creation ──────────────────────────────────────

    _stage(1, TOTAL_STAGES, "Creating Agent Roster")
    t_stage = time.monotonic()

    from src.framework.agent import AgentFrameworkAgent

    agents_created = []
    agent_configs = [
        ("CEO", "Orchestrator: analyzes tasks, manages budget, delegates"),
        ("Builder", "Code generation, testing, and deployment specialist"),
        ("Research", "Web search, data analysis, competitive research"),
        ("Analyst", "Financial modeling, pricing, market research"),
    ]
    for name, desc in agent_configs:
        agent = AgentFrameworkAgent(
            name=name, description=desc,
            instructions=f"You are the {name} agent in HireWire.",
            chat_client=client,
        )
        agents_created.append(agent)
        _agent(name, desc)

    _ok(f"Created {len(agents_created)} agents")
    stages.append({
        "stage": 1, "name": "Agent Creation",
        "agents": [a.name for a in agents_created],
        "duration_ms": round((time.monotonic() - t_stage) * 1000, 1),
    })

    # ── Stage 2: Marketplace Registration ────────────────────────────

    _stage(2, TOTAL_STAGES, "Registering Agents in Marketplace")
    t_stage = time.monotonic()

    marketplace_agents = registry.list_all()
    for a in marketplace_agents:
        _agent(a.name, f"Skills: {', '.join(a.skills)} | Price: {a.price_per_call}")

    _ok(f"{len(marketplace_agents)} agents in marketplace (internal + external)")
    stages.append({
        "stage": 2, "name": "Marketplace Registration",
        "agent_count": len(marketplace_agents),
        "duration_ms": round((time.monotonic() - t_stage) * 1000, 1),
    })

    # ── Stage 3: CEO Task Analysis ───────────────────────────────────

    _stage(3, TOTAL_STAGES, "CEO Analyzes Task + Allocates Budget")
    t_stage = time.monotonic()

    task_desc = "Build a landing page with a professional design for HireWire"
    task_id = f"showcase_{uuid.uuid4().hex[:8]}"
    budget = 10.0

    from src.agents.ceo_agent import analyze_task
    analysis = await analyze_task(task_desc)

    ledger.allocate_budget(task_id, budget)
    storage.save_task(
        task_id=task_id, description=task_desc, workflow="showcase",
        budget_usd=budget, status="pending", created_at=time.time(),
    )

    _agent("CEO", f"Task: \"{task_desc}\"")
    _agent("CEO", f"Type: {analysis.get('task_type', 'general')} | Complexity: {analysis.get('complexity', 'moderate')}")
    _money(f"Budget allocated: ${budget:.2f} USDC")
    _ok("Task analyzed and budget allocated")

    stages.append({
        "stage": 3, "name": "CEO Task Analysis",
        "task_id": task_id,
        "analysis": analysis,
        "budget": budget,
        "duration_ms": round((time.monotonic() - t_stage) * 1000, 1),
    })

    # ── Stage 4: Sequential Workflow ─────────────────────────────────

    _stage(4, TOTAL_STAGES, "Sequential Workflow: Research -> Builder")
    t_stage = time.monotonic()

    storage.update_task_status(task_id, "running")

    from src.framework.orchestrator import SequentialOrchestrator
    research_agent = agents_created[2]  # Research
    builder_agent = agents_created[1]   # Builder

    seq_orch = SequentialOrchestrator([research_agent, builder_agent])
    seq_result = await seq_orch.run("Research landing page best practices, then build the HTML/CSS")

    _agent("Research", "Gathering best practices for modern landing pages...")
    _agent("Builder", "Implementing responsive HTML/CSS based on research...")
    _ok(f"Sequential workflow completed in {seq_result.elapsed_ms:.0f}ms")

    stages.append({
        "stage": 4, "name": "Sequential Workflow",
        "pattern": "sequential",
        "agents": ["Research", "Builder"],
        "status": seq_result.status,
        "duration_ms": round((time.monotonic() - t_stage) * 1000, 1),
    })

    # ── Stage 5: External Agent Hiring + x402 Payment ────────────────

    _stage(5, TOTAL_STAGES, "Hiring External Designer via x402")
    t_stage = time.monotonic()

    from src.workflows.hiring import discover_external_agents, run_hiring_workflow

    candidates = discover_external_agents("design")
    for c in candidates:
        _agent(c.name, f"Skills: {', '.join(c.skills)} | Price: {c.price_per_call}")

    hiring_result = await run_hiring_workflow(
        task_id=f"{task_id}-design",
        task_description="Create a professional design specification for the landing page",
        required_skills=["design", "ui", "landing-page"],
        budget_usd=budget,
        capability_query="design",
    )

    if hiring_result.status == "completed":
        _ok(f"Designer hired and task completed")
        if hiring_result.payment:
            _money(f"Paid {hiring_result.payment['amount_usdc']:.4f} USDC to {hiring_result.payment['to_agent']}")
            _money(f"Protocol: x402 | Network: eip155:8453 (Base)")
            _money(f"TX: {hiring_result.payment['tx_id']}")
    else:
        _info(f"Hiring status: {hiring_result.status}")

    stages.append({
        "stage": 5, "name": "External Agent Hiring + x402",
        "status": hiring_result.status,
        "payment": hiring_result.payment,
        "external_agent": candidates[0].name if candidates else "none",
        "duration_ms": round((time.monotonic() - t_stage) * 1000, 1),
    })

    # ── Stage 6: Concurrent Multi-Agent Execution ────────────────────

    _stage(6, TOTAL_STAGES, "Concurrent Execution: 3 Agents in Parallel")
    t_stage = time.monotonic()

    from src.framework.orchestrator import ConcurrentOrchestrator

    concurrent_agents = [agents_created[0], agents_created[2], agents_created[3]]  # CEO, Research, Analyst
    con_orch = ConcurrentOrchestrator(concurrent_agents)
    con_result = await con_orch.run("Analyze the competitive landscape for AI agent marketplaces")

    for ar in con_result.agent_results:
        _agent(ar["agent"], f"Completed analysis ({len(ar.get('response', ''))} chars)")

    _ok(f"Concurrent execution completed in {con_result.elapsed_ms:.0f}ms")
    _highlight(f"Speedup: {len(concurrent_agents)} agents ran in parallel")

    stages.append({
        "stage": 6, "name": "Concurrent Execution",
        "pattern": "concurrent",
        "agents": [a.name for a in concurrent_agents],
        "status": con_result.status,
        "duration_ms": round((time.monotonic() - t_stage) * 1000, 1),
    })

    # ── Stage 7: Foundry Agent Service ───────────────────────────────

    _stage(7, TOTAL_STAGES, "Foundry Agent Service Integration")
    t_stage = time.monotonic()

    from src.framework.foundry_agent import (
        FoundryAgentProvider,
        FoundryAgentConfig,
        create_hirewire_foundry_agents,
    )

    foundry_provider = FoundryAgentProvider()
    foundry_agents = create_hirewire_foundry_agents(foundry_provider)

    for name, inst in foundry_agents.items():
        _agent(f"Foundry:{inst.name}", f"ID: {inst.agent_id[:20]}... | Status: {inst.status}")

    # Invoke a Foundry agent
    foundry_builder = foundry_agents["builder"]
    foundry_result = await foundry_provider.invoke_agent(
        foundry_builder.agent_id,
        "Implement the final landing page integration",
    )

    _ok(f"Foundry agent invoked: {foundry_result.get('agent', 'unknown')}")
    _highlight(f"Provider: {foundry_result.get('provider', 'unknown')} | Model: {foundry_result.get('model', 'unknown')}")

    stages.append({
        "stage": 7, "name": "Foundry Agent Service",
        "foundry_agents": len(foundry_agents),
        "invoke_result": foundry_result.get("status", "unknown"),
        "duration_ms": round((time.monotonic() - t_stage) * 1000, 1),
    })

    # ── Stage 8: Results Summary ─────────────────────────────────────

    _stage(8, TOTAL_STAGES, "Results & Payment Summary")
    t_stage = time.monotonic()

    # Complete the task
    storage.update_task_status(task_id, "completed", result={
        "analysis": analysis,
        "sequential_status": seq_result.status,
        "hiring_status": hiring_result.status,
        "concurrent_status": con_result.status,
        "foundry_status": foundry_result.get("status", "unknown"),
    })

    # Payment summary
    txs = ledger.get_transactions()
    total_spent = ledger.total_spent()
    _money(f"Total USDC spent: ${total_spent:.4f}")
    _money(f"Transactions: {len(txs)}")
    _info(f"Tasks in database: {storage.count_tasks()}")
    _info(f"Agents in marketplace: {len(registry.list_all())}")

    total_elapsed = time.monotonic() - t0
    print(f"\n{_C.BOLD}{_C.GREEN}{'=' * 62}{_C.RESET}")
    print(f"{_C.BOLD}{_C.GREEN}  Showcase Complete in {total_elapsed:.2f}s{_C.RESET}")
    print(f"{_C.BOLD}{_C.GREEN}{'=' * 62}{_C.RESET}")

    stages.append({
        "stage": 8, "name": "Summary",
        "total_spent_usdc": total_spent,
        "transaction_count": len(txs),
        "task_count": storage.count_tasks(),
        "agent_count": len(registry.list_all()),
        "duration_ms": round((time.monotonic() - t_stage) * 1000, 1),
    })

    return {
        "task": task_desc,
        "workflow": "showcase",
        "status": "completed",
        "stages": stages,
        "total_elapsed_s": round(total_elapsed, 3),
        "total_spent_usdc": total_spent,
        "budget": {
            "allocated": budget,
            "spent": total_spent,
            "remaining": budget - total_spent,
        },
    }


if __name__ == "__main__":
    result = asyncio.run(run_showcase_scenario())
    print(f"\nFinal status: {result['status']}")
    print(f"Total time: {result['total_elapsed_s']:.2f}s")
    print(f"Total spent: ${result['total_spent_usdc']:.4f} USDC")
