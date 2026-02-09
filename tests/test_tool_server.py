"""Tests for MCP Tool Server.

Covers:
- ToolDefinition model
- ToolRegistry: registration, discovery, search, listing, unregister
- ToolExecutor: invocation, validation, timeout, error handling
- Tool composition (chaining tools into workflows)
- Azure tool stubs (resource check, DevOps, Key Vault)
- MCP server endpoints (tools_list, tools_search, tools_invoke, etc.)
- Storage persistence for tools
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict

import pytest

from src.mcp_servers.tool_server import (
    ToolDefinition,
    ToolInvocation,
    ToolComposition,
    ToolRegistry,
    ToolExecutor,
    tool_registry,
    tool_executor,
    create_tool_mcp_server,
    _azure_resource_check,
    _azure_devops_create_item,
    _azure_keyvault_get,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_tool_state():
    """Clear global tool state between tests, then re-register Azure stubs."""
    tool_registry.clear()
    tool_executor.clear()

    # Re-register the 3 Azure stubs (module-level registration is cleared)
    from src.mcp_servers.tool_server import (
        _AZURE_RESOURCE_CHECK,
        _AZURE_DEVOPS_CREATE_ITEM,
        _AZURE_KEYVAULT_GET,
    )
    tool_registry.register(_AZURE_RESOURCE_CHECK, _azure_resource_check)
    tool_registry.register(_AZURE_DEVOPS_CREATE_ITEM, _azure_devops_create_item)
    tool_registry.register(_AZURE_KEYVAULT_GET, _azure_keyvault_get)

    yield

    tool_registry.clear()
    tool_executor.clear()


def _make_tool(
    name: str = "test_tool",
    description: str = "A test tool",
    required: list[str] | None = None,
    properties: dict | None = None,
    provider: str = "test",
    tags: list[str] | None = None,
) -> ToolDefinition:
    """Helper to create a ToolDefinition quickly."""
    if properties is None:
        properties = {"message": {"type": "string", "description": "A message"}}
    if required is None:
        required = ["message"]
    return ToolDefinition(
        name=name,
        description=description,
        input_schema={
            "type": "object",
            "properties": properties,
            "required": required,
        },
        provider=provider,
        tags=tags if tags is not None else [],
    )


# ---------------------------------------------------------------------------
# ToolDefinition model tests
# ---------------------------------------------------------------------------

class TestToolDefinition:
    """Tests for the ToolDefinition dataclass."""

    def test_create_basic(self):
        td = ToolDefinition(
            name="my_tool",
            description="Does things",
            input_schema={"type": "object", "properties": {}},
        )
        assert td.name == "my_tool"
        assert td.description == "Does things"
        assert td.provider == "local"
        assert td.version == "1.0.0"
        assert td.tags == []

    def test_to_dict(self):
        td = _make_tool()
        d = asdict(td)
        assert d["name"] == "test_tool"
        assert "input_schema" in d
        assert d["provider"] == "test"

    def test_custom_fields(self):
        td = ToolDefinition(
            name="custom",
            description="Custom tool",
            input_schema={},
            output_schema={"type": "object"},
            provider="azure",
            version="2.0.0",
            tags=["cloud", "infra"],
        )
        assert td.provider == "azure"
        assert td.version == "2.0.0"
        assert td.tags == ["cloud", "infra"]
        assert td.output_schema == {"type": "object"}


# ---------------------------------------------------------------------------
# ToolRegistry tests
# ---------------------------------------------------------------------------

class TestToolRegistry:
    """Tests for tool registration and discovery."""

    def test_register_and_get(self):
        reg = ToolRegistry()
        reg._persist = False
        td = _make_tool(name="reg_test")
        reg.register(td)
        assert reg.get("reg_test") is not None
        assert reg.get("reg_test").description == "A test tool"

    def test_get_missing(self):
        reg = ToolRegistry()
        reg._persist = False
        assert reg.get("nonexistent") is None

    def test_unregister(self):
        reg = ToolRegistry()
        reg._persist = False
        reg.register(_make_tool(name="temp"))
        assert reg.unregister("temp") is True
        assert reg.get("temp") is None

    def test_unregister_missing(self):
        reg = ToolRegistry()
        reg._persist = False
        assert reg.unregister("nope") is False

    def test_list_all(self):
        reg = ToolRegistry()
        reg._persist = False
        reg.register(_make_tool(name="a"))
        reg.register(_make_tool(name="b"))
        reg.register(_make_tool(name="c"))
        assert len(reg.list_all()) == 3

    def test_search_by_name(self):
        reg = ToolRegistry()
        reg._persist = False
        reg.register(_make_tool(name="image_resize", description="Resize images"))
        reg.register(_make_tool(name="text_summarize", description="Summarize text"))
        results = reg.search("image")
        assert len(results) == 1
        assert results[0].name == "image_resize"

    def test_search_by_description(self):
        reg = ToolRegistry()
        reg._persist = False
        reg.register(_make_tool(name="tool1", description="Processes PDF documents"))
        results = reg.search("pdf")
        assert len(results) == 1

    def test_search_by_tag(self):
        reg = ToolRegistry()
        reg._persist = False
        reg.register(_make_tool(name="t1", tags=["cloud", "azure"]))
        reg.register(_make_tool(name="t2", tags=["local"]))
        results = reg.search("azure")
        assert len(results) == 1
        assert results[0].name == "t1"

    def test_search_by_tag_dedicated(self):
        reg = ToolRegistry()
        reg._persist = False
        reg.register(_make_tool(name="t1", tags=["cloud", "azure"]))
        reg.register(_make_tool(name="t2", tags=["azure", "devops"]))
        reg.register(_make_tool(name="t3", tags=["local"]))
        results = reg.search_by_tag("azure")
        assert len(results) == 2

    def test_search_no_results(self):
        reg = ToolRegistry()
        reg._persist = False
        reg.register(_make_tool(name="alpha"))
        results = reg.search("zzzzzzz")
        assert len(results) == 0

    def test_clear(self):
        reg = ToolRegistry()
        reg._persist = False
        reg.register(_make_tool(name="x"))
        reg.register_composition(ToolComposition(name="c", description="", steps=["x"]))
        reg.clear()
        assert len(reg.list_all()) == 0
        assert len(reg.list_compositions()) == 0

    def test_handler_registration(self):
        reg = ToolRegistry()
        reg._persist = False

        async def my_handler(args):
            return {"custom": True}

        reg.register(_make_tool(name="with_handler"), my_handler)
        assert reg.get_handler("with_handler") is not None
        assert reg.get_handler("missing") is None

    def test_default_handler(self):
        """Tools registered without handler get the default echo handler."""
        reg = ToolRegistry()
        reg._persist = False
        reg.register(_make_tool(name="no_handler"))
        handler = reg.get_handler("no_handler")
        assert handler is not None  # default handler assigned


# ---------------------------------------------------------------------------
# ToolComposition tests
# ---------------------------------------------------------------------------

class TestToolComposition:
    """Tests for tool composition registration and listing."""

    def test_register_composition(self):
        reg = ToolRegistry()
        reg._persist = False
        comp = ToolComposition(
            name="check_and_create",
            description="Check resource then create work item",
            steps=["azure_resource_check", "azure_devops_create_item"],
        )
        reg.register_composition(comp)
        assert reg.get_composition("check_and_create") is not None

    def test_get_missing_composition(self):
        reg = ToolRegistry()
        reg._persist = False
        assert reg.get_composition("nope") is None

    def test_list_compositions(self):
        reg = ToolRegistry()
        reg._persist = False
        reg.register_composition(ToolComposition(name="c1", description="", steps=["a"]))
        reg.register_composition(ToolComposition(name="c2", description="", steps=["b"]))
        assert len(reg.list_compositions()) == 2


# ---------------------------------------------------------------------------
# ToolExecutor tests
# ---------------------------------------------------------------------------

class TestToolExecutor:
    """Tests for tool invocation and validation."""

    @pytest.mark.asyncio
    async def test_invoke_success(self):
        inv = await tool_executor.invoke(
            "azure_resource_check",
            {"resource_type": "Microsoft.Compute/virtualMachines", "resource_name": "vm-1"},
        )
        assert inv.status == "completed"
        assert inv.output_data is not None
        assert inv.output_data["status"] == "available"
        assert inv.duration_ms is not None

    @pytest.mark.asyncio
    async def test_invoke_missing_tool(self):
        inv = await tool_executor.invoke("nonexistent_tool", {})
        assert inv.status == "failed"
        assert "not found" in inv.error

    @pytest.mark.asyncio
    async def test_invoke_missing_required_field(self):
        inv = await tool_executor.invoke(
            "azure_resource_check",
            {"resource_type": "something"},  # missing resource_name
        )
        assert inv.status == "failed"
        assert "Missing required field" in inv.error

    @pytest.mark.asyncio
    async def test_invoke_wrong_type(self):
        inv = await tool_executor.invoke(
            "azure_resource_check",
            {"resource_type": 123, "resource_name": "vm-1"},  # should be string
        )
        assert inv.status == "failed"
        assert "expected type" in inv.error

    @pytest.mark.asyncio
    async def test_invoke_timeout(self):
        """Tools that exceed timeout should fail."""
        async def slow_handler(args):
            await asyncio.sleep(10)
            return {"done": True}

        tool_registry.register(
            _make_tool(name="slow_tool", required=[], properties={}),
            slow_handler,
        )
        inv = await tool_executor.invoke("slow_tool", {}, timeout_seconds=0.05)
        assert inv.status == "failed"
        assert "timed out" in inv.error

    @pytest.mark.asyncio
    async def test_invoke_handler_error(self):
        """Tools whose handler raises should fail gracefully."""
        async def bad_handler(args):
            raise ValueError("something went wrong")

        tool_registry.register(
            _make_tool(name="bad_tool", required=[], properties={}),
            bad_handler,
        )
        inv = await tool_executor.invoke("bad_tool", {})
        assert inv.status == "failed"
        assert "something went wrong" in inv.error

    @pytest.mark.asyncio
    async def test_invocation_tracking(self):
        await tool_executor.invoke(
            "azure_resource_check",
            {"resource_type": "vm", "resource_name": "test"},
        )
        await tool_executor.invoke(
            "azure_keyvault_get",
            {"secret_name": "my-secret"},
        )
        all_invs = tool_executor.get_invocations()
        assert len(all_invs) == 2
        filtered = tool_executor.get_invocations("azure_keyvault_get")
        assert len(filtered) == 1

    @pytest.mark.asyncio
    async def test_invocation_id_increments(self):
        inv1 = await tool_executor.invoke(
            "azure_keyvault_get", {"secret_name": "a"},
        )
        inv2 = await tool_executor.invoke(
            "azure_keyvault_get", {"secret_name": "b"},
        )
        assert inv1.invocation_id != inv2.invocation_id

    @pytest.mark.asyncio
    async def test_invoke_composition_success(self):
        tool_registry.register_composition(ToolComposition(
            name="check_then_create",
            description="Check resource then create work item",
            steps=["azure_resource_check", "azure_devops_create_item"],
        ))
        results = await tool_executor.invoke_composition(
            "check_then_create",
            {"resource_type": "vm", "resource_name": "test", "title": "Fix VM"},
        )
        assert len(results) == 2
        assert all(r.status == "completed" for r in results)

    @pytest.mark.asyncio
    async def test_invoke_composition_stops_on_failure(self):
        """Composition should stop at the first failing step."""
        async def failing_handler(args):
            raise RuntimeError("boom")

        tool_registry.register(
            _make_tool(name="fail_tool", required=[], properties={}),
            failing_handler,
        )
        tool_registry.register_composition(ToolComposition(
            name="fail_chain",
            description="Will fail at step 1",
            steps=["fail_tool", "azure_keyvault_get"],
        ))
        results = await tool_executor.invoke_composition("fail_chain", {})
        assert len(results) == 1
        assert results[0].status == "failed"

    @pytest.mark.asyncio
    async def test_invoke_composition_not_found(self):
        results = await tool_executor.invoke_composition("nonexistent", {})
        assert len(results) == 1
        assert results[0].status == "failed"
        assert "not found" in results[0].error

    def test_clear_executor(self):
        tool_executor.clear()
        assert len(tool_executor.get_invocations()) == 0


# ---------------------------------------------------------------------------
# Azure tool stub tests
# ---------------------------------------------------------------------------

class TestAzureStubs:
    """Tests for pre-registered Azure tool stubs."""

    def test_azure_stubs_registered(self):
        names = [t.name for t in tool_registry.list_all()]
        assert "azure_resource_check" in names
        assert "azure_devops_create_item" in names
        assert "azure_keyvault_get" in names

    def test_azure_tools_have_azure_tag(self):
        for name in ["azure_resource_check", "azure_devops_create_item", "azure_keyvault_get"]:
            td = tool_registry.get(name)
            assert "azure" in td.tags

    def test_azure_tools_provider(self):
        for name in ["azure_resource_check", "azure_devops_create_item", "azure_keyvault_get"]:
            td = tool_registry.get(name)
            assert td.provider == "azure"

    @pytest.mark.asyncio
    async def test_azure_resource_check_handler(self):
        result = await _azure_resource_check({
            "resource_type": "Microsoft.Web/sites",
            "resource_name": "my-app",
            "region": "westus",
        })
        assert result["status"] == "available"
        assert result["region"] == "westus"
        assert result["provisioning_state"] == "Succeeded"

    @pytest.mark.asyncio
    async def test_azure_devops_create_item_handler(self):
        result = await _azure_devops_create_item({
            "title": "Implement feature X",
            "work_item_type": "User Story",
            "assigned_to": "builder-agent",
        })
        assert result["title"] == "Implement feature X"
        assert result["type"] == "User Story"
        assert result["state"] == "New"
        assert "url" in result

    @pytest.mark.asyncio
    async def test_azure_keyvault_get_handler(self):
        result = await _azure_keyvault_get({
            "secret_name": "db-connection-string",
            "vault_name": "prod-vault",
        })
        assert result["secret_name"] == "db-connection-string"
        assert result["vault_name"] == "prod-vault"
        assert result["enabled"] is True

    @pytest.mark.asyncio
    async def test_search_azure_tools(self):
        results = tool_registry.search("azure")
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_search_azure_by_tag(self):
        results = tool_registry.search_by_tag("security")
        assert len(results) == 1
        assert results[0].name == "azure_keyvault_get"


# ---------------------------------------------------------------------------
# Input validation edge cases
# ---------------------------------------------------------------------------

class TestInputValidation:
    """Tests for input schema validation edge cases."""

    @pytest.mark.asyncio
    async def test_extra_fields_allowed(self):
        """Extra fields not in schema should be allowed."""
        inv = await tool_executor.invoke(
            "azure_resource_check",
            {"resource_type": "vm", "resource_name": "test", "extra_field": "ok"},
        )
        assert inv.status == "completed"

    @pytest.mark.asyncio
    async def test_number_type_validation(self):
        async def num_handler(args):
            return {"sum": args["a"] + args["b"]}

        tool_registry.register(
            ToolDefinition(
                name="adder",
                description="Adds two numbers",
                input_schema={
                    "type": "object",
                    "properties": {
                        "a": {"type": "number"},
                        "b": {"type": "number"},
                    },
                    "required": ["a", "b"],
                },
            ),
            num_handler,
        )
        inv = await tool_executor.invoke("adder", {"a": "not_a_number", "b": 2})
        assert inv.status == "failed"
        assert "expected type" in inv.error

    @pytest.mark.asyncio
    async def test_boolean_type_validation(self):
        tool_registry.register(
            ToolDefinition(
                name="toggle",
                description="Toggle something",
                input_schema={
                    "type": "object",
                    "properties": {
                        "enabled": {"type": "boolean"},
                    },
                    "required": ["enabled"],
                },
            ),
        )
        inv = await tool_executor.invoke("toggle", {"enabled": "yes"})
        assert inv.status == "failed"
        assert "expected type" in inv.error

    @pytest.mark.asyncio
    async def test_array_type_validation(self):
        tool_registry.register(
            ToolDefinition(
                name="batch",
                description="Process batch",
                input_schema={
                    "type": "object",
                    "properties": {
                        "items": {"type": "array"},
                    },
                    "required": ["items"],
                },
            ),
        )
        # Valid
        inv = await tool_executor.invoke("batch", {"items": [1, 2, 3]})
        assert inv.status == "completed"
        # Invalid
        inv = await tool_executor.invoke("batch", {"items": "not_array"})
        assert inv.status == "failed"


# ---------------------------------------------------------------------------
# MCP Server endpoint tests
# ---------------------------------------------------------------------------

class TestMCPServerEndpoints:
    """Tests for the MCP server tool endpoints via request_handlers."""

    def _get_handlers(self):
        """Create server and return (list_handler, call_handler)."""
        from mcp.types import ListToolsRequest, CallToolRequest
        server = create_tool_mcp_server()
        return (
            server.request_handlers[ListToolsRequest],
            server.request_handlers[CallToolRequest],
        )

    @pytest.mark.asyncio
    async def test_list_tools_returns_all_endpoints(self):
        from mcp.types import ListToolsRequest
        list_handler, _ = self._get_handlers()
        result = await list_handler(ListToolsRequest(method="tools/list"))
        tools = result.root.tools
        names = [t.name for t in tools]
        assert "tools_list" in names
        assert "tools_search" in names
        assert "tools_invoke" in names
        assert "tools_register" in names
        assert "tools_invoke_composition" in names
        assert "tools_get_info" in names

    @pytest.mark.asyncio
    async def test_tools_list_via_mcp(self):
        from mcp.types import CallToolRequest, CallToolRequestParams
        _, call_handler = self._get_handlers()
        result = await call_handler(CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(name="tools_list", arguments={}),
        ))
        data = json.loads(result.root.content[0].text)
        assert isinstance(data, list)
        assert len(data) >= 3
        names = [t["name"] for t in data]
        assert "azure_resource_check" in names

    @pytest.mark.asyncio
    async def test_tools_list_by_tag_via_mcp(self):
        from mcp.types import CallToolRequest, CallToolRequestParams
        _, call_handler = self._get_handlers()
        result = await call_handler(CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(name="tools_list", arguments={"tag": "devops"}),
        ))
        data = json.loads(result.root.content[0].text)
        assert len(data) == 1
        assert data[0]["name"] == "azure_devops_create_item"

    @pytest.mark.asyncio
    async def test_tools_search_via_mcp(self):
        from mcp.types import CallToolRequest, CallToolRequestParams
        _, call_handler = self._get_handlers()
        result = await call_handler(CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(name="tools_search", arguments={"query": "keyvault"}),
        ))
        data = json.loads(result.root.content[0].text)
        assert len(data) == 1
        assert data[0]["name"] == "azure_keyvault_get"

    @pytest.mark.asyncio
    async def test_tools_invoke_via_mcp(self):
        from mcp.types import CallToolRequest, CallToolRequestParams
        _, call_handler = self._get_handlers()
        result = await call_handler(CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(
                name="tools_invoke",
                arguments={
                    "tool_name": "azure_resource_check",
                    "input": {"resource_type": "vm", "resource_name": "test-vm"},
                },
            ),
        ))
        data = json.loads(result.root.content[0].text)
        assert data["status"] == "completed"
        assert data["output_data"]["status"] == "available"

    @pytest.mark.asyncio
    async def test_tools_register_via_mcp(self):
        from mcp.types import CallToolRequest, CallToolRequestParams
        _, call_handler = self._get_handlers()
        result = await call_handler(CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(
                name="tools_register",
                arguments={
                    "name": "new_tool",
                    "description": "A brand new tool",
                    "input_schema": {"type": "object", "properties": {}},
                    "provider": "custom",
                    "tags": ["test"],
                },
            ),
        ))
        data = json.loads(result.root.content[0].text)
        assert data["registered"] is True
        assert tool_registry.get("new_tool") is not None

    @pytest.mark.asyncio
    async def test_tools_get_info_via_mcp(self):
        from mcp.types import CallToolRequest, CallToolRequestParams
        _, call_handler = self._get_handlers()
        result = await call_handler(CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(
                name="tools_get_info",
                arguments={"tool_name": "azure_keyvault_get"},
            ),
        ))
        data = json.loads(result.root.content[0].text)
        assert data["name"] == "azure_keyvault_get"
        assert data["provider"] == "azure"
        assert "input_schema" in data

    @pytest.mark.asyncio
    async def test_tools_get_info_not_found_via_mcp(self):
        from mcp.types import CallToolRequest, CallToolRequestParams
        _, call_handler = self._get_handlers()
        result = await call_handler(CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(
                name="tools_get_info",
                arguments={"tool_name": "doesnt_exist"},
            ),
        ))
        data = json.loads(result.root.content[0].text)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_tools_invoke_composition_via_mcp(self):
        tool_registry.register_composition(ToolComposition(
            name="az_pipeline",
            description="Azure pipeline",
            steps=["azure_resource_check", "azure_devops_create_item"],
        ))
        from mcp.types import CallToolRequest, CallToolRequestParams
        _, call_handler = self._get_handlers()
        result = await call_handler(CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(
                name="tools_invoke_composition",
                arguments={
                    "composition_name": "az_pipeline",
                    "input": {"resource_type": "vm", "resource_name": "test", "title": "Deploy VM"},
                },
            ),
        ))
        data = json.loads(result.root.content[0].text)
        assert isinstance(data, list)
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_unknown_tool_via_mcp(self):
        from mcp.types import CallToolRequest, CallToolRequestParams
        _, call_handler = self._get_handlers()
        result = await call_handler(CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(name="unknown_endpoint", arguments={}),
        ))
        assert "Unknown tool" in result.root.content[0].text


# ---------------------------------------------------------------------------
# Storage persistence tests
# ---------------------------------------------------------------------------

class TestToolStorage:
    """Tests for tool persistence via SQLite."""

    def test_save_and_get_tool(self):
        from src.storage import get_storage
        storage = get_storage()
        storage.save_tool(
            name="persisted_tool",
            description="A persisted tool",
            input_schema={"type": "object"},
            provider="test",
            tags=["test", "persist"],
        )
        result = storage.get_tool("persisted_tool")
        assert result is not None
        assert result["name"] == "persisted_tool"
        assert result["tags"] == ["test", "persist"]

    def test_remove_tool(self):
        from src.storage import get_storage
        storage = get_storage()
        storage.save_tool(name="temp", description="", input_schema={})
        assert storage.remove_tool("temp") is True
        assert storage.get_tool("temp") is None

    def test_list_tools(self):
        from src.storage import get_storage
        storage = get_storage()
        storage.save_tool(name="t1", description="Tool 1", input_schema={})
        storage.save_tool(name="t2", description="Tool 2", input_schema={})
        tools = storage.list_tools()
        names = [t["name"] for t in tools]
        assert "t1" in names
        assert "t2" in names

    def test_clear_tools(self):
        from src.storage import get_storage
        storage = get_storage()
        storage.save_tool(name="gone", description="", input_schema={})
        storage.clear_tools()
        assert len(storage.list_tools()) == 0
