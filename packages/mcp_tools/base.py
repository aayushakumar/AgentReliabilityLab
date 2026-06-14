"""
MCP Tool base classes and registry.

Tools are MCP-compatible: typed input/output schemas, registered by name,
and intercepted by the policy engine before execution.
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


class ToolSchema(BaseModel):
    """Describes the typed schema for a tool's input."""
    name: str
    description: str
    input_schema: dict[str, Any]  # JSON Schema
    output_schema: dict[str, Any] | None = None


class ToolResult(BaseModel):
    """Standardized output from any tool invocation."""
    tool_name: str
    success: bool
    output: Any = None
    error: str | None = None
    metadata: dict[str, Any] = {}


class BaseTool(ABC):
    """
    Abstract base for MCP-wrapped tool definitions.

    Subclasses must define:
    - schema: ToolSchema — the typed input/output spec
    - _execute(input_dict) -> Any — the actual implementation
    """
    schema: ClassVar[ToolSchema]

    def __init__(self, policy_engine=None):
        self._policy_engine = policy_engine

    def validate_input(self, input_dict: dict[str, Any]) -> tuple[bool, str | None]:
        """Validate input against the registered JSON Schema."""
        required = self.schema.input_schema.get("required", [])
        properties = self.schema.input_schema.get("properties", {})

        missing = [k for k in required if k not in input_dict]
        if missing:
            return False, f"Missing required fields: {missing}"

        # Type checking
        for key, val in input_dict.items():
            if key in properties:
                expected_type = properties[key].get("type")
                if expected_type == "string" and not isinstance(val, str):
                    return False, f"Field '{key}' must be a string"
                if expected_type == "integer" and not isinstance(val, int):
                    return False, f"Field '{key}' must be an integer"
                if expected_type == "number" and not isinstance(val, (int, float)):
                    return False, f"Field '{key}' must be a number"

        return True, None

    def invoke(self, input_dict: dict[str, Any]) -> ToolResult:
        """Validate input, run policy check, execute, return result."""
        valid, err = self.validate_input(input_dict)
        if not valid:
            return ToolResult(
                tool_name=self.schema.name,
                success=False,
                error=f"Schema validation failed: {err}",
            )

        try:
            output = self._execute(input_dict)
            return ToolResult(tool_name=self.schema.name, success=True, output=output)
        except Exception as e:
            logger.exception("Tool '%s' execution failed", self.schema.name)
            return ToolResult(tool_name=self.schema.name, success=False, error=str(e))

    @abstractmethod
    def _execute(self, input_dict: dict[str, Any]) -> Any:
        """Execute the tool. Must be implemented by subclasses."""
        ...

    def to_langchain_tool(self):
        """Convert to a LangChain tool for use in LangGraph agents."""
        from langchain_core.tools import StructuredTool

        tool_instance = self

        def _run(**kwargs) -> str:
            result = tool_instance.invoke(kwargs)
            if result.success:
                return json.dumps(result.output) if not isinstance(result.output, str) else result.output
            return f"Error: {result.error}"

        return StructuredTool(
            name=self.schema.name,
            description=self.schema.description,
            func=_run,
        )


class ToolRegistry:
    """Global registry of available MCP-wrapped tools."""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        name = tool.schema.name
        logger.debug("Registering tool: %s", name)
        self._tools[name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[ToolSchema]:
        return [t.schema for t in self._tools.values()]

    def get_langchain_tools(self, names: list[str] | None = None) -> list:
        tools = self._tools.values()
        if names:
            tools = [t for t in tools if t.schema.name in names]
        return [t.to_langchain_tool() for t in tools]

    def __contains__(self, name: str) -> bool:
        return name in self._tools


# Global registry
_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
