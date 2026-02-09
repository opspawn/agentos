"""Tests for workflow creation and orchestration patterns."""

from __future__ import annotations

import pytest

from agent_framework import SequentialBuilder, ConcurrentBuilder, GroupChatBuilder, HandoffBuilder

from src.agents._mock_client import MockChatClient
from src.agents.ceo_agent import create_ceo_agent
from src.agents.builder_agent import create_builder_agent
from src.agents.research_agent import create_research_agent
from src.workflows.sequential import create_sequential_workflow
from src.workflows.concurrent import create_concurrent_workflow
from src.workflows.group_chat import create_group_chat_workflow


@pytest.fixture
def mock_client():
    return MockChatClient()


@pytest.fixture
def ceo(mock_client):
    return create_ceo_agent(chat_client=mock_client)


@pytest.fixture
def builder(mock_client):
    return create_builder_agent(chat_client=mock_client)


@pytest.fixture
def research(mock_client):
    return create_research_agent(chat_client=mock_client)


class TestWorkflowCreation:
    """Test that workflows are created with correct structure."""

    def test_sequential_workflow_creates(self, mock_client):
        workflow = create_sequential_workflow(chat_client=mock_client)
        assert workflow is not None

    def test_concurrent_workflow_creates(self, mock_client):
        workflow = create_concurrent_workflow(chat_client=mock_client)
        assert workflow is not None

    def test_group_chat_workflow_creates(self, mock_client):
        workflow = create_group_chat_workflow(chat_client=mock_client)
        assert workflow is not None

    def test_sequential_has_participants(self, ceo, builder, research):
        workflow = create_sequential_workflow(
            ceo=ceo, builder=builder, research=research,
        )
        executors = workflow.get_executors_list()
        # 3 agents + 2 internal executors (InputToConversation, EndWithConversation)
        assert len(executors) == 5

    def test_concurrent_has_two_participants(self, mock_client):
        workflow = create_concurrent_workflow(chat_client=mock_client)
        executors = workflow.get_executors_list()
        assert len(executors) >= 2

    def test_group_chat_has_participants(self, ceo, builder, research):
        workflow = create_group_chat_workflow(
            ceo=ceo, builder=builder, research=research,
        )
        executors = workflow.get_executors_list()
        assert len(executors) >= 3  # 3 agents + possible orchestrator


class TestWorkflowBuilders:
    """Test that SDK builders produce valid workflow objects."""

    def test_sequential_builder(self, ceo, builder):
        workflow = SequentialBuilder().participants([ceo, builder]).build()
        assert workflow is not None

    def test_concurrent_builder(self, builder, research):
        workflow = ConcurrentBuilder().participants([builder, research]).build()
        assert workflow is not None

    def test_group_chat_builder(self, ceo, builder, research):
        workflow = (
            GroupChatBuilder()
            .participants([builder, research])
            .with_orchestrator(agent=ceo)
            .with_max_rounds(5)
            .build()
        )
        assert workflow is not None

    def test_handoff_builder(self, ceo, builder, research):
        workflow = (
            HandoffBuilder()
            .participants([ceo, builder, research])
            .with_start_agent(ceo)
            .add_handoff(ceo, [builder, research])
            .add_handoff(builder, [ceo])
            .add_handoff(research, [ceo])
            .build()
        )
        assert workflow is not None
