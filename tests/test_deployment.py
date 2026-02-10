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


# ── Docker Compose tests ────────────────────────────────────────────────────


class TestDockerCompose:
    """Verify docker-compose.yml is correctly configured."""

    def test_docker_compose_exists(self):
        assert (PROJECT_DIR / "docker-compose.yml").is_file()

    def test_docker_compose_has_hirewire_service(self):
        content = (PROJECT_DIR / "docker-compose.yml").read_text()
        assert "hirewire:" in content

    def test_docker_compose_exposes_port_8000(self):
        content = (PROJECT_DIR / "docker-compose.yml").read_text()
        assert "8000:8000" in content

    def test_docker_compose_has_healthcheck(self):
        content = (PROJECT_DIR / "docker-compose.yml").read_text()
        assert "healthcheck" in content
        assert "/health" in content

    def test_docker_compose_sets_demo_mode(self):
        content = (PROJECT_DIR / "docker-compose.yml").read_text()
        assert "HIREWIRE_DEMO=1" in content

    def test_docker_compose_has_volume(self):
        content = (PROJECT_DIR / "docker-compose.yml").read_text()
        assert "hirewire-data" in content


# ── Azure Bicep deployment tests ────────────────────────────────────────────


class TestAzureBicepDeployment:
    """Verify Bicep template and deploy script are correctly configured."""

    def test_bicep_template_exists(self):
        assert (PROJECT_DIR / "deploy" / "azure" / "main.bicep").is_file()

    def test_bicep_has_container_app(self):
        content = (PROJECT_DIR / "deploy" / "azure" / "main.bicep").read_text()
        assert "Microsoft.App/containerApps" in content

    def test_bicep_has_cosmos_db(self):
        content = (PROJECT_DIR / "deploy" / "azure" / "main.bicep").read_text()
        assert "Microsoft.DocumentDB/databaseAccounts" in content

    def test_bicep_has_app_insights(self):
        content = (PROJECT_DIR / "deploy" / "azure" / "main.bicep").read_text()
        assert "Microsoft.Insights/components" in content

    def test_bicep_has_acr(self):
        content = (PROJECT_DIR / "deploy" / "azure" / "main.bicep").read_text()
        assert "Microsoft.ContainerRegistry/registries" in content

    def test_bicep_has_container_apps_env(self):
        content = (PROJECT_DIR / "deploy" / "azure" / "main.bicep").read_text()
        assert "Microsoft.App/managedEnvironments" in content

    def test_bicep_has_outputs(self):
        content = (PROJECT_DIR / "deploy" / "azure" / "main.bicep").read_text()
        assert "output appUrl" in content
        assert "output acrLoginServer" in content
        assert "output cosmosEndpoint" in content

    def test_bicep_sets_env_vars(self):
        content = (PROJECT_DIR / "deploy" / "azure" / "main.bicep").read_text()
        assert "AZURE_OPENAI_ENDPOINT" in content
        assert "COSMOS_ENDPOINT" in content
        assert "MODEL_PROVIDER" in content

    def test_bicep_configures_scaling(self):
        content = (PROJECT_DIR / "deploy" / "azure" / "main.bicep").read_text()
        assert "minReplicas" in content
        assert "maxReplicas" in content

    def test_azure_deploy_script_exists(self):
        assert (PROJECT_DIR / "deploy" / "azure" / "deploy.sh").is_file()

    def test_azure_deploy_script_is_executable(self):
        assert os.access(PROJECT_DIR / "deploy" / "azure" / "deploy.sh", os.X_OK)

    def test_azure_deploy_script_has_commands(self):
        content = (PROJECT_DIR / "deploy" / "azure" / "deploy.sh").read_text()
        assert "deploy_infra()" in content
        assert "build_image()" in content
        assert "push_image()" in content
        assert "smoke_test()" in content

    def test_azure_deploy_script_uses_bicep(self):
        content = (PROJECT_DIR / "deploy" / "azure" / "deploy.sh").read_text()
        assert "az deployment group create" in content
        assert "main.bicep" in content

    def test_azure_deploy_smoke_tests(self):
        content = (PROJECT_DIR / "deploy" / "azure" / "deploy.sh").read_text()
        assert "/health" in content
        assert "/agents" in content
        assert "/tasks" in content

    def test_azure_env_example_exists(self):
        assert (PROJECT_DIR / "deploy" / "azure" / "env.example").is_file()


# ── Architecture diagram tests ──────────────────────────────────────────────


class TestArchitectureDiagram:
    """Verify architecture diagram documentation exists."""

    def test_architecture_diagram_exists(self):
        assert (PROJECT_DIR / "docs" / "architecture-diagram.md").is_file()

    def test_architecture_diagram_has_mermaid(self):
        content = (PROJECT_DIR / "docs" / "architecture-diagram.md").read_text()
        assert "```mermaid" in content

    def test_architecture_diagram_shows_azure_services(self):
        content = (PROJECT_DIR / "docs" / "architecture-diagram.md").read_text()
        assert "Azure OpenAI" in content
        assert "Cosmos DB" in content
        assert "Container Apps" in content
        assert "Application Insights" in content

    def test_architecture_diagram_shows_agents(self):
        content = (PROJECT_DIR / "docs" / "architecture-diagram.md").read_text()
        assert "CEO Agent" in content
        assert "Builder Agent" in content
        assert "Research Agent" in content

    def test_architecture_diagram_shows_x402(self):
        content = (PROJECT_DIR / "docs" / "architecture-diagram.md").read_text()
        assert "x402" in content
        assert "USDC" in content

    def test_architecture_diagram_shows_hitl(self):
        content = (PROJECT_DIR / "docs" / "architecture-diagram.md").read_text()
        assert "HITL" in content

    def test_architecture_diagram_has_hiring_pipeline(self):
        content = (PROJECT_DIR / "docs" / "architecture-diagram.md").read_text()
        assert "Hiring Pipeline" in content

    def test_architecture_diagram_has_payment_flow(self):
        content = (PROJECT_DIR / "docs" / "architecture-diagram.md").read_text()
        assert "x402 Payment Flow" in content


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
