"""Builder Agent - Writes code, runs tests, and deploys services.

Uses ChatAgent with tools for GitHub operations and deployment.
Supports handoff pattern for receiving work from CEO agent.
"""

from __future__ import annotations

from typing import Any

from agent_framework import ChatAgent, tool

from src.config import get_chat_client

BUILDER_INSTRUCTIONS = """You are the Builder Agent of AgentOS.

Your responsibilities:
1. **Write Code**: Implement features, fix bugs, and refactor code based on task specs.
2. **Run Tests**: Execute test suites and verify code quality.
3. **Deploy**: Push code to repositories and deploy to hosting platforms.
4. **Report**: Provide detailed summaries of what was built and any issues found.

When you receive a task:
1. Analyze the requirements
2. Write or modify the necessary code
3. Run tests to verify correctness
4. Deploy if requested
5. Report back with: files changed, tests passed/failed, deployment status

You have access to:
- GitHub operations (commit, push, create PR)
- Deployment tools (restart services, deploy to cloud)
- Code analysis tools

Always write clean, typed, well-documented code. Follow existing project patterns.
"""


@tool(name="github_commit", description="Commit changes to a GitHub repository")
async def github_commit(
    repo: str,
    branch: str,
    message: str,
    files: list[str] | None = None,
) -> dict[str, Any]:
    """Commit changes to GitHub.

    Placeholder - will integrate with real GitHub API.
    """
    return {
        "status": "committed",
        "repo": repo,
        "branch": branch,
        "message": message,
        "files_committed": files or [],
        "commit_sha": "abc123_placeholder",
    }


@tool(name="deploy_service", description="Deploy a service to the target environment")
async def deploy_service(
    service_name: str,
    target: str = "local",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Deploy a service.

    Placeholder - will integrate with real deployment systems.
    """
    return {
        "status": "deployed",
        "service": service_name,
        "target": target,
        "url": f"http://localhost:8080/{service_name}" if target == "local" else f"https://{service_name}.azurewebsites.net",
        "config": config or {},
    }


@tool(name="run_tests", description="Run test suite for a project")
async def run_tests(
    project_path: str,
    test_pattern: str = "tests/",
) -> dict[str, Any]:
    """Run project tests.

    Placeholder - will integrate with real test runner.
    """
    return {
        "status": "passed",
        "project": project_path,
        "tests_run": 0,
        "tests_passed": 0,
        "tests_failed": 0,
        "duration_ms": 0,
    }


def create_builder_agent(chat_client=None) -> ChatAgent:
    """Create and return the Builder agent.

    Args:
        chat_client: Optional ChatClientProtocol instance. If None, creates one
                     from environment config.
    """
    if chat_client is None:
        chat_client = get_chat_client()

    return ChatAgent(
        chat_client=chat_client,
        name="Builder",
        description="Code builder agent that writes, tests, and deploys software",
        instructions=BUILDER_INSTRUCTIONS,
        tools=[github_commit, deploy_service, run_tests],
    )
