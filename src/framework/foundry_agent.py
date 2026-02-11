"""Azure AI Foundry Agent Service provider for HireWire.

Wraps Azure AI Foundry's agent hosting service, allowing HireWire agents
to be hosted, discovered, and orchestrated via the Foundry Agent Service.

The provider bridges HireWire's AgentFrameworkAgent with Foundry's hosted
agent runtime, enabling:
- Agent creation and lifecycle management via Foundry
- Task execution through Foundry-hosted agents
- Agent discovery and capability querying
- Integration with Azure AI Project endpoints

Environment variables:
    AZURE_AI_PROJECT_ENDPOINT  -- Azure AI Foundry project endpoint
    AZURE_AI_MODEL_DEPLOYMENT  -- Model deployment name (default: gpt-4o)
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class FoundryAgentConfig:
    """Configuration for a Foundry-hosted agent."""

    name: str
    description: str
    instructions: str
    model_deployment: str = "gpt-4o"
    tools: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FoundryAgentInstance:
    """Represents a running agent instance in Foundry."""

    agent_id: str
    name: str
    description: str
    model_deployment: str
    status: str = "active"
    created_at: float = field(default_factory=time.time)
    thread_ids: list[str] = field(default_factory=list)
    invoke_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def agent_card(self) -> dict[str, Any]:
        """Generate an agent card for A2A/MCP discovery."""
        return {
            "id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "model": self.model_deployment,
            "status": self.status,
            "provider": "azure_ai_foundry",
            "capabilities": {
                "invoke": True,
                "threads": True,
                "foundry_hosted": True,
            },
        }


# ---------------------------------------------------------------------------
# FoundryAgentProvider
# ---------------------------------------------------------------------------


class FoundryAgentProvider:
    """Provider for Azure AI Foundry Agent Service.

    Manages agent lifecycle (create, invoke, delete) through the Foundry
    Agent Service API. Falls back to local mock execution when Foundry
    credentials are not configured.

    Usage::

        provider = FoundryAgentProvider()
        agent = provider.create_agent(FoundryAgentConfig(
            name="Builder",
            description="Code generation specialist",
            instructions="You are the Builder Agent...",
        ))
        result = await provider.invoke_agent(agent.agent_id, "Build a landing page")
    """

    def __init__(
        self,
        project_endpoint: str | None = None,
        model_deployment: str | None = None,
    ) -> None:
        self.project_endpoint = (
            project_endpoint
            or os.environ.get("AZURE_AI_PROJECT_ENDPOINT", "")
        )
        self.model_deployment = (
            model_deployment
            or os.environ.get("AZURE_AI_MODEL_DEPLOYMENT", "gpt-4o")
        )
        self._agents: dict[str, FoundryAgentInstance] = {}
        self._client: Any = None

    # ------------------------------------------------------------------
    # Client management
    # ------------------------------------------------------------------

    @property
    def client(self) -> Any:
        """Lazy-initialise the Azure AI Foundry client.

        Uses the ``azure-ai-projects`` SDK when available, otherwise
        returns None (mock mode).
        """
        if self._client is None and self.project_endpoint:
            try:
                from azure.ai.projects import AIProjectClient
                from azure.identity import DefaultAzureCredential

                self._client = AIProjectClient(
                    endpoint=self.project_endpoint,
                    credential=DefaultAzureCredential(),
                )
            except ImportError:
                logger.info(
                    "azure-ai-projects SDK not installed; "
                    "Foundry provider will run in mock mode"
                )
            except Exception as exc:
                logger.warning("Failed to init Foundry client: %s", exc)
        return self._client

    @property
    def is_available(self) -> bool:
        """Check if the Foundry Agent Service is configured."""
        return bool(self.project_endpoint)

    @property
    def is_connected(self) -> bool:
        """Check if the Foundry client is connected."""
        return self.client is not None

    # ------------------------------------------------------------------
    # Agent lifecycle
    # ------------------------------------------------------------------

    def create_agent(self, config: FoundryAgentConfig) -> FoundryAgentInstance:
        """Create a new agent in the Foundry Agent Service.

        If the Foundry SDK is available and configured, creates a real
        hosted agent. Otherwise, creates a local mock instance.

        Args:
            config: Agent configuration.

        Returns:
            A ``FoundryAgentInstance`` representing the created agent.
        """
        agent_id = f"foundry_{uuid.uuid4().hex[:12]}"

        if self.client is not None:
            try:
                foundry_agent = self.client.agents.create_agent(
                    model=config.model_deployment or self.model_deployment,
                    name=config.name,
                    instructions=config.instructions,
                )
                agent_id = getattr(foundry_agent, "id", agent_id)
                logger.info(
                    "Created Foundry agent: %s (%s)", config.name, agent_id
                )
            except Exception as exc:
                logger.warning(
                    "Foundry agent creation failed, using mock: %s", exc
                )

        instance = FoundryAgentInstance(
            agent_id=agent_id,
            name=config.name,
            description=config.description,
            model_deployment=config.model_deployment or self.model_deployment,
            metadata=config.metadata,
        )
        self._agents[agent_id] = instance
        return instance

    def get_agent(self, agent_id: str) -> FoundryAgentInstance | None:
        """Retrieve an agent instance by ID."""
        return self._agents.get(agent_id)

    def list_agents(self) -> list[FoundryAgentInstance]:
        """List all registered agent instances."""
        return list(self._agents.values())

    def delete_agent(self, agent_id: str) -> bool:
        """Delete an agent from the provider.

        If connected to Foundry, also deletes the remote agent.

        Returns:
            True if the agent was found and deleted.
        """
        instance = self._agents.pop(agent_id, None)
        if instance is None:
            return False

        if self.client is not None:
            try:
                self.client.agents.delete_agent(agent_id)
                logger.info("Deleted Foundry agent: %s", agent_id)
            except Exception as exc:
                logger.warning("Failed to delete remote agent: %s", exc)

        instance.status = "deleted"
        return True

    # ------------------------------------------------------------------
    # Agent invocation
    # ------------------------------------------------------------------

    async def invoke_agent(
        self,
        agent_id: str,
        task: str,
        thread_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Invoke an agent with a task.

        Routes through the Foundry Agent Service when connected, otherwise
        falls back to the local HireWire agent framework.

        Args:
            agent_id: ID of the agent to invoke.
            task: Task description.
            thread_id: Optional conversation thread ID.
            context: Optional additional context.

        Returns:
            Dict with agent response, metadata, and timing information.
        """
        instance = self._agents.get(agent_id)
        if instance is None:
            return {
                "status": "error",
                "error": f"Agent '{agent_id}' not found",
            }

        instance.invoke_count += 1
        t0 = time.time()

        # Try Foundry-hosted execution
        if self.client is not None:
            try:
                result = await self._invoke_via_foundry(
                    instance, task, thread_id
                )
                result["elapsed_ms"] = round((time.time() - t0) * 1000, 2)
                return result
            except Exception as exc:
                logger.warning(
                    "Foundry invocation failed, using fallback: %s", exc
                )

        # Fallback to local execution via HireWire framework
        result = await self._invoke_locally(instance, task, context)
        result["elapsed_ms"] = round((time.time() - t0) * 1000, 2)
        return result

    async def _invoke_via_foundry(
        self,
        instance: FoundryAgentInstance,
        task: str,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute task through the Foundry Agent Service API."""
        # Create or reuse thread
        if thread_id is None:
            thread = self.client.agents.create_thread()
            thread_id = thread.id
            instance.thread_ids.append(thread_id)

        # Send message
        self.client.agents.create_message(
            thread_id=thread_id,
            role="user",
            content=task,
        )

        # Run the agent
        run = self.client.agents.create_and_process_run(
            thread_id=thread_id,
            agent_id=instance.agent_id,
        )

        # Get the response
        messages = self.client.agents.list_messages(thread_id=thread_id)
        response_text = ""
        for msg in reversed(list(messages)):
            if hasattr(msg, "role") and msg.role == "assistant":
                for content_block in msg.content:
                    if hasattr(content_block, "text"):
                        response_text = content_block.text.value
                break

        return {
            "agent": instance.name,
            "agent_id": instance.agent_id,
            "response": response_text,
            "thread_id": thread_id,
            "provider": "azure_ai_foundry",
            "model": instance.model_deployment,
            "invoke_count": instance.invoke_count,
            "status": "completed",
        }

    async def _invoke_locally(
        self,
        instance: FoundryAgentInstance,
        task: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute task locally using HireWire's agent framework."""
        from src.framework.agent import AgentFrameworkAgent
        from src.config import get_chat_client

        agent = AgentFrameworkAgent(
            name=instance.name,
            description=instance.description,
            instructions=f"You are {instance.name}.",
            chat_client=get_chat_client(),
        )

        result = await agent.invoke(task, context=context)
        result["agent_id"] = instance.agent_id
        result["provider"] = "local_fallback"
        result["model"] = instance.model_deployment
        result["status"] = "completed"
        return result

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover_agents(
        self, capability: str | None = None,
    ) -> list[dict[str, Any]]:
        """Discover available agents, optionally filtered by capability.

        Args:
            capability: Optional capability keyword to filter by.

        Returns:
            List of agent cards matching the query.
        """
        cards = [inst.agent_card for inst in self._agents.values()
                 if inst.status == "active"]

        if capability:
            cap_lower = capability.lower()
            cards = [
                c for c in cards
                if cap_lower in c["name"].lower()
                or cap_lower in c["description"].lower()
            ]

        return cards

    # ------------------------------------------------------------------
    # Connectivity
    # ------------------------------------------------------------------

    def check_connection(self) -> dict[str, Any]:
        """Verify connectivity to the Foundry Agent Service.

        Returns:
            Dict with ``connected`` (bool) and optional details.
        """
        if not self.project_endpoint:
            return {
                "connected": False,
                "error": "AZURE_AI_PROJECT_ENDPOINT not configured",
            }

        if self.client is None:
            return {
                "connected": False,
                "error": "Foundry client not initialized (SDK not installed?)",
            }

        try:
            # Try listing agents as a health check
            self.client.agents.list_agents(limit=1)
            return {
                "connected": True,
                "endpoint": self.project_endpoint,
                "model": self.model_deployment,
            }
        except Exception as exc:
            return {"connected": False, "error": str(exc)}

    def get_info(self) -> dict[str, Any]:
        """Return provider information and status."""
        return {
            "provider": "azure_ai_foundry",
            "endpoint": self.project_endpoint or "not configured",
            "model_deployment": self.model_deployment,
            "is_available": self.is_available,
            "is_connected": self.is_connected,
            "agent_count": len(self._agents),
            "agents": [
                {"id": a.agent_id, "name": a.name, "status": a.status}
                for a in self._agents.values()
            ],
        }


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

_provider: FoundryAgentProvider | None = None


def get_foundry_provider(**kwargs: Any) -> FoundryAgentProvider:
    """Return a cached :class:`FoundryAgentProvider` singleton."""
    global _provider
    if _provider is None:
        _provider = FoundryAgentProvider(**kwargs)
    return _provider


def foundry_available() -> bool:
    """Return *True* if Foundry Agent Service environment variables are set."""
    return bool(os.environ.get("AZURE_AI_PROJECT_ENDPOINT"))


def create_hirewire_foundry_agents(
    provider: FoundryAgentProvider | None = None,
) -> dict[str, FoundryAgentInstance]:
    """Create the standard HireWire agent roster as Foundry-hosted agents.

    Returns a dict keyed by role name with ``FoundryAgentInstance`` objects.
    """
    if provider is None:
        provider = get_foundry_provider()

    agents: dict[str, FoundryAgentInstance] = {}

    configs = [
        FoundryAgentConfig(
            name="CEO",
            description="Orchestrator that analyzes tasks, manages budget, and delegates work",
            instructions=(
                "You are the CEO Agent in HireWire. Your role is to:\n"
                "1. Analyze incoming tasks and break them into subtasks\n"
                "2. Estimate costs and allocate budget\n"
                "3. Route work to the best agent (Builder, Research, external)\n"
                "4. Review results and ensure quality\n"
                "Be concise and structured in your analysis."
            ),
        ),
        FoundryAgentConfig(
            name="Builder",
            description="Code generation, testing, and deployment specialist",
            instructions=(
                "You are the Builder Agent in HireWire. Your role is to:\n"
                "1. Write clean, tested code based on requirements\n"
                "2. Run tests and fix issues\n"
                "3. Deploy services and manage infrastructure\n"
                "Respond with structured implementation plans and deliverables."
            ),
        ),
        FoundryAgentConfig(
            name="Research",
            description="Web search, data analysis, and competitive research specialist",
            instructions=(
                "You are the Research Agent in HireWire. Your role is to:\n"
                "1. Search for relevant information and data\n"
                "2. Analyze findings and identify patterns\n"
                "3. Produce structured reports with key insights\n"
                "Always cite sources and indicate confidence levels."
            ),
        ),
        FoundryAgentConfig(
            name="Analyst",
            description="Financial modeling, pricing analysis, and market research",
            instructions=(
                "You are the Analyst Agent in HireWire. Your role is to:\n"
                "1. Perform quantitative analysis on market data\n"
                "2. Build pricing models and competitive comparisons\n"
                "3. Generate data-driven recommendations\n"
                "Be precise with numbers and transparent about assumptions."
            ),
        ),
    ]

    for config in configs:
        instance = provider.create_agent(config)
        agents[config.name.lower()] = instance

    return agents
