"""Tests for deployment configuration and live endpoint verification.

Validates:
- Dockerfile configuration
- Deploy script structure
- Environment variable requirements
- Live endpoint responses (when HIREWIRE_LIVE_URL is set)
"""

import os
import subprocess
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parent.parent
LIVE_URL = os.environ.get(
    "HIREWIRE_LIVE_URL",
    "https://hirewire-api.purplecliff-500810ff.eastus.azurecontainerapps.io",
)


# ── Dockerfile tests ────────────────────────────────────────────────────────


class TestDockerfile:
    """Verify Dockerfile is correctly configured."""

    def test_dockerfile_exists(self):
        assert (PROJECT_DIR / "Dockerfile").is_file()

    def test_dockerfile_exposes_port_8000(self):
        content = (PROJECT_DIR / "Dockerfile").read_text()
        assert "EXPOSE 8000" in content

    def test_dockerfile_has_healthcheck(self):
        content = (PROJECT_DIR / "Dockerfile").read_text()
        assert "HEALTHCHECK" in content
        assert "/health" in content

    def test_dockerfile_uses_multistage_build(self):
        content = (PROJECT_DIR / "Dockerfile").read_text()
        assert "FROM python:3.12-slim AS builder" in content
        assert "FROM python:3.12-slim AS runtime" in content

    def test_dockerfile_copies_src(self):
        content = (PROJECT_DIR / "Dockerfile").read_text()
        assert "COPY src/ src/" in content

    def test_dockerfile_runs_uvicorn(self):
        content = (PROJECT_DIR / "Dockerfile").read_text()
        assert "uvicorn" in content
        assert "src.api.main:app" in content

    def test_dockerfile_sets_unbuffered(self):
        content = (PROJECT_DIR / "Dockerfile").read_text()
        assert "PYTHONUNBUFFERED=1" in content


# ── Deploy script tests ──────────────────────────────────────────────────────


class TestDeployScript:
    """Verify deploy.sh is correctly configured."""

    def test_deploy_script_exists(self):
        assert (PROJECT_DIR / "scripts" / "deploy.sh").is_file()

    def test_deploy_script_is_executable(self):
        assert os.access(PROJECT_DIR / "scripts" / "deploy.sh", os.X_OK)

    def test_deploy_script_has_build_function(self):
        content = (PROJECT_DIR / "scripts" / "deploy.sh").read_text()
        assert "build()" in content

    def test_deploy_script_has_push_function(self):
        content = (PROJECT_DIR / "scripts" / "deploy.sh").read_text()
        assert "push()" in content

    def test_deploy_script_has_deploy_function(self):
        content = (PROJECT_DIR / "scripts" / "deploy.sh").read_text()
        assert "deploy()" in content

    def test_deploy_script_uses_acr(self):
        content = (PROJECT_DIR / "scripts" / "deploy.sh").read_text()
        assert "ACR_LOGIN_SERVER" in content

    def test_deploy_script_sets_env_vars(self):
        content = (PROJECT_DIR / "scripts" / "deploy.sh").read_text()
        assert "AZURE_OPENAI_ENDPOINT" in content
        assert "COSMOS_ENDPOINT" in content
        assert "MODEL_PROVIDER=azure_ai" in content

    def test_deploy_script_sets_target_port(self):
        content = (PROJECT_DIR / "scripts" / "deploy.sh").read_text()
        assert "--target-port 8000" in content

    def test_deploy_script_sets_external_ingress(self):
        content = (PROJECT_DIR / "scripts" / "deploy.sh").read_text()
        assert "--ingress external" in content


# ── Environment configuration tests ──────────────────────────────────────────


class TestEnvironmentConfig:
    """Verify environment variable configuration."""

    def test_env_example_exists(self):
        assert (PROJECT_DIR / ".env.example").is_file()

    def test_env_example_has_required_vars(self):
        content = (PROJECT_DIR / ".env.example").read_text()
        required = [
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_KEY",
            "AZURE_OPENAI_DEPLOYMENT",
            "COSMOS_ENDPOINT",
            "COSMOS_KEY",
            "ACR_LOGIN_SERVER",
        ]
        for var in required:
            assert var in content, f"Missing {var} in .env.example"

    def test_dockerignore_excludes_env(self):
        content = (PROJECT_DIR / ".dockerignore").read_text()
        assert ".env" in content

    def test_gitignore_excludes_env(self):
        content = (PROJECT_DIR / ".gitignore").read_text()
        assert ".env" in content


# ── Live endpoint tests (require network) ────────────────────────────────────


@pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_TESTS") == "1",
    reason="SKIP_LIVE_TESTS=1",
)
class TestLiveEndpoints:
    """Test the live deployed endpoints."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        import httpx

        self.client = httpx.Client(timeout=30)
        self.base = LIVE_URL.rstrip("/")
        yield
        self.client.close()

    def test_health_returns_200(self):
        r = self.client.get(f"{self.base}/health")
        assert r.status_code == 200

    def test_health_returns_healthy(self):
        r = self.client.get(f"{self.base}/health")
        data = r.json()
        assert data["status"] == "healthy"
        assert "uptime_seconds" in data
        assert "agents_count" in data

    def test_health_azure_returns_connected(self):
        r = self.client.get(f"{self.base}/health/azure")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "healthy"
        assert data["services"]["azure_openai"]["connected"] is True
        assert data["services"]["cosmos_db"]["connected"] is True

    def test_root_serves_dashboard(self):
        r = self.client.get(f"{self.base}/")
        assert r.status_code == 200
        assert "HireWire" in r.text

    def test_agents_endpoint(self):
        r = self.client.get(f"{self.base}/agents")
        assert r.status_code == 200
        agents = r.json()
        assert isinstance(agents, list)
        assert len(agents) >= 2

    def test_tasks_endpoint(self):
        r = self.client.get(f"{self.base}/tasks")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_transactions_endpoint(self):
        r = self.client.get(f"{self.base}/transactions")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_metrics_endpoint(self):
        r = self.client.get(f"{self.base}/metrics")
        assert r.status_code == 200

    def test_docs_endpoint(self):
        r = self.client.get(f"{self.base}/docs")
        assert r.status_code == 200

    def test_submit_task(self):
        r = self.client.post(
            f"{self.base}/tasks",
            json={"description": "Test task from deployment verification", "budget": 0.01},
        )
        assert r.status_code == 201
        data = r.json()
        assert data["status"] == "pending"
        assert "task_id" in data
