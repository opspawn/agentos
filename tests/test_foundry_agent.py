"""Tests for the Azure AI Foundry Agent Service provider.

All Foundry API calls are mocked so tests run without credentials.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("MODEL_PROVIDER", "mock")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def _foundry_env(monkeypatch):
    """Set Foundry environment variables for tests."""
    monkeypatch.setenv("AZURE_AI_PROJECT_ENDPOINT", "https://test.services.ai.azure.com/api/projects/test-project")
    monkeypatch.setenv("AZURE_AI_MODEL_DEPLOYMENT", "gpt-4o")
    # Reset singleton
    import src.framework.foundry_agent as mod
    mod._provider = None
    yield
    mod._provider = None


@pytest.fixture()
def _no_foundry_env(monkeypatch):
    """Ensure no Foundry env vars are set."""
    monkeypatch.delenv("AZURE_AI_PROJECT_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_AI_MODEL_DEPLOYMENT", raising=False)
    import src.framework.foundry_agent as mod
    mod._provider = None
    yield
    mod._provider = None


# ---------------------------------------------------------------------------
# Tests — FoundryAgentConfig
# ---------------------------------------------------------------------------


class TestFoundryAgentConfig:
    def test_config_defaults(self):
        from src.framework.foundry_agent import FoundryAgentConfig

        config = FoundryAgentConfig(
            name="Test",
            description="Test agent",
            instructions="Do things",
        )
        assert config.name == "Test"
        assert config.model_deployment == "gpt-4o"
        assert config.tools == []
        assert config.metadata == {}

    def test_config_custom_model(self):
        from src.framework.foundry_agent import FoundryAgentConfig

        config = FoundryAgentConfig(
            name="Custom",
            description="Custom model",
            instructions="...",
            model_deployment="gpt-35-turbo",
        )
        assert config.model_deployment == "gpt-35-turbo"


# ---------------------------------------------------------------------------
# Tests — FoundryAgentInstance
# ---------------------------------------------------------------------------


class TestFoundryAgentInstance:
    def test_instance_defaults(self):
        from src.framework.foundry_agent import FoundryAgentInstance

        inst = FoundryAgentInstance(
            agent_id="test_123",
            name="Builder",
            description="Code specialist",
            model_deployment="gpt-4o",
        )
        assert inst.agent_id == "test_123"
        assert inst.status == "active"
        assert inst.invoke_count == 0
        assert inst.thread_ids == []

    def test_instance_agent_card(self):
        from src.framework.foundry_agent import FoundryAgentInstance

        inst = FoundryAgentInstance(
            agent_id="agent_abc",
            name="Research",
            description="Research specialist",
            model_deployment="gpt-4o",
        )
        card = inst.agent_card
        assert card["id"] == "agent_abc"
        assert card["name"] == "Research"
        assert card["provider"] == "azure_ai_foundry"
        assert card["capabilities"]["foundry_hosted"] is True
        assert card["capabilities"]["invoke"] is True

    def test_instance_card_model(self):
        from src.framework.foundry_agent import FoundryAgentInstance

        inst = FoundryAgentInstance(
            agent_id="x", name="Y", description="Z",
            model_deployment="gpt-35-turbo",
        )
        assert inst.agent_card["model"] == "gpt-35-turbo"


# ---------------------------------------------------------------------------
# Tests — FoundryAgentProvider (without Foundry SDK)
# ---------------------------------------------------------------------------


class TestFoundryAgentProviderLocal:
    """Tests for the provider running in local/mock mode (no Foundry SDK)."""

    def test_init_from_env(self, _foundry_env):
        from src.framework.foundry_agent import FoundryAgentProvider

        provider = FoundryAgentProvider()
        assert provider.project_endpoint == "https://test.services.ai.azure.com/api/projects/test-project"
        assert provider.model_deployment == "gpt-4o"

    def test_init_explicit_args(self):
        from src.framework.foundry_agent import FoundryAgentProvider

        provider = FoundryAgentProvider(
            project_endpoint="https://custom.endpoint.com",
            model_deployment="gpt-35-turbo",
        )
        assert provider.project_endpoint == "https://custom.endpoint.com"
        assert provider.model_deployment == "gpt-35-turbo"

    def test_is_available_with_env(self, _foundry_env):
        from src.framework.foundry_agent import FoundryAgentProvider

        provider = FoundryAgentProvider()
        assert provider.is_available is True

    def test_is_available_without_env(self, _no_foundry_env):
        from src.framework.foundry_agent import FoundryAgentProvider

        provider = FoundryAgentProvider()
        assert provider.is_available is False

    def test_create_agent(self, _foundry_env):
        from src.framework.foundry_agent import FoundryAgentProvider, FoundryAgentConfig

        provider = FoundryAgentProvider()
        config = FoundryAgentConfig(
            name="TestAgent",
            description="A test agent",
            instructions="Do testing",
        )
        inst = provider.create_agent(config)
        assert inst.name == "TestAgent"
        assert inst.agent_id.startswith("foundry_")
        assert inst.status == "active"

    def test_get_agent(self, _foundry_env):
        from src.framework.foundry_agent import FoundryAgentProvider, FoundryAgentConfig

        provider = FoundryAgentProvider()
        inst = provider.create_agent(FoundryAgentConfig(
            name="Getter", description="Get test", instructions="...",
        ))
        found = provider.get_agent(inst.agent_id)
        assert found is inst

    def test_get_agent_not_found(self, _foundry_env):
        from src.framework.foundry_agent import FoundryAgentProvider

        provider = FoundryAgentProvider()
        assert provider.get_agent("nonexistent") is None

    def test_list_agents(self, _foundry_env):
        from src.framework.foundry_agent import FoundryAgentProvider, FoundryAgentConfig

        provider = FoundryAgentProvider()
        provider.create_agent(FoundryAgentConfig(name="A", description="A", instructions="A"))
        provider.create_agent(FoundryAgentConfig(name="B", description="B", instructions="B"))
        assert len(provider.list_agents()) == 2

    def test_list_agents_empty(self, _foundry_env):
        from src.framework.foundry_agent import FoundryAgentProvider

        provider = FoundryAgentProvider()
        assert provider.list_agents() == []

    def test_delete_agent(self, _foundry_env):
        from src.framework.foundry_agent import FoundryAgentProvider, FoundryAgentConfig

        provider = FoundryAgentProvider()
        inst = provider.create_agent(FoundryAgentConfig(
            name="Deletable", description="...", instructions="...",
        ))
        assert provider.delete_agent(inst.agent_id) is True
        assert provider.get_agent(inst.agent_id) is None

    def test_delete_agent_not_found(self, _foundry_env):
        from src.framework.foundry_agent import FoundryAgentProvider

        provider = FoundryAgentProvider()
        assert provider.delete_agent("nonexistent") is False

    @pytest.mark.asyncio
    async def test_invoke_agent_local(self, _foundry_env):
        from src.framework.foundry_agent import FoundryAgentProvider, FoundryAgentConfig

        provider = FoundryAgentProvider()
        inst = provider.create_agent(FoundryAgentConfig(
            name="Invoker", description="Test invoke", instructions="Invoke things",
        ))
        result = await provider.invoke_agent(inst.agent_id, "Hello world")
        assert result["agent"] == "Invoker"
        assert result["status"] == "completed"
        assert result["provider"] == "local_fallback"
        assert result["elapsed_ms"] >= 0
        assert inst.invoke_count == 1

    @pytest.mark.asyncio
    async def test_invoke_agent_not_found(self, _foundry_env):
        from src.framework.foundry_agent import FoundryAgentProvider

        provider = FoundryAgentProvider()
        result = await provider.invoke_agent("nonexistent", "task")
        assert result["status"] == "error"
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_invoke_increments_count(self, _foundry_env):
        from src.framework.foundry_agent import FoundryAgentProvider, FoundryAgentConfig

        provider = FoundryAgentProvider()
        inst = provider.create_agent(FoundryAgentConfig(
            name="Counter", description="Count invokes", instructions="...",
        ))
        await provider.invoke_agent(inst.agent_id, "task 1")
        await provider.invoke_agent(inst.agent_id, "task 2")
        assert inst.invoke_count == 2

    @pytest.mark.asyncio
    async def test_invoke_with_context(self, _foundry_env):
        from src.framework.foundry_agent import FoundryAgentProvider, FoundryAgentConfig

        provider = FoundryAgentProvider()
        inst = provider.create_agent(FoundryAgentConfig(
            name="Contextual", description="Uses context", instructions="...",
        ))
        result = await provider.invoke_agent(
            inst.agent_id, "task", context={"key": "value"}
        )
        assert result["status"] == "completed"


# ---------------------------------------------------------------------------
# Tests — Discovery
# ---------------------------------------------------------------------------


class TestFoundryDiscovery:
    def test_discover_all(self, _foundry_env):
        from src.framework.foundry_agent import FoundryAgentProvider, FoundryAgentConfig

        provider = FoundryAgentProvider()
        provider.create_agent(FoundryAgentConfig(name="Alpha", description="Alpha agent", instructions="..."))
        provider.create_agent(FoundryAgentConfig(name="Beta", description="Beta agent", instructions="..."))
        cards = provider.discover_agents()
        assert len(cards) == 2

    def test_discover_by_capability(self, _foundry_env):
        from src.framework.foundry_agent import FoundryAgentProvider, FoundryAgentConfig

        provider = FoundryAgentProvider()
        provider.create_agent(FoundryAgentConfig(name="Builder", description="Code generation", instructions="..."))
        provider.create_agent(FoundryAgentConfig(name="Research", description="Data analysis", instructions="..."))
        cards = provider.discover_agents("code")
        assert len(cards) == 1
        assert cards[0]["name"] == "Builder"

    def test_discover_no_match(self, _foundry_env):
        from src.framework.foundry_agent import FoundryAgentProvider, FoundryAgentConfig

        provider = FoundryAgentProvider()
        provider.create_agent(FoundryAgentConfig(name="Alpha", description="Does alpha", instructions="..."))
        cards = provider.discover_agents("nonexistent_capability")
        assert len(cards) == 0

    def test_discover_excludes_deleted(self, _foundry_env):
        from src.framework.foundry_agent import FoundryAgentProvider, FoundryAgentConfig

        provider = FoundryAgentProvider()
        inst = provider.create_agent(FoundryAgentConfig(name="Old", description="Old agent", instructions="..."))
        provider.delete_agent(inst.agent_id)
        cards = provider.discover_agents()
        assert len(cards) == 0

    def test_discover_case_insensitive(self, _foundry_env):
        from src.framework.foundry_agent import FoundryAgentProvider, FoundryAgentConfig

        provider = FoundryAgentProvider()
        provider.create_agent(FoundryAgentConfig(name="Builder", description="Code Generation", instructions="..."))
        cards = provider.discover_agents("CODE")
        assert len(cards) == 1


# ---------------------------------------------------------------------------
# Tests — Connectivity
# ---------------------------------------------------------------------------


class TestFoundryConnectivity:
    def test_check_connection_not_configured(self, _no_foundry_env):
        from src.framework.foundry_agent import FoundryAgentProvider

        provider = FoundryAgentProvider()
        result = provider.check_connection()
        assert result["connected"] is False
        assert "not configured" in result["error"]

    def test_check_connection_no_sdk(self, _foundry_env):
        from src.framework.foundry_agent import FoundryAgentProvider

        provider = FoundryAgentProvider()
        # Client won't initialize without the SDK
        result = provider.check_connection()
        assert result["connected"] is False

    def test_get_info(self, _foundry_env):
        from src.framework.foundry_agent import FoundryAgentProvider, FoundryAgentConfig

        provider = FoundryAgentProvider()
        provider.create_agent(FoundryAgentConfig(name="Test", description="...", instructions="..."))
        info = provider.get_info()
        assert info["provider"] == "azure_ai_foundry"
        assert info["is_available"] is True
        assert info["agent_count"] == 1
        assert len(info["agents"]) == 1

    def test_get_info_not_configured(self, _no_foundry_env):
        from src.framework.foundry_agent import FoundryAgentProvider

        provider = FoundryAgentProvider()
        info = provider.get_info()
        assert info["is_available"] is False
        assert info["agent_count"] == 0


# ---------------------------------------------------------------------------
# Tests — Module-level helpers
# ---------------------------------------------------------------------------


class TestModuleHelpers:
    def test_foundry_available_true(self, _foundry_env):
        from src.framework.foundry_agent import foundry_available
        assert foundry_available() is True

    def test_foundry_available_false(self, _no_foundry_env):
        from src.framework.foundry_agent import foundry_available
        assert foundry_available() is False

    def test_get_foundry_provider_singleton(self, _foundry_env):
        from src.framework.foundry_agent import get_foundry_provider
        p1 = get_foundry_provider()
        p2 = get_foundry_provider()
        assert p1 is p2

    def test_create_hirewire_foundry_agents(self, _foundry_env):
        from src.framework.foundry_agent import (
            FoundryAgentProvider,
            create_hirewire_foundry_agents,
        )
        provider = FoundryAgentProvider()
        agents = create_hirewire_foundry_agents(provider)
        assert len(agents) == 4
        assert "ceo" in agents
        assert "builder" in agents
        assert "research" in agents
        assert "analyst" in agents
        for name, inst in agents.items():
            assert inst.status == "active"
            assert inst.agent_id.startswith("foundry_")


# ---------------------------------------------------------------------------
# Tests — Integration with framework __init__
# ---------------------------------------------------------------------------


class TestFrameworkExports:
    def test_foundry_exports(self):
        from src.framework import (
            FoundryAgentProvider,
            FoundryAgentConfig,
            FoundryAgentInstance,
            get_foundry_provider,
            foundry_available,
            create_hirewire_foundry_agents,
        )
        assert FoundryAgentProvider is not None
        assert FoundryAgentConfig is not None
        assert FoundryAgentInstance is not None
        assert callable(get_foundry_provider)
        assert callable(foundry_available)
        assert callable(create_hirewire_foundry_agents)


# ---------------------------------------------------------------------------
# Tests — Multiple agent interactions
# ---------------------------------------------------------------------------


class TestMultiAgentFoundry:
    @pytest.mark.asyncio
    async def test_sequential_invocation(self, _foundry_env):
        """Invoke multiple agents sequentially."""
        from src.framework.foundry_agent import FoundryAgentProvider, FoundryAgentConfig

        provider = FoundryAgentProvider()
        ceo = provider.create_agent(FoundryAgentConfig(
            name="CEO", description="Orchestrator", instructions="Orchestrate",
        ))
        builder = provider.create_agent(FoundryAgentConfig(
            name="Builder", description="Code gen", instructions="Build code",
        ))

        r1 = await provider.invoke_agent(ceo.agent_id, "Analyze this task")
        r2 = await provider.invoke_agent(builder.agent_id, "Build the feature")

        assert r1["status"] == "completed"
        assert r2["status"] == "completed"
        assert r1["agent"] == "CEO"
        assert r2["agent"] == "Builder"

    @pytest.mark.asyncio
    async def test_discovery_after_creation(self, _foundry_env):
        """Create agents then discover by capability."""
        from src.framework.foundry_agent import (
            FoundryAgentProvider,
            FoundryAgentConfig,
            create_hirewire_foundry_agents,
        )

        provider = FoundryAgentProvider()
        create_hirewire_foundry_agents(provider)

        # Discover code-related agents
        code_agents = provider.discover_agents("code")
        assert any(a["name"] == "Builder" for a in code_agents)

        # Discover research-related agents
        research_agents = provider.discover_agents("research")
        assert any(a["name"] == "Research" for a in research_agents)

        # Discover budget/market agents
        analysis_agents = provider.discover_agents("pricing")
        assert any(a["name"] == "Analyst" for a in analysis_agents)

    @pytest.mark.asyncio
    async def test_create_invoke_delete_lifecycle(self, _foundry_env):
        """Full lifecycle: create -> invoke -> delete."""
        from src.framework.foundry_agent import FoundryAgentProvider, FoundryAgentConfig

        provider = FoundryAgentProvider()

        # Create
        inst = provider.create_agent(FoundryAgentConfig(
            name="Lifecycle", description="Lifecycle test", instructions="...",
        ))
        assert provider.get_agent(inst.agent_id) is not None

        # Invoke
        result = await provider.invoke_agent(inst.agent_id, "Do work")
        assert result["status"] == "completed"
        assert inst.invoke_count == 1

        # Delete
        assert provider.delete_agent(inst.agent_id) is True
        assert provider.get_agent(inst.agent_id) is None

        # Cannot invoke deleted agent
        result = await provider.invoke_agent(inst.agent_id, "Should fail")
        assert result["status"] == "error"
