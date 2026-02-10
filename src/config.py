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

    # Azure AI settings
    azure_ai_project_endpoint: Optional[str] = None
    azure_ai_model_deployment: str = "gpt-4o"

    # Ollama settings (local dev default)
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    # OpenAI settings (fallback)
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o"

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


def get_chat_client(settings: Settings | None = None):
    """Create a chat client based on the configured provider.

    Returns a ChatClientProtocol-compatible client.
    """
    if settings is None:
        settings = get_settings()

    if settings.model_provider == ModelProvider.MOCK:
        from src.agents._mock_client import MockChatClient

        return MockChatClient()

    if settings.model_provider == ModelProvider.AZURE_AI:
        from agent_framework_azure_ai import AzureAIClient

        return AzureAIClient(
            project_endpoint=settings.azure_ai_project_endpoint,
            model_deployment_name=settings.azure_ai_model_deployment,
        )

    if settings.model_provider == ModelProvider.OLLAMA:
        from agent_framework.ollama import OllamaChatClient

        return OllamaChatClient(
            host=settings.ollama_host,
            model_id=settings.ollama_model,
        )

    if settings.model_provider == ModelProvider.OPENAI:
        from agent_framework.ollama import OllamaChatClient

        return OllamaChatClient(
            host="https://api.openai.com/v1",
            model_id=settings.openai_model,
        )

    raise ValueError(f"Unknown model provider: {settings.model_provider}")
