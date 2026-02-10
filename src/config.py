"""Configuration management for HireWire.

Supports Azure AI, Ollama (local), OpenAI, and mock backends.
Uses pydantic-settings for env var loading.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelProvider(str, Enum):
    """Supported model providers."""

    AZURE_AI = "azure_ai"
    AZURE_OPENAI = "azure_openai"
    OLLAMA = "ollama"
    OPENAI = "openai"
    MOCK = "mock"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Model provider selection
    model_provider: ModelProvider = ModelProvider.MOCK

    # Azure AI settings (Azure AI Project endpoint for agent_framework_azure_ai)
    azure_ai_project_endpoint: Optional[str] = None
    azure_ai_model_deployment: str = "gpt-4o"

    # Azure OpenAI settings (direct openai SDK — preferred for live demos)
    azure_openai_endpoint: Optional[str] = None
    azure_openai_key: Optional[str] = None
    azure_openai_deployment: str = "gpt-4o"

    # Ollama settings (local dev default)
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    # OpenAI settings (fallback)
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o"

    # Cosmos DB persistence
    cosmos_endpoint: Optional[str] = None
    cosmos_key: Optional[str] = None

    # x402 payment settings
    x402_facilitator_url: str = "https://facilitator.payai.network"
    x402_network: str = "eip155:8453"
    x402_receiver_address: str = ""
    x402_private_key: Optional[str] = None

    # Wallet
    wallet_address: str = "0x7483a9F237cf8043704D6b17DA31c12BfFF860DD"

    # Budget
    max_budget_usd: float = 100.0

    # API server
    api_host: str = "0.0.0.0"
    api_port: int = 8080

    # MCP servers
    registry_mcp_port: int = 8090
    payment_mcp_port: int = 8091


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get application settings (cached singleton)."""
    return Settings()


def _resolve_provider(settings: Settings) -> ModelProvider:
    """Determine the effective model provider.

    If MODEL_PROVIDER was not explicitly set (defaults to ``mock``) and Azure
    OpenAI env vars are present, automatically upgrade to ``azure_openai`` so
    that sourcing ``azure-hackathon.env`` is enough to switch to live GPT-4o.

    When ``MODEL_PROVIDER`` is explicitly set (e.g. in tests), we respect that
    choice and never auto-upgrade.
    """
    import os

    # If the user (or test harness) explicitly set MODEL_PROVIDER, honour it.
    if os.environ.get("MODEL_PROVIDER"):
        return settings.model_provider

    # Default (mock) + Azure creds present → auto-upgrade
    if (
        settings.model_provider == ModelProvider.MOCK
        and settings.azure_openai_endpoint
        and settings.azure_openai_key
    ):
        return ModelProvider.AZURE_OPENAI

    return settings.model_provider


def get_chat_client(settings: Settings | None = None):
    """Create a chat client based on the configured provider.

    Returns a ChatClientProtocol-compatible client.
    """
    if settings is None:
        settings = get_settings()

    provider = _resolve_provider(settings)

    if provider == ModelProvider.MOCK:
        from src.agents._mock_client import MockChatClient

        return MockChatClient()

    if provider == ModelProvider.AZURE_OPENAI:
        from src.agents._azure_openai_client import AzureOpenAIChatClient  # noqa: E501

        return AzureOpenAIChatClient(
            endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_key,
            deployment=settings.azure_openai_deployment,
        )

    if provider == ModelProvider.AZURE_AI:
        from agent_framework_azure_ai import AzureAIClient

        return AzureAIClient(
            project_endpoint=settings.azure_ai_project_endpoint,
            model_deployment_name=settings.azure_ai_model_deployment,
        )

    if provider == ModelProvider.OLLAMA:
        from agent_framework.ollama import OllamaChatClient

        return OllamaChatClient(
            host=settings.ollama_host,
            model_id=settings.ollama_model,
        )

    if provider == ModelProvider.OPENAI:
        from agent_framework.ollama import OllamaChatClient

        return OllamaChatClient(
            host="https://api.openai.com/v1",
            model_id=settings.openai_model,
        )

    raise ValueError(f"Unknown model provider: {provider}")


def get_cosmos_client(settings: Settings | None = None):
    """Return a :class:`CosmosDBStore` if Cosmos DB is configured, else *None*.

    The store is a cached singleton — safe to call repeatedly.
    """
    if settings is None:
        settings = get_settings()

    if settings.cosmos_endpoint and settings.cosmos_key:
        from src.persistence.cosmos import get_cosmos_store

        return get_cosmos_store(
            endpoint=settings.cosmos_endpoint,
            key=settings.cosmos_key,
        )
    return None
