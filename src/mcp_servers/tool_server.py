"""MCP Tool Server - External tool registration and invocation.

Provides an MCP-compliant tool server that lets agents discover, register,
and invoke external tools. Supports tool composition (chaining tools into
workflows) and includes Azure tool stubs for Microsoft AI Dev Days.

Implements the MCP tools/list and tools/invoke protocol pattern.
Uses SQLite for durable persistence with in-memory caching.
"""

from __future__ import annotations

import json
import time
import asyncio
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Awaitable

from mcp.server import Server
from mcp.types import TextContent, Tool

from src.storage import get_storage


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class ToolDefinition:
    """Definition of an external tool that agents can invoke."""

    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] = field(default_factory=dict)
    provider: str = "local"
    version: str = "1.0.0"
    tags: list[str] = field(default_factory=list)
    registered_at: float = field(default_factory=time.time)


@dataclass
class ToolInvocation:
    """Record of a tool invocation."""

    invocation_id: str
    tool_name: str
    input_data: dict[str, Any]
    output_data: dict[str, Any] | None = None
    status: str = "pending"  # pending, running, completed, failed
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    error: str | None = None
    duration_ms: float | None = None


@dataclass
class ToolComposition:
    """A chain of tools executed in sequence, passing output to input."""

    name: str
    description: str
    steps: list[str]  # tool names in order
    input_mapping: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Tool Handlers (mock implementations with real interfaces)
# ---------------------------------------------------------------------------

ToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


async def _default_handler(args: dict[str, Any]) -> dict[str, Any]:
    """Default mock handler that echoes back the input."""
    return {"status": "ok", "echo": args}


async def _azure_resource_check(args: dict[str, Any]) -> dict[str, Any]:
    """Azure Resource Check - verify resource availability and status."""
    resource_type = args.get("resource_type", "unknown")
    resource_name = args.get("resource_name", "")
    subscription_id = args.get("subscription_id", "mock-sub-001")
    return {
        "resource_type": resource_type,
        "resource_name": resource_name,
        "subscription_id": subscription_id,
        "status": "available",
        "region": args.get("region", "eastus2"),
        "sku": "Standard",
        "provisioning_state": "Succeeded",
        "checked_at": time.time(),
    }


async def _azure_devops_create_item(args: dict[str, Any]) -> dict[str, Any]:
    """Azure DevOps - create a work item."""
    return {
        "id": f"WI-{int(time.time()) % 100000}",
        "title": args.get("title", "Untitled"),
        "type": args.get("work_item_type", "Task"),
        "state": "New",
        "assigned_to": args.get("assigned_to", "unassigned"),
        "project": args.get("project", "HireWire"),
        "created_at": time.time(),
        "url": f"https://dev.azure.com/mock/HireWire/_workitems/edit/{int(time.time()) % 100000}",
    }


async def _azure_keyvault_get(args: dict[str, Any]) -> dict[str, Any]:
    """Azure Key Vault - retrieve a secret (mock, returns metadata only)."""
    secret_name = args.get("secret_name", "")
    vault_name = args.get("vault_name", "hirewire-vault")
    return {
        "secret_name": secret_name,
        "vault_name": vault_name,
        "version": "latest",
        "content_type": "text/plain",
        "enabled": True,
        "created_at": time.time() - 86400,
        "updated_at": time.time(),
        "value": f"<mock-secret-{secret_name}>",
    }


# ---------------------------------------------------------------------------
# Tool Registry
# ---------------------------------------------------------------------------

class ToolRegistry:
    """Registry for discovering and managing external tools.

    Supports registration, discovery by name/tag, and listing.
    Backed by SQLite with in-memory caching.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._handlers: dict[str, ToolHandler] = {}
        self._compositions: dict[str, ToolComposition] = {}
        self._persist = True

    def _storage(self):
        """Lazy access to storage singleton."""
        return get_storage()

    def register(
        self,
        definition: ToolDefinition,
        handler: ToolHandler | None = None,
    ) -> None:
        """Register a tool definition with an optional handler."""
        self._tools[definition.name] = definition
        self._handlers[definition.name] = handler or _default_handler
        if self._persist:
            try:
                self._storage().save_tool(
                    name=definition.name,
                    description=definition.description,
                    input_schema=definition.input_schema,
                    output_schema=definition.output_schema,
                    provider=definition.provider,
                    version=definition.version,
                    tags=definition.tags,
                    registered_at=definition.registered_at,
                )
            except Exception:
                pass

    def unregister(self, name: str) -> bool:
        """Remove a tool from the registry."""
        removed = self._tools.pop(name, None) is not None
        self._handlers.pop(name, None)
        if self._persist and removed:
            try:
                self._storage().remove_tool(name)
            except Exception:
                pass
        return removed

    def get(self, name: str) -> ToolDefinition | None:
        """Get a tool definition by name."""
        return self._tools.get(name)

    def get_handler(self, name: str) -> ToolHandler | None:
        """Get the handler for a tool."""
        return self._handlers.get(name)

    def search(self, query: str) -> list[ToolDefinition]:
        """Search for tools by name, description, or tags."""
        query_lower = query.lower()
        results = []
        for tool_def in self._tools.values():
            if (
                query_lower in tool_def.name.lower()
                or query_lower in tool_def.description.lower()
                or any(query_lower in t.lower() for t in tool_def.tags)
            ):
                results.append(tool_def)
        return results

    def search_by_tag(self, tag: str) -> list[ToolDefinition]:
        """Search for tools by a specific tag."""
        tag_lower = tag.lower()
        return [
            t for t in self._tools.values()
            if any(tag_lower == tt.lower() for tt in t.tags)
        ]

    def list_all(self) -> list[ToolDefinition]:
        """List all registered tools."""
        return list(self._tools.values())

    def register_composition(self, composition: ToolComposition) -> None:
        """Register a tool composition (chain of tools)."""
        self._compositions[composition.name] = composition

    def get_composition(self, name: str) -> ToolComposition | None:
        """Get a composition by name."""
        return self._compositions.get(name)

    def list_compositions(self) -> list[ToolComposition]:
        """List all registered compositions."""
        return list(self._compositions.values())

    def clear(self) -> None:
        """Clear all tools and compositions (for testing)."""
        self._tools.clear()
        self._handlers.clear()
        self._compositions.clear()
        if self._persist:
            try:
                self._storage().clear_tools()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Tool Executor
# ---------------------------------------------------------------------------

class ToolExecutor:
    """Executes tools by name with input validation and invocation tracking."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry
        self._invocations: list[ToolInvocation] = []
        self._inv_counter: int = 0

    def _validate_input(
        self, tool_def: ToolDefinition, input_data: dict[str, Any]
    ) -> str | None:
        """Validate input against the tool's input schema.

        Returns None if valid, or an error message string.
        """
        schema = tool_def.input_schema
        required = schema.get("required", [])
        properties = schema.get("properties", {})

        # Check required fields
        for req in required:
            if req not in input_data:
                return f"Missing required field: '{req}'"

        # Check property types (basic validation)
        for key, value in input_data.items():
            if key in properties:
                expected_type = properties[key].get("type")
                if expected_type and not self._check_type(value, expected_type):
                    return f"Field '{key}' expected type '{expected_type}', got '{type(value).__name__}'"

        return None  # valid

    @staticmethod
    def _check_type(value: Any, expected: str) -> bool:
        """Check if a value matches a JSON schema type."""
        type_map = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        expected_type = type_map.get(expected)
        if expected_type is None:
            return True  # unknown type, pass through
        return isinstance(value, expected_type)

    async def invoke(
        self,
        tool_name: str,
        input_data: dict[str, Any],
        timeout_seconds: float = 30.0,
    ) -> ToolInvocation:
        """Invoke a tool by name with the given input.

        Returns a ToolInvocation record with status and output.
        """
        self._inv_counter += 1
        inv_id = f"inv_{self._inv_counter:06d}"

        invocation = ToolInvocation(
            invocation_id=inv_id,
            tool_name=tool_name,
            input_data=input_data,
            status="running",
        )

        # Look up tool
        tool_def = self._registry.get(tool_name)
        if tool_def is None:
            invocation.status = "failed"
            invocation.error = f"Tool not found: '{tool_name}'"
            invocation.completed_at = time.time()
            self._invocations.append(invocation)
            return invocation

        # Validate input
        validation_error = self._validate_input(tool_def, input_data)
        if validation_error:
            invocation.status = "failed"
            invocation.error = f"Input validation failed: {validation_error}"
            invocation.completed_at = time.time()
            self._invocations.append(invocation)
            return invocation

        # Get handler
        handler = self._registry.get_handler(tool_name)
        if handler is None:
            invocation.status = "failed"
            invocation.error = f"No handler registered for tool: '{tool_name}'"
            invocation.completed_at = time.time()
            self._invocations.append(invocation)
            return invocation

        # Execute with timeout
        start = time.time()
        try:
            result = await asyncio.wait_for(
                handler(input_data),
                timeout=timeout_seconds,
            )
            elapsed = time.time() - start
            invocation.output_data = result
            invocation.status = "completed"
            invocation.completed_at = time.time()
            invocation.duration_ms = round(elapsed * 1000, 2)
        except asyncio.TimeoutError:
            invocation.status = "failed"
            invocation.error = f"Tool execution timed out after {timeout_seconds}s"
            invocation.completed_at = time.time()
        except Exception as e:
            invocation.status = "failed"
            invocation.error = f"Tool execution error: {e}"
            invocation.completed_at = time.time()

        self._invocations.append(invocation)
        return invocation

    async def invoke_composition(
        self,
        composition_name: str,
        input_data: dict[str, Any],
        timeout_seconds: float = 30.0,
    ) -> list[ToolInvocation]:
        """Invoke a tool composition, chaining outputs to inputs."""
        composition = self._registry.get_composition(composition_name)
        if composition is None:
            self._inv_counter += 1
            inv = ToolInvocation(
                invocation_id=f"inv_{self._inv_counter:06d}",
                tool_name=composition_name,
                input_data=input_data,
                status="failed",
                error=f"Composition not found: '{composition_name}'",
                completed_at=time.time(),
            )
            self._invocations.append(inv)
            return [inv]

        results: list[ToolInvocation] = []
        current_input = dict(input_data)

        for step_name in composition.steps:
            inv = await self.invoke(step_name, current_input, timeout_seconds)
            results.append(inv)
            if inv.status != "completed":
                break  # stop chain on failure
            # Pass output as input to next step
            if inv.output_data:
                current_input = {**current_input, **inv.output_data}

        return results

    def get_invocations(
        self, tool_name: str | None = None
    ) -> list[ToolInvocation]:
        """Get invocation history, optionally filtered by tool name."""
        if tool_name is None:
            return list(self._invocations)
        return [i for i in self._invocations if i.tool_name == tool_name]

    def clear(self) -> None:
        """Clear invocation history (for testing)."""
        self._invocations.clear()
        self._inv_counter = 0


# ---------------------------------------------------------------------------
# Global instances
# ---------------------------------------------------------------------------

tool_registry = ToolRegistry()
tool_executor = ToolExecutor(tool_registry)


# ---------------------------------------------------------------------------
# Pre-register Azure tool stubs
# ---------------------------------------------------------------------------

_AZURE_RESOURCE_CHECK = ToolDefinition(
    name="azure_resource_check",
    description="Check Azure resource availability and status. Verifies provisioning state, region, and SKU.",
    input_schema={
        "type": "object",
        "properties": {
            "resource_type": {
                "type": "string",
                "description": "Azure resource type (e.g., 'Microsoft.Compute/virtualMachines')",
            },
            "resource_name": {
                "type": "string",
                "description": "Name of the resource to check",
            },
            "subscription_id": {
                "type": "string",
                "description": "Azure subscription ID (optional, uses default)",
            },
            "region": {
                "type": "string",
                "description": "Azure region (e.g., 'eastus2')",
            },
        },
        "required": ["resource_type", "resource_name"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "status": {"type": "string"},
            "provisioning_state": {"type": "string"},
            "region": {"type": "string"},
        },
    },
    provider="azure",
    tags=["azure", "resource", "infrastructure"],
)

_AZURE_DEVOPS_CREATE_ITEM = ToolDefinition(
    name="azure_devops_create_item",
    description="Create a work item in Azure DevOps. Supports Tasks, Bugs, User Stories, and Features.",
    input_schema={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Work item title",
            },
            "work_item_type": {
                "type": "string",
                "description": "Type: Task, Bug, User Story, or Feature",
            },
            "assigned_to": {
                "type": "string",
                "description": "Person or agent to assign to",
            },
            "project": {
                "type": "string",
                "description": "Azure DevOps project name",
            },
        },
        "required": ["title"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "state": {"type": "string"},
            "url": {"type": "string"},
        },
    },
    provider="azure",
    tags=["azure", "devops", "project-management"],
)

_AZURE_KEYVAULT_GET = ToolDefinition(
    name="azure_keyvault_get",
    description="Retrieve a secret from Azure Key Vault. Returns secret metadata and value.",
    input_schema={
        "type": "object",
        "properties": {
            "secret_name": {
                "type": "string",
                "description": "Name of the secret to retrieve",
            },
            "vault_name": {
                "type": "string",
                "description": "Key Vault name (optional, uses default)",
            },
        },
        "required": ["secret_name"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "secret_name": {"type": "string"},
            "value": {"type": "string"},
            "enabled": {"type": "boolean"},
        },
    },
    provider="azure",
    tags=["azure", "security", "secrets"],
)

# Register Azure stubs with their handlers
tool_registry.register(_AZURE_RESOURCE_CHECK, _azure_resource_check)
tool_registry.register(_AZURE_DEVOPS_CREATE_ITEM, _azure_devops_create_item)
tool_registry.register(_AZURE_KEYVAULT_GET, _azure_keyvault_get)


# ---------------------------------------------------------------------------
# MCP Server Factory
# ---------------------------------------------------------------------------

def create_tool_mcp_server() -> Server:
    """Create the MCP server for tool operations.

    Implements the MCP tools/list and tools/invoke protocol pattern,
    exposing tool registration, discovery, invocation, and composition.
    """
    server = Server("tool-server")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="tools_list",
                description="List all registered tools available for agents to use. Implements MCP tools/list.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "tag": {
                            "type": "string",
                            "description": "Optional tag to filter tools by (e.g., 'azure', 'security')",
                        },
                    },
                },
            ),
            Tool(
                name="tools_search",
                description="Search for tools by name, description, or tags.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query (matches name, description, tags)",
                        },
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="tools_invoke",
                description="Invoke a registered tool with given input. Implements MCP tools/invoke.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "tool_name": {
                            "type": "string",
                            "description": "Name of the tool to invoke",
                        },
                        "input": {
                            "type": "object",
                            "description": "Input arguments for the tool",
                        },
                    },
                    "required": ["tool_name", "input"],
                },
            ),
            Tool(
                name="tools_register",
                description="Register a new external tool in the tool server.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Tool name"},
                        "description": {"type": "string", "description": "What the tool does"},
                        "input_schema": {
                            "type": "object",
                            "description": "JSON Schema for tool input",
                        },
                        "provider": {"type": "string", "description": "Tool provider"},
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Tags for categorization",
                        },
                    },
                    "required": ["name", "description", "input_schema"],
                },
            ),
            Tool(
                name="tools_invoke_composition",
                description="Invoke a tool composition (chain of tools executed in sequence).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "composition_name": {
                            "type": "string",
                            "description": "Name of the composition to invoke",
                        },
                        "input": {
                            "type": "object",
                            "description": "Input arguments for the first tool in the chain",
                        },
                    },
                    "required": ["composition_name", "input"],
                },
            ),
            Tool(
                name="tools_get_info",
                description="Get detailed information about a specific tool.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "tool_name": {
                            "type": "string",
                            "description": "Name of the tool",
                        },
                    },
                    "required": ["tool_name"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        if name == "tools_list":
            tag = arguments.get("tag")
            if tag:
                tools = tool_registry.search_by_tag(tag)
            else:
                tools = tool_registry.list_all()
            result = [
                {
                    "name": t.name,
                    "description": t.description,
                    "provider": t.provider,
                    "tags": t.tags,
                    "version": t.version,
                }
                for t in tools
            ]
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        if name == "tools_search":
            query = arguments.get("query", "")
            tools = tool_registry.search(query)
            result = [
                {
                    "name": t.name,
                    "description": t.description,
                    "provider": t.provider,
                    "tags": t.tags,
                }
                for t in tools
            ]
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        if name == "tools_invoke":
            tool_name = arguments["tool_name"]
            input_data = arguments.get("input", {})
            invocation = await tool_executor.invoke(tool_name, input_data)
            return [TextContent(
                type="text",
                text=json.dumps(asdict(invocation), indent=2),
            )]

        if name == "tools_register":
            definition = ToolDefinition(
                name=arguments["name"],
                description=arguments["description"],
                input_schema=arguments.get("input_schema", {}),
                provider=arguments.get("provider", "external"),
                tags=arguments.get("tags", []),
            )
            tool_registry.register(definition)
            return [TextContent(
                type="text",
                text=json.dumps({
                    "registered": True,
                    "name": definition.name,
                    "provider": definition.provider,
                }),
            )]

        if name == "tools_invoke_composition":
            comp_name = arguments["composition_name"]
            input_data = arguments.get("input", {})
            invocations = await tool_executor.invoke_composition(comp_name, input_data)
            return [TextContent(
                type="text",
                text=json.dumps([asdict(i) for i in invocations], indent=2),
            )]

        if name == "tools_get_info":
            tool_name = arguments["tool_name"]
            tool_def = tool_registry.get(tool_name)
            if tool_def is None:
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": f"Tool not found: '{tool_name}'"}),
                )]
            return [TextContent(
                type="text",
                text=json.dumps(asdict(tool_def), indent=2),
            )]

        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    return server
