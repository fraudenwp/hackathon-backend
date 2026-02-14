from src.services.tools.base import BaseTool, ToolRegistry, tool_registry
from src.services.tools.google_search import GoogleSearchTool
from src.services.tools.generate_visual import GenerateVisualTool
from src.services.tools.list_documents import ListDocumentsTool
from src.services.tools.news_search import NewsSearchTool
from src.services.tools.rag_search import RagSearchTool
from src.services.tools.wikipedia_search import WikipediaSearchTool

# Register all tools
tool_registry.register(GoogleSearchTool())
tool_registry.register(GenerateVisualTool())
tool_registry.register(ListDocumentsTool())
tool_registry.register(RagSearchTool())
tool_registry.register(NewsSearchTool())
tool_registry.register(WikipediaSearchTool())

__all__ = ["BaseTool", "ToolRegistry", "tool_registry"]
