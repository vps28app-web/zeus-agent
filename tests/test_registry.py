"""Unit tests for the tool registry."""

from zeus.core.registry import Tool, register_tool, REGISTRY


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
