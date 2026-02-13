from src.services.tools.base import BaseTool, ToolRegistry, tool_registry
from src.services.tools.google_search import GoogleSearchTool
from src.services.tools.list_documents import ListDocumentsTool
from src.services.tools.rag_search import RagSearchTool

# Register all tools
tool_registry.register(GoogleSearchTool())
tool_registry.register(ListDocumentsTool())
tool_registry.register(RagSearchTool())

__all__ = ["BaseTool", "ToolRegistry", "tool_registry"]
