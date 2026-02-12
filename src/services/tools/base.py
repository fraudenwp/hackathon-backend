"""Abstract base tool and registry for LLM function calling"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """Abstract base class for agent tools.

    Subclass and implement:
      - name: tool name (used as function name in LLM)
      - description: what the tool does (shown to LLM)
      - parameters: JSON Schema dict for the function parameters
      - execute(**kwargs): run the tool and return a string result
    """

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    @abstractmethod
    def parameters(self) -> dict: ...

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """Execute the tool and return a string result for the LLM."""
        ...

    def to_openai_function(self) -> dict:
        """Convert to OpenAI function calling format"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Registry for available tools"""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def all(self) -> list[BaseTool]:
        return list(self._tools.values())

    def to_openai_functions(self) -> list[dict]:
        """Get all tools in OpenAI function calling format"""
        return [t.to_openai_function() for t in self._tools.values()]

    async def execute(self, name: str, **kwargs: Any) -> str:
        """Execute a tool by name"""
        tool = self._tools.get(name)
        if not tool:
            return f"Tool '{name}' not found"
        return await tool.execute(**kwargs)


# Global singleton
tool_registry = ToolRegistry()
