#!/usr/bin/env python3
"""HireWire Polished CLI Demo Runner.

Demonstrates the full HireWire pipeline with rich terminal output:
CEO receives task -> discovers agents -> evaluates candidates ->
hires best agent -> executes via A2A -> pays with USDC via x402.

Usage:
    python demo.py              # Default mode with realistic timing
    python demo.py --fast       # Fast mode (skip delays)
    python demo.py --budget 10  # Custom budget

Environment:
    MODEL_PROVIDER  - mock (default), ollama, azure_ai, openai
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

# Ensure project root is on sys.path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.align import Align
from rich.rule import Rule
from rich import box

# ---------------------------------------------------------------------------
# Demo data structures
# ---------------------------------------------------------------------------

@dataclass
class MockExternalAgent:
    """An external agent available for hire in the demo."""
    name: str
    description: str
    skills: list[str]
    price_per_call: float
    rating: float
    tasks_completed: int
    endpoint: str = "http://127.0.0.1:9100"
    protocol: str = "a2a"
    payment: str = "x402"

    @property
    def price_str(self) -> str:
        return f"${self.price_per_call:.2f}"


# Three mock external agents with varying capabilities and prices
DEMO_AGENTS = [
    MockExternalAgent(
        name="DesignStudio AI",
        description="Premium UI/UX design, mockups, and branding",
        skills=["design", "ui", "ux", "mockup", "landing-page", "branding"],
        price_per_call=0.15,
        rating=4.9,
        tasks_completed=342,
    ),
    MockExternalAgent(
        name="PixelForge",
        description="Fast wireframes and basic page layouts",
        skills=["design", "wireframe", "layout", "landing-page"],
        price_per_call=0.05,
        rating=4.2,
        tasks_completed=89,
    ),
    MockExternalAgent(
        name="CodeCraft Agent",
        description="Full-stack web development and API integration",
        skills=["code", "frontend", "backend", "api", "deployment"],
        price_per_call=0.10,
        rating=4.6,
        tasks_completed=217,
    ),
]


@dataclass
class DemoConfig:
    """Configuration for a demo run."""
    fast: bool = False
    budget: float = 5.0
    task_description: str = (
        "Build a professional landing page for HireWire with modern design, "
        "responsive layout, and interactive agent marketplace showcase"
    )
    required_skills: list[str] = field(
        default_factory=lambda: ["design", "ui", "landing-page"]
    )


@dataclass
class DemoStepResult:
    """Result of a single demo step."""
    name: str
    status: str  # "completed" | "failed" | "skipped"
    duration_s: float
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class DemoResult:
    """Full result of a demo run."""
    task: str
    agent_hired: str
    capability_score: float
    price_paid: float
    budget_allocated: float
    budget_remaining: float
    total_elapsed_s: float
    steps: list[DemoStepResult] = field(default_factory=list)
    status: str = "completed"

# ---------------------------------------------------------------------------
# Demo workflow orchestration (testable core logic)
# ---------------------------------------------------------------------------

def discover_agents(
    agents: list[MockExternalAgent],
    required_skills: list[str],
) -> list[MockExternalAgent]:
    """Filter agents that have at least one matching skill."""
    required_lower = {s.lower() for s in required_skills}
    matches = []
    for agent in agents:
        agent_skills = {s.lower() for s in agent.skills}
        if agent_skills & required_lower:
            matches.append(agent)
    return matches


def evaluate_agent(
    agent: MockExternalAgent,
    required_skills: list[str],
) -> dict[str, Any]:
    """Evaluate an agent against required skills and return a scored assessment."""
    agent_skills_lower = {s.lower() for s in agent.skills}
    required_lower = {s.lower() for s in required_skills}

    if not required_lower:
        match_score = 1.0
    else:
        overlap = agent_skills_lower & required_lower
        match_score = len(overlap) / len(required_lower)

    # Composite score: 60% skill match + 25% rating + 15% experience
    rating_normalized = agent.rating / 5.0
    experience_normalized = min(agent.tasks_completed / 500.0, 1.0)
    composite = 0.60 * match_score + 0.25 * rating_normalized + 0.15 * experience_normalized

    return {
        "agent_name": agent.name,
        "skill_match": round(match_score, 3),
        "rating_score": round(rating_normalized, 3),
        "experience_score": round(experience_normalized, 3),
        "composite_score": round(composite, 3),
        "price": agent.price_per_call,
        "matched_skills": sorted(agent_skills_lower & required_lower),
        "approved": match_score >= 0.3,
    }


def select_best_agent(
    evaluations: list[dict[str, Any]],
    budget_remaining: float,
) -> dict[str, Any] | None:
    """Select the best agent from evaluations within budget."""
    affordable = [
        e for e in evaluations
        if e["approved"] and e["price"] <= budget_remaining
    ]
    if not affordable:
        return None
    return max(affordable, key=lambda e: e["composite_score"])


def simulate_task_execution(agent_name: str, task_description: str) -> dict[str, Any]:
    """Simulate an external agent executing a task via A2A."""
    return {
        "task_id": f"task-{uuid.uuid4().hex[:8]}",
        "status": "completed",
        "agent": agent_name,
        "deliverable": _generate_deliverable(agent_name, task_description),
        "protocol": "A2A (Google Agent-to-Agent)",
    }


def simulate_payment(
    from_agent: str,
    to_agent: str,
    amount: float,
    task_id: str,
) -> dict[str, Any]:
    """Simulate an x402 USDC payment."""
    return {
        "tx_id": f"tx_{uuid.uuid4().hex[:12]}",
        "from": from_agent,
        "to": to_agent,
        "amount_usdc": amount,
        "task_id": task_id,
        "network": "Base (EIP-155:8453)",
        "protocol": "x402",
        "status": "confirmed",
    }


def run_demo_workflow(config: DemoConfig) -> DemoResult:
    """Execute the full demo workflow (pure logic, no display).

    This is the testable core: discovery -> evaluation -> hiring ->
    execution -> payment.
    """
    t0 = time.monotonic()
    steps: list[DemoStepResult] = []
    budget_remaining = config.budget

    # Step 1: Discovery
    s1 = time.monotonic()
    candidates = discover_agents(DEMO_AGENTS, config.required_skills)
    steps.append(DemoStepResult(
        name="Discovery",
        status="completed",
        duration_s=round(time.monotonic() - s1, 4),
        details={"candidates_found": len(candidates),
                 "agents": [a.name for a in candidates]},
    ))

    # Step 2: Evaluation
    s2 = time.monotonic()
    evaluations = [evaluate_agent(a, config.required_skills) for a in candidates]
    steps.append(DemoStepResult(
        name="Evaluation",
        status="completed",
        duration_s=round(time.monotonic() - s2, 4),
        details={"evaluations": evaluations},
    ))

    # Step 3: Hiring decision
    s3 = time.monotonic()
    best = select_best_agent(evaluations, budget_remaining)
    if best is None:
        return DemoResult(
            task=config.task_description,
            agent_hired="none",
            capability_score=0.0,
            price_paid=0.0,
            budget_allocated=config.budget,
            budget_remaining=budget_remaining,
            total_elapsed_s=round(time.monotonic() - t0, 3),
            steps=steps,
            status="no_suitable_agents",
        )
    steps.append(DemoStepResult(
        name="Hiring",
        status="completed",
        duration_s=round(time.monotonic() - s3, 4),
        details={"selected": best["agent_name"],
                 "score": best["composite_score"],
                 "price": best["price"]},
    ))

    # Step 4: Task execution via A2A
    s4 = time.monotonic()
    exec_result = simulate_task_execution(best["agent_name"], config.task_description)
    steps.append(DemoStepResult(
        name="Execution",
        status="completed",
        duration_s=round(time.monotonic() - s4, 4),
        details=exec_result,
    ))

    # Step 5: Payment via x402
    s5 = time.monotonic()
    payment = simulate_payment("CEO Agent", best["agent_name"],
                               best["price"], exec_result["task_id"])
    budget_remaining -= best["price"]
    steps.append(DemoStepResult(
        name="Payment",
        status="completed",
        duration_s=round(time.monotonic() - s5, 4),
        details=payment,
    ))

    return DemoResult(
        task=config.task_description,
        agent_hired=best["agent_name"],
        capability_score=best["composite_score"],
        price_paid=best["price"],
        budget_allocated=config.budget,
        budget_remaining=round(budget_remaining, 2),
        total_elapsed_s=round(time.monotonic() - t0, 3),
        steps=steps,
        status="completed",
    )


def _generate_deliverable(agent_name: str, description: str) -> str:
    """Generate a mock deliverable string."""
    return (
        f"Landing Page Design Specification\n"
        f"Agent: {agent_name}\n"
        f"---\n"
        f"- Hero section: Bold headline + animated agent network visualization\n"
        f"- Feature grid: Agent Hiring | x402 Payments | Multi-Agent Orchestration\n"
        f"- Live marketplace widget showing real agent availability\n"
        f"- Responsive (Desktop 1200px+ / Tablet 768px / Mobile <768px)\n"
        f"- Color: #6C5CE7 (Electric Purple) + #00D2D3 (Cyan) on #0F0F1A (Dark Navy)\n"
        f"- Typography: Inter Bold 48px headlines, Inter Regular 16px body\n"
        f"- Dark mode native, WCAG 2.1 AA accessible"
    )

# ---------------------------------------------------------------------------
# Rich display layer (visual presentation)
# ---------------------------------------------------------------------------

console = Console()

BANNER = r"""
     █████╗  ██████╗ ███████╗███╗   ██╗████████╗ ██████╗ ███████╗
    ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝██╔═══██╗██╔════╝
    ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║   ██║   ██║███████╗
    ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║   ██║   ██║╚════██║
    ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   ╚██████╔╝███████║
    ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝    ╚═════╝ ╚══════╝
"""

PHASE_DESCRIPTIONS = {
    "Discovery":  "Searching agent marketplace for candidates...",
    "Evaluation": "Scoring candidates on skills, rating & experience...",
    "Hiring":     "Selecting best agent within budget...",
    "Execution":  "Sending task via A2A protocol...",
    "Payment":    "Processing x402 USDC micropayment...",
    "Complete":   "Task completed successfully!",
}

PHASE_NUMBERS = {
    "Discovery": 1, "Evaluation": 2, "Hiring": 3,
    "Execution": 4, "Payment": 5, "Complete": 6,
}


def _delay(seconds: float, fast: bool) -> None:
    """Sleep unless in fast mode."""
    if not fast:
        time.sleep(seconds)


def display_banner() -> None:
    """Display the HireWire ASCII banner."""
    banner_text = Text(BANNER, style="bold cyan")
    console.print(Panel(
        Align.center(banner_text),
        subtitle="[dim]Multi-Agent Operating System[/dim]",
        border_style="cyan",
        padding=(0, 2),
    ))
    console.print()


def display_task_brief(config: DemoConfig) -> None:
    """Display the incoming task briefing."""
    task_panel = Panel(
        f"[bold white]{config.task_description}[/]\n\n"
        f"[dim]Required skills:[/] [cyan]{', '.join(config.required_skills)}[/]\n"
        f"[dim]Budget:[/] [green]${config.budget:.2f} USDC[/]\n"
        f"[dim]Protocol:[/] [yellow]A2A + x402[/]",
        title="[bold yellow]Incoming Task[/]",
        border_style="yellow",
        padding=(1, 2),
    )
    console.print(task_panel)
    console.print()


def display_phase(name: str) -> None:
    """Display a phase header."""
    num = PHASE_NUMBERS.get(name, "")
    desc = PHASE_DESCRIPTIONS.get(name, "")
    console.print(Rule(f"[bold cyan]{num}[/] [bold]{name}[/]", style="cyan"))
    if desc:
        console.print(f"  [dim italic]{desc}[/]")
    console.print()


def display_discovery(candidates: list[MockExternalAgent]) -> None:
    """Display discovered agents in a table."""
    table = Table(
        title="Marketplace Agents Found",
        box=box.ROUNDED,
        border_style="cyan",
        show_lines=True,
        padding=(0, 1),
    )
    table.add_column("Agent", style="bold white", min_width=18)
    table.add_column("Skills", style="cyan", min_width=30)
    table.add_column("Price", justify="right", style="green")
    table.add_column("Rating", justify="center", style="yellow")
    table.add_column("Jobs Done", justify="right", style="dim")

    for agent in candidates:
        stars = "+" * int(agent.rating) + ("*" if agent.rating % 1 >= 0.5 else "")
        table.add_row(
            agent.name,
            ", ".join(agent.skills[:5]) + ("..." if len(agent.skills) > 5 else ""),
            agent.price_str + " USDC",
            f"{agent.rating:.1f} {stars}",
            str(agent.tasks_completed),
        )

    console.print(table)
    console.print()


def display_evaluations(evaluations: list[dict[str, Any]]) -> None:
    """Display agent evaluation scores."""
    table = Table(
        title="Agent Evaluation Scorecard",
        box=box.ROUNDED,
        border_style="magenta",
        show_lines=True,
        padding=(0, 1),
    )
    table.add_column("Agent", style="bold white", min_width=18)
    table.add_column("Skill Match", justify="center", style="cyan")
    table.add_column("Rating", justify="center", style="yellow")
    table.add_column("Experience", justify="center", style="blue")
    table.add_column("Composite", justify="center", style="bold green")
    table.add_column("Status", justify="center")

    sorted_evals = sorted(evaluations, key=lambda e: e["composite_score"], reverse=True)

    for i, ev in enumerate(sorted_evals):
        skill_bar = _score_bar(ev["skill_match"])
        rating_bar = _score_bar(ev["rating_score"])
        exp_bar = _score_bar(ev["experience_score"])
        composite_bar = _score_bar(ev["composite_score"])

        status = "[bold green]BEST[/]" if i == 0 else (
            "[yellow]OK[/]" if ev["approved"] else "[red]REJECT[/]"
        )

        table.add_row(
            ev["agent_name"],
            f"{ev['skill_match']:.0%} {skill_bar}",
            f"{ev['rating_score']:.0%} {rating_bar}",
            f"{ev['experience_score']:.0%} {exp_bar}",
            f"{ev['composite_score']:.0%} {composite_bar}",
            status,
        )

    console.print(table)
    console.print()

    best = sorted_evals[0]
    console.print(Panel(
        f"[bold]Selected:[/] [cyan]{best['agent_name']}[/]\n"
        f"[dim]Matched skills:[/] {', '.join(best['matched_skills'])}\n"
        f"[dim]Reasoning:[/] Highest composite score ({best['composite_score']:.0%}) "
        f"combining {best['skill_match']:.0%} skill match, "
        f"{best['rating_score']:.0%} rating, "
        f"{best['experience_score']:.0%} experience",
        title="[bold green]Hiring Decision[/]",
        border_style="green",
        padding=(0, 2),
    ))
    console.print()


def display_execution(exec_result: dict[str, Any]) -> None:
    """Display task execution result."""
    console.print(Panel(
        f"[bold]Task ID:[/] [cyan]{exec_result['task_id']}[/]\n"
        f"[bold]Agent:[/] {exec_result['agent']}\n"
        f"[bold]Protocol:[/] {exec_result['protocol']}\n"
        f"[bold]Status:[/] [green]{exec_result['status']}[/]\n\n"
        f"[dim]--- Deliverable Preview ---[/]\n"
        f"{exec_result['deliverable']}",
        title="[bold blue]A2A Task Execution[/]",
        border_style="blue",
        padding=(1, 2),
    ))
    console.print()


def display_payment(payment: dict[str, Any], budget_allocated: float, budget_remaining: float) -> None:
    """Display payment confirmation with budget tracking."""
    budget_spent = budget_allocated - budget_remaining
    pct_used = (budget_spent / budget_allocated * 100) if budget_allocated > 0 else 0

    console.print(Panel(
        f"[bold]Transaction:[/] [cyan]{payment['tx_id']}[/]\n"
        f"[bold]From:[/] {payment['from']}  [bold]To:[/] {payment['to']}\n"
        f"[bold]Amount:[/] [green]${payment['amount_usdc']:.2f} USDC[/]\n"
        f"[bold]Network:[/] {payment['network']}\n"
        f"[bold]Protocol:[/] {payment['protocol']}\n"
        f"[bold]Status:[/] [green]{payment['status']}[/]\n\n"
        f"[dim]--- Budget Tracker ---[/]\n"
        f"  Allocated: [green]${budget_allocated:.2f}[/]  "
        f"Spent: [yellow]${budget_spent:.2f}[/]  "
        f"Remaining: [{'green' if budget_remaining > 1 else 'red'}]"
        f"${budget_remaining:.2f}[/]  "
        f"({pct_used:.1f}% used)",
        title="[bold green]x402 Payment Confirmed[/]",
        border_style="green",
        padding=(1, 2),
    ))
    console.print()


def display_summary(result: DemoResult) -> None:
    """Display the final summary table."""
    table = Table(
        title="Demo Summary",
        box=box.DOUBLE_EDGE,
        border_style="bold cyan",
        show_lines=True,
        padding=(0, 2),
    )
    table.add_column("Metric", style="bold white", min_width=20)
    table.add_column("Value", style="cyan", min_width=40)

    table.add_row("Task", result.task[:80] + ("..." if len(result.task) > 80 else ""))
    table.add_row("Status", f"[bold green]{result.status}[/]")
    table.add_row("Agent Hired", f"[bold]{result.agent_hired}[/]")
    table.add_row("Capability Score", f"[yellow]{result.capability_score:.0%}[/]")
    table.add_row("Price Paid", f"[green]${result.price_paid:.2f} USDC[/]")
    table.add_row("Budget Allocated", f"${result.budget_allocated:.2f} USDC")
    table.add_row("Budget Remaining", f"[green]${result.budget_remaining:.2f} USDC[/]")
    table.add_row("Time Elapsed", f"{result.total_elapsed_s:.2f}s")

    steps_text = ""
    for step in result.steps:
        icon = "[green]+[/]" if step.status == "completed" else "[red]x[/]"
        steps_text += f"  {icon} {step.name} ({step.duration_s:.3f}s)\n"
    table.add_row("Pipeline Steps", steps_text.rstrip())

    console.print(table)
    console.print()


def _score_bar(score: float, width: int = 8) -> str:
    """Create a simple text progress bar."""
    filled = int(score * width)
    empty = width - filled
    return "[green]" + "|" * filled + "[/][dim]" + "." * empty + "[/]"


# ---------------------------------------------------------------------------
# Main demo runner (combines logic + display)
# ---------------------------------------------------------------------------

def run_demo_with_display(config: DemoConfig) -> DemoResult:
    """Run the demo with rich terminal output."""
    t0 = time.monotonic()

    # Banner
    display_banner()

    # Task brief
    console.print("[bold white]CEO Agent received a new task from the user.[/]\n")
    _delay(0.8, config.fast)
    display_task_brief(config)
    _delay(1.0, config.fast)

    # Phase 1: Discovery
    display_phase("Discovery")
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Scanning marketplace...", total=100)
        for i in range(100):
            _delay(0.01, config.fast)
            progress.update(task, advance=1)

    candidates = discover_agents(DEMO_AGENTS, config.required_skills)
    console.print(f"  [green]+[/] Found [bold]{len(candidates)}[/] matching agents\n")
    _delay(0.5, config.fast)
    display_discovery(candidates)
    _delay(1.0, config.fast)

    # Phase 2: Evaluation
    display_phase("Evaluation")
    evaluations = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        for agent in candidates:
            task = progress.add_task(f"Evaluating {agent.name}...", total=None)
            _delay(0.5, config.fast)
            ev = evaluate_agent(agent, config.required_skills)
            evaluations.append(ev)
            progress.update(task, completed=True)

    display_evaluations(evaluations)
    _delay(1.0, config.fast)

    # Phase 3: Hiring
    display_phase("Hiring")
    budget_remaining = config.budget
    best = select_best_agent(evaluations, budget_remaining)
    if best is None:
        console.print("[bold red]No suitable agents found within budget.[/]")
        return DemoResult(
            task=config.task_description,
            agent_hired="none",
            capability_score=0.0,
            price_paid=0.0,
            budget_allocated=config.budget,
            budget_remaining=budget_remaining,
            total_elapsed_s=round(time.monotonic() - t0, 3),
            status="no_suitable_agents",
        )

    console.print(
        f"  [green]+[/] Hired [bold cyan]{best['agent_name']}[/] "
        f"at [green]${best['price']:.2f} USDC[/] "
        f"(score: {best['composite_score']:.0%})\n"
    )
    _delay(0.8, config.fast)

    # Phase 4: Execution
    display_phase("Execution")
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task(
            f"Sending task to {best['agent_name']} via A2A...", total=100
        )
        for i in range(100):
            _delay(0.02, config.fast)
            progress.update(task, advance=1)

    exec_result = simulate_task_execution(best["agent_name"], config.task_description)
    console.print(f"  [green]+[/] Task completed by [bold]{exec_result['agent']}[/]\n")
    _delay(0.5, config.fast)
    display_execution(exec_result)
    _delay(1.0, config.fast)

    # Phase 5: Payment
    display_phase("Payment")
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Processing x402 USDC payment on Base...", total=None)
        _delay(1.5, config.fast)
        progress.update(task, completed=True)

    payment = simulate_payment("CEO Agent", best["agent_name"],
                               best["price"], exec_result["task_id"])
    budget_remaining -= best["price"]
    display_payment(payment, config.budget, budget_remaining)
    _delay(0.8, config.fast)

    # Phase 6: Complete
    display_phase("Complete")
    total_elapsed = round(time.monotonic() - t0, 3)

    result = DemoResult(
        task=config.task_description,
        agent_hired=best["agent_name"],
        capability_score=best["composite_score"],
        price_paid=best["price"],
        budget_allocated=config.budget,
        budget_remaining=round(budget_remaining, 2),
        total_elapsed_s=total_elapsed,
        steps=[
            DemoStepResult("Discovery", "completed", 0.0,
                           {"candidates": len(candidates)}),
            DemoStepResult("Evaluation", "completed", 0.0,
                           {"agents_scored": len(evaluations)}),
            DemoStepResult("Hiring", "completed", 0.0,
                           {"selected": best["agent_name"]}),
            DemoStepResult("Execution", "completed", 0.0,
                           {"task_id": exec_result["task_id"]}),
            DemoStepResult("Payment", "completed", 0.0,
                           {"tx_id": payment["tx_id"]}),
        ],
        status="completed",
    )

    display_summary(result)

    console.print(Panel(
        "[bold green]The autonomous agent economy is live.[/]\n\n"
        "[dim]CEO agent discovered, evaluated, hired, and paid an external agent\n"
        "using A2A protocol for communication and x402 for USDC micropayments.\n"
        "All without human intervention.[/]",
        title="[bold cyan]HireWire[/]",
        border_style="cyan",
        padding=(1, 2),
    ))

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="HireWire Demo - Full agent hiring pipeline with rich output",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Skip timing delays for quick demo",
    )
    parser.add_argument(
        "--budget",
        type=float,
        default=5.0,
        help="Starting budget in USDC (default: 5.0)",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    config = DemoConfig(fast=args.fast, budget=args.budget)
    run_demo_with_display(config)


if __name__ == "__main__":
    main()
