"""Live Azure integration tests.

These tests hit the REAL Azure OpenAI and Cosmos DB endpoints.
They require credentials in the environment (source azure-hackathon.env).

Run with:
    pytest tests/test_azure_integration.py -m azure -v

Skip in CI by default — the ``azure`` marker is not selected unless
explicitly requested.
"""

from __future__ import annotations

import os
import uuid

import pytest

# Skip the entire module if Azure credentials are not available
pytestmark = pytest.mark.azure


def _has_azure_openai() -> bool:
    return bool(
        os.environ.get("AZURE_OPENAI_ENDPOINT")
        and os.environ.get("AZURE_OPENAI_KEY")
    )


def _has_cosmos() -> bool:
    return bool(
        os.environ.get("COSMOS_ENDPOINT")
        and os.environ.get("COSMOS_KEY")
    )


# ---------------------------------------------------------------------------
# Azure OpenAI tests
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _has_azure_openai(), reason="AZURE_OPENAI_ENDPOINT not set")
class TestAzureOpenAICompletion:
    """Live connectivity and completion tests against Azure OpenAI."""

    def test_azure_openai_completion(self):
        """Verify we can get a real completion from Azure OpenAI GPT-4o."""
        from src.framework.azure_llm import AzureLLMProvider

        provider = AzureLLMProvider()
        result = provider.chat_completion(
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Reply in one sentence."},
                {"role": "user", "content": "What is 2 + 2?"},
            ],
            max_tokens=50,
            temperature=0.0,
        )

        assert result["content"], "Expected non-empty response content"
        assert "4" in result["content"], f"Expected '4' in response: {result['content']}"
        assert result["role"] == "assistant"
        assert result["usage"]["total_tokens"] > 0
        assert result["finish_reason"] in ("stop", "length")

    def test_azure_openai_check_connection(self):
        """Verify the check_connection helper reports connected."""
        from src.framework.azure_llm import AzureLLMProvider

        provider = AzureLLMProvider()
        health = provider.check_connection()
        assert health["connected"] is True
        assert "model" in health

    def test_azure_openai_generate(self):
        """Verify the convenience generate() method works."""
        from src.framework.azure_llm import AzureLLMProvider

        provider = AzureLLMProvider()
        text = provider.generate(
            "Reply with exactly one word: hello",
            temperature=0.0,
            max_tokens=10,
        )
        assert len(text) > 0

    def test_azure_chat_client_framework(self):
        """Verify AzureOpenAIChatClient works as an Agent Framework client."""
        import asyncio
        from src.agents._azure_openai_client import AzureOpenAIChatClient
        from agent_framework import ChatMessage, Role

        client = AzureOpenAIChatClient()

        async def _run():
            messages = [
                ChatMessage(role=Role.SYSTEM, text="You are a test bot. Reply with 'OK'."),
                ChatMessage(role=Role.USER, text="ping"),
            ]
            response = await client._inner_get_response(
                messages=messages, options={"max_tokens": 10, "temperature": 0.0}
            )
            return response

        response = asyncio.run(_run())
        assert len(response.messages) > 0
        assert response.messages[0].text
        assert client.usage_summary["total_tokens"] > 0


# ---------------------------------------------------------------------------
# Cosmos DB tests
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _has_cosmos(), reason="COSMOS_ENDPOINT not set")
class TestCosmosWriteRead:
    """Live write/read cycle tests against Azure Cosmos DB."""

    def test_cosmos_write_read(self):
        """Verify we can write and read back a document from Cosmos DB."""
        from src.persistence.cosmos import CosmosDBStore

        store = CosmosDBStore()
        test_id = f"test-{uuid.uuid4().hex[:8]}"

        # Write
        agent = store.save_agent({
            "id": test_id,
            "name": f"TestAgent-{test_id}",
            "description": "Integration test agent",
            "skills": ["testing"],
        })
        assert agent["id"] == test_id

        # Read back
        fetched = store.get_agent(test_id)
        assert fetched is not None
        assert fetched["id"] == test_id
        assert fetched["name"] == f"TestAgent-{test_id}"

        # Cleanup
        try:
            store._container("agents").delete_item(item=test_id, partition_key=test_id)
        except Exception:
            pass  # best-effort cleanup

    def test_cosmos_check_connection(self):
        """Verify Cosmos DB connectivity check works."""
        from src.persistence.cosmos import CosmosDBStore

        store = CosmosDBStore()
        health = store.check_connection()
        assert health["connected"] is True
        assert health["databases"] >= 0

    def test_cosmos_job_lifecycle(self):
        """Verify a complete job save/read/update cycle."""
        from src.persistence.cosmos import CosmosDBStore

        store = CosmosDBStore()
        job_id = f"job-test-{uuid.uuid4().hex[:8]}"

        # Create
        job = store.save_job({
            "id": job_id,
            "description": "Test job for integration",
            "status": "pending",
        })
        assert job["id"] == job_id

        # Read
        fetched = store.get_job(job_id)
        assert fetched is not None
        assert fetched["status"] == "pending"

        # Update
        job["status"] = "completed"
        job["result"] = "Success"
        store.save_job(job)
        updated = store.get_job(job_id)
        assert updated["status"] == "completed"

        # Cleanup
        try:
            store._container("jobs").delete_item(item=job_id, partition_key=job_id)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# End-to-end sequential workflow test
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _has_azure_openai(), reason="AZURE_OPENAI_ENDPOINT not set")
class TestE2ESequentialAzure:
    """End-to-end test: run a sequential workflow with Azure OpenAI."""

    def test_e2e_sequential_azure(self):
        """Run Research -> CEO -> Builder with real Azure completions."""
        import asyncio
        from src.agents._azure_openai_client import AzureOpenAIChatClient
        from src.workflows.sequential import create_sequential_workflow, _extract_output_text

        client = AzureOpenAIChatClient()
        workflow = create_sequential_workflow(chat_client=client)

        async def _run():
            result = await workflow.run(
                "Summarize the key benefits of agent-to-agent commerce in one paragraph."
            )
            return result

        result = asyncio.run(_run())
        outputs = result.get_outputs()
        text = _extract_output_text(outputs)

        # Verify we got real content
        assert len(text) > 50, f"Expected substantial output, got: {text[:100]}"
        assert client.usage_summary["total_tokens"] > 0

        # Verify workflow completed successfully (IDLE is the normal terminal
        # state in agent_framework — there is no explicit "completed" state)
        state = str(result.get_final_state())
        assert "FAILED" not in state and "CANCELLED" not in state, \
            f"Workflow ended in error state: {state}"
