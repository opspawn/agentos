"""Tests for agent creation and basic functionality."""

from __future__ import annotations

import pytest

from src.agents._mock_client import MockChatClient
from src.agents.ceo_agent import create_ceo_agent, CEO_INSTRUCTIONS
from src.agents.builder_agent import create_builder_agent, BUILDER_INSTRUCTIONS
from src.agents.research_agent import create_research_agent, RESEARCH_INSTRUCTIONS


@pytest.fixture
def mock_client():
    """Create a mock chat client for testing."""
    return MockChatClient()


class TestAgentCreation:
    """Test that agents are created correctly with proper configuration."""

    def test_create_ceo_agent(self, mock_client):
        agent = create_ceo_agent(chat_client=mock_client)
        assert agent.name == "CEO"
        assert agent.description is not None
        assert "CEO" in agent.description or "orchestrat" in agent.description.lower()

    def test_create_builder_agent(self, mock_client):
        agent = create_builder_agent(chat_client=mock_client)
        assert agent.name == "Builder"
        assert agent.description is not None

    def test_create_research_agent(self, mock_client):
        agent = create_research_agent(chat_client=mock_client)
        assert agent.name == "Research"
        assert agent.description is not None

    def test_ceo_has_instructions(self, mock_client):
        agent = create_ceo_agent(chat_client=mock_client)
        # Agent should have instructions in default_options
        assert agent.default_options is not None
        assert "instructions" in agent.default_options

    def test_builder_has_instructions(self, mock_client):
        agent = create_builder_agent(chat_client=mock_client)
        assert agent.default_options is not None
        assert "instructions" in agent.default_options

    def test_research_has_instructions(self, mock_client):
        agent = create_research_agent(chat_client=mock_client)
        assert agent.default_options is not None
        assert "instructions" in agent.default_options

    def test_instructions_are_set(self, mock_client):
        """Verify that each agent has meaningful instructions."""
        assert len(CEO_INSTRUCTIONS) > 100
        assert len(BUILDER_INSTRUCTIONS) > 100
        assert len(RESEARCH_INSTRUCTIONS) > 100

    @pytest.mark.asyncio
    async def test_mock_client_works(self, mock_client):
        """Verify mock client returns a response."""
        response = await mock_client.get_response("Hello, world!")
        assert response.text is not None
        assert len(response.text) > 0
        assert mock_client._call_count == 1
