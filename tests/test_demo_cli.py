"""Tests for demo.py CLI demo runner.

Tests the core workflow orchestration logic (discovery, evaluation,
hiring, execution, payment) without testing display/rich output.
"""

from __future__ import annotations

import pytest

from demo.cli import (
    DemoConfig,
    DemoResult,
    MockExternalAgent,
    DEMO_AGENTS,
    discover_agents,
    evaluate_agent,
    select_best_agent,
    simulate_task_execution,
    simulate_payment,
    run_demo_workflow,
    build_parser,
)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

class TestDiscoverAgents:
    def test_finds_matching_agents(self):
        agents = discover_agents(DEMO_AGENTS, ["design", "ui", "landing-page"])
        names = [a.name for a in agents]
        assert "DesignStudio AI" in names
        assert "PixelForge" in names

    def test_excludes_non_matching_agents(self):
        agents = discover_agents(DEMO_AGENTS, ["design", "ui", "landing-page"])
        names = [a.name for a in agents]
        # CodeCraft doesn't have design/ui/landing-page skills
        assert "CodeCraft Agent" not in names

    def test_empty_skills_returns_nothing(self):
        agents = discover_agents(DEMO_AGENTS, [])
        assert agents == []

    def test_no_match_returns_empty(self):
        agents = discover_agents(DEMO_AGENTS, ["quantum-computing"])
        assert agents == []

    def test_case_insensitive_matching(self):
        agents = discover_agents(DEMO_AGENTS, ["DESIGN", "UI"])
        assert len(agents) >= 1

    def test_custom_agent_list(self):
        custom = [
            MockExternalAgent(
                name="TestAgent",
                description="Test",
                skills=["testing"],
                price_per_call=0.01,
                rating=5.0,
                tasks_completed=100,
            )
        ]
        agents = discover_agents(custom, ["testing"])
        assert len(agents) == 1
        assert agents[0].name == "TestAgent"


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

class TestEvaluateAgent:
    def test_full_skill_match(self):
        agent = DEMO_AGENTS[0]  # DesignStudio AI
        ev = evaluate_agent(agent, ["design", "ui", "landing-page"])
        assert ev["skill_match"] == 1.0
        assert ev["approved"] is True

    def test_partial_skill_match(self):
        agent = DEMO_AGENTS[1]  # PixelForge
        ev = evaluate_agent(agent, ["design", "ui", "landing-page"])
        assert 0.0 < ev["skill_match"] < 1.0
        assert ev["approved"] is True  # score >= 0.3

    def test_no_skill_match(self):
        agent = DEMO_AGENTS[2]  # CodeCraft Agent
        ev = evaluate_agent(agent, ["design", "ui", "landing-page"])
        assert ev["skill_match"] == 0.0
        assert ev["approved"] is False

    def test_composite_score_components(self):
        agent = DEMO_AGENTS[0]
        ev = evaluate_agent(agent, ["design"])
        # Composite = 60% skill + 25% rating + 15% experience
        assert 0.0 <= ev["composite_score"] <= 1.0
        assert "skill_match" in ev
        assert "rating_score" in ev
        assert "experience_score" in ev

    def test_empty_required_skills_gives_full_match(self):
        agent = DEMO_AGENTS[0]
        ev = evaluate_agent(agent, [])
        assert ev["skill_match"] == 1.0

    def test_matched_skills_list(self):
        agent = DEMO_AGENTS[0]
        ev = evaluate_agent(agent, ["design", "ui", "branding"])
        assert "design" in ev["matched_skills"]
        assert "ui" in ev["matched_skills"]

    def test_higher_rated_agent_scores_higher(self):
        ev1 = evaluate_agent(DEMO_AGENTS[0], ["design"])  # rating 4.9
        ev2 = evaluate_agent(DEMO_AGENTS[1], ["design"])  # rating 4.2
        # DesignStudio AI should have higher rating_score
        assert ev1["rating_score"] > ev2["rating_score"]


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

class TestSelectBestAgent:
    def test_selects_highest_composite(self):
        evaluations = [
            evaluate_agent(a, ["design", "ui", "landing-page"])
            for a in DEMO_AGENTS[:2]
        ]
        best = select_best_agent(evaluations, budget_remaining=10.0)
        assert best is not None
        assert best["agent_name"] == "DesignStudio AI"

    def test_budget_constraint(self):
        evaluations = [
            evaluate_agent(a, ["design", "ui", "landing-page"])
            for a in DEMO_AGENTS[:2]
        ]
        # Budget of $0.06 excludes DesignStudio AI ($0.15) but allows PixelForge ($0.05)
        best = select_best_agent(evaluations, budget_remaining=0.06)
        assert best is not None
        assert best["agent_name"] == "PixelForge"

    def test_no_affordable_agents(self):
        evaluations = [
            evaluate_agent(a, ["design", "ui", "landing-page"])
            for a in DEMO_AGENTS[:2]
        ]
        best = select_best_agent(evaluations, budget_remaining=0.01)
        assert best is None

    def test_no_approved_agents(self):
        # All agents with zero matching skills => not approved
        evaluations = [
            evaluate_agent(a, ["quantum-teleportation"])
            for a in DEMO_AGENTS
        ]
        best = select_best_agent(evaluations, budget_remaining=100.0)
        assert best is None


# ---------------------------------------------------------------------------
# Simulation helpers
# ---------------------------------------------------------------------------

class TestSimulateTaskExecution:
    def test_returns_completed_result(self):
        result = simulate_task_execution("TestAgent", "Build a page")
        assert result["status"] == "completed"
        assert result["agent"] == "TestAgent"
        assert "task_id" in result
        assert result["task_id"].startswith("task-")
        assert "deliverable" in result

    def test_deliverable_references_agent(self):
        result = simulate_task_execution("DesignStudio AI", "landing page")
        assert "DesignStudio AI" in result["deliverable"]


class TestSimulatePayment:
    def test_returns_confirmed_payment(self):
        payment = simulate_payment("CEO", "Designer", 0.15, "task-123")
        assert payment["status"] == "confirmed"
        assert payment["amount_usdc"] == 0.15
        assert payment["from"] == "CEO"
        assert payment["to"] == "Designer"
        assert payment["protocol"] == "x402"

    def test_tx_id_is_unique(self):
        p1 = simulate_payment("CEO", "A", 0.1, "t1")
        p2 = simulate_payment("CEO", "B", 0.2, "t2")
        assert p1["tx_id"] != p2["tx_id"]


# ---------------------------------------------------------------------------
# Full workflow
# ---------------------------------------------------------------------------

class TestRunDemoWorkflow:
    def test_full_workflow_completes(self):
        config = DemoConfig(fast=True, budget=5.0)
        result = run_demo_workflow(config)
        assert result.status == "completed"
        assert result.agent_hired == "DesignStudio AI"
        assert result.price_paid == 0.15
        assert result.budget_remaining == 4.85
        assert result.capability_score > 0.5
        assert len(result.steps) == 5

    def test_workflow_step_names(self):
        config = DemoConfig(fast=True)
        result = run_demo_workflow(config)
        step_names = [s.name for s in result.steps]
        assert step_names == ["Discovery", "Evaluation", "Hiring",
                              "Execution", "Payment"]

    def test_all_steps_completed(self):
        config = DemoConfig(fast=True)
        result = run_demo_workflow(config)
        for step in result.steps:
            assert step.status == "completed"

    def test_budget_tracking(self):
        config = DemoConfig(fast=True, budget=10.0)
        result = run_demo_workflow(config)
        assert result.budget_allocated == 10.0
        assert result.budget_remaining == 10.0 - result.price_paid

    def test_tiny_budget_selects_cheaper_agent(self):
        config = DemoConfig(
            fast=True,
            budget=0.06,
            required_skills=["design", "landing-page"],
        )
        result = run_demo_workflow(config)
        assert result.status == "completed"
        assert result.agent_hired == "PixelForge"
        assert result.price_paid == 0.05

    def test_insufficient_budget_fails(self):
        config = DemoConfig(
            fast=True,
            budget=0.01,
            required_skills=["design", "ui", "landing-page"],
        )
        result = run_demo_workflow(config)
        assert result.status == "no_suitable_agents"
        assert result.agent_hired == "none"

    def test_no_matching_skills_fails(self):
        config = DemoConfig(
            fast=True,
            required_skills=["quantum-teleportation"],
        )
        result = run_demo_workflow(config)
        # Discovery finds 0 agents, evaluation has 0 candidates
        # No candidates means no steps beyond discovery+evaluation
        assert result.agent_hired == "none"

    def test_custom_task_description(self):
        config = DemoConfig(fast=True, task_description="Custom task XYZ")
        result = run_demo_workflow(config)
        assert result.task == "Custom task XYZ"


# ---------------------------------------------------------------------------
# CLI parser
# ---------------------------------------------------------------------------

class TestBuildParser:
    def test_default_args(self):
        parser = build_parser()
        args = parser.parse_args([])
        assert args.fast is False
        assert args.budget == 5.0

    def test_fast_flag(self):
        parser = build_parser()
        args = parser.parse_args(["--fast"])
        assert args.fast is True

    def test_custom_budget(self):
        parser = build_parser()
        args = parser.parse_args(["--budget", "25.0"])
        assert args.budget == 25.0

    def test_fast_with_budget(self):
        parser = build_parser()
        args = parser.parse_args(["--fast", "--budget", "10"])
        assert args.fast is True
        assert args.budget == 10.0
