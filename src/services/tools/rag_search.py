"""RAG Document Search Tool for LLM agent"""

from typing import Any

from src.services.tools.base import BaseTool
from src.utils.logger import get_logger

logger = get_logger(__name__)


class RagSearchTool(BaseTool):
    """Search user's uploaded documents via ChromaDB"""

    @property
    def name(self) -> str:
        return "search_documents"

    @property
    def description(self) -> str:
        return "Search through the user's uploaded documents for relevant information. Use when the user asks about their documents or specific content they uploaded."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to find relevant document sections",
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> str:
        query = kwargs.get("query", "")
        user_id = kwargs.get("user_id", "")

        if not query:
            return "No search query provided"
        if not user_id:
            return "No user context available for document search"

        try:
            from src.services.rag_service import rag_service

            doc_ids = kwargs.get("doc_ids")
            results = rag_service.search(user_id=user_id, query=query, k=5, doc_ids=doc_ids)
            if not results:
                return "Kullanicinin dokumanlarinda ilgili bilgi bulunamadi."

            parts = []
            for i, r in enumerate(results, 1):
                parts.append(f"[{i}] {r['text']}")
            return "\n\n".join(parts)

        except Exception as e:
            logger.warning("RAG search tool failed", error=str(e))
            return f"Document search failed: {str(e)}"
