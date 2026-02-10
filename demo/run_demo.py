#!/usr/bin/env python3
"""CLI entry point for HireWire demo scenarios.

Usage:
    python demo/run_demo.py landing-page   # Build a landing page
    python demo/run_demo.py research        # Parallel research
    python demo/run_demo.py all             # Run both scenarios

Environment:
    MODEL_PROVIDER  - mock (default), ollama, azure_ai, openai
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time

# Ensure project root is on sys.path when running as a script
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# -- ANSI helpers --

_BOLD = "\033[1m"
_DIM = "\033[2m"
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_RESET = "\033[0m"


def _banner() -> None:
    print(f"""
{_BOLD}{_CYAN}╔══════════════════════════════════════════════════════════╗
║                                                          ║
║     █████╗  ██████╗ ███████╗███╗   ██╗████████╗          ║
║    ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝          ║
║    ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║              ║
║    ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║              ║
║    ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   OS         ║
║    ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝              ║
║                                                          ║
║       Multi-Agent Operating System Demo                  ║
╚══════════════════════════════════════════════════════════╝{_RESET}
""")


def _summary(name: str, result: dict) -> None:
    status = result.get("status", "unknown")
    elapsed = result.get("elapsed_s", 0)
    status_lower = status.lower()
    is_ok = ("complete" in status_lower or "success" in status_lower
             or "idle" in status_lower)
    colour = _GREEN if is_ok else _YELLOW

    print(f"\n{_BOLD}--- {name} Summary ---{_RESET}")
    print(f"  Status  : {colour}{status}{_RESET}")
    print(f"  Elapsed : {elapsed:.2f}s")
    if "budget" in result:
        b = result["budget"]
        print(f"  Budget  : ${b['allocated']:.2f} allocated, "
              f"${b['spent']:.2f} spent, "
              f"${b['remaining']:.2f} remaining")
    if "token_usage" in result:
        tu = result["token_usage"]
        prompt_tok = tu.get("prompt_tokens", 0)
        completion_tok = tu.get("completion_tokens", 0)
        total_tok = tu.get("total_tokens", 0)
        cost_input = prompt_tok * 2.50 / 1_000_000
        cost_output = completion_tok * 10.00 / 1_000_000
        print(f"  Tokens  : {total_tok:,} total "
              f"({prompt_tok:,} prompt + {completion_tok:,} completion)")
        print(f"  Cost    : ${cost_input + cost_output:.4f}")
    output = result.get("output", "")
    if output:
        preview = output[:300].replace("\n", "\n    ")
        print(f"  Output  : {_DIM}{preview}{'…' if len(output) > 300 else ''}{_RESET}")


async def _run_landing_page() -> dict:
    from demo.scenario_landing_page import run_landing_page_scenario
    return await run_landing_page_scenario()


async def _run_research() -> dict:
    from demo.scenario_parallel_research import run_parallel_research_scenario
    return await run_parallel_research_scenario()


async def _run_agent_hiring() -> dict:
    from demo.scenario_agent_hiring import run_agent_hiring_scenario
    return await run_agent_hiring_scenario()


async def _run_all() -> list[dict]:
    results = []
    print(f"{_BOLD}{_YELLOW}Running all demo scenarios …{_RESET}\n")

    t0 = time.monotonic()

    result = await _run_landing_page()
    _summary("Landing Page", result)
    results.append(result)

    result = await _run_research()
    _summary("Parallel Research", result)
    results.append(result)

    result = await _run_agent_hiring()
    _summary("Agent Hiring", result)
    results.append(result)

    total = time.monotonic() - t0
    print(f"\n{_BOLD}{_GREEN}All scenarios complete in {total:.2f}s{_RESET}")
    return results


SCENARIOS = {
    "landing-page": ("Build a Landing Page", _run_landing_page),
    "research": ("Parallel Research", _run_research),
    "agent-hiring": ("Agent Hiring", _run_agent_hiring),
    "all": ("All Scenarios", None),  # handled specially
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="HireWire Demo Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Set MODEL_PROVIDER env var to switch between mock/ollama/azure_ai/openai",
    )
    parser.add_argument(
        "scenario",
        choices=list(SCENARIOS.keys()),
        help="Which demo scenario to run",
    )
    return parser


async def main(scenario: str) -> None:
    _banner()

    if scenario == "all":
        await _run_all()
    else:
        name, coro_fn = SCENARIOS[scenario]
        result = await coro_fn()
        _summary(name, result)


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(main(args.scenario))
