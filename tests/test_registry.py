"""Unit tests for the tool registry."""

from zeus.core.registry import REGISTRY, Tool, ToolRegistry, register_tool


def test_tool_registration():
    registry = REGISTRY
    tool = Tool(
        name="test_tool",
        description="A test tool",
        parameters={"type": "object", "properties": {}},
        handler=lambda: "ok",
    )
    registry.register(tool)
    assert registry.get("test_tool") == tool
    assert "test_tool" in [t.name for t in registry.list_tools()]


def test_register_tool_helper():
    register_tool(
        name="helper_tool",
        description="Helper tool",
        parameters={"type": "object", "properties": {}},
        handler=lambda: "helper ok",
    )
    tool = REGISTRY.get("helper_tool")
    assert tool is not None
    assert tool.handler() == "helper ok"


def test_registry_filter_by_tags():
    registry = ToolRegistry()
    registry.register(Tool(
        name="read_tool",
        description="Read",
        parameters={"type": "object", "properties": {}},
        handler=lambda: "read",
        tags=["file", "read"],
    ))
    registry.register(Tool(
        name="write_tool",
        description="Write",
        parameters={"type": "object", "properties": {}},
        handler=lambda: "write",
        tags=["file", "write"],
    ))
    all_schemas = registry.schemas()
    assert len(all_schemas) == 2
    read_schemas = registry.schemas(tag_allowlist={"read"})
    assert len(read_schemas) == 1
    assert read_schemas[0]["function"]["name"] == "read_tool"


def test_registry_list_tags():
    registry = ToolRegistry()
    registry.register(Tool(
        name="a",
        description="A",
        parameters={"type": "object", "properties": {}},
        handler=lambda: "a",
        tags=["x", "y"],
    ))
    assert registry.list_tags() == ["x", "y"]
