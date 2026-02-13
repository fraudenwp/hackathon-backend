"""Wikipedia Search Tool for LLM agent"""

import asyncio
from typing import Any

from src.services.tools.base import BaseTool
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _wikipedia_search_sync(query: str) -> str:
    """Run Wikipedia search synchronously (called via asyncio.to_thread)"""
    import wikipedia

    wikipedia.set_lang("tr")

    try:
        # Search for matching titles
        search_results = wikipedia.search(query, results=3)
        if not search_results:
            return f"Wikipedia'da sonuç bulunamadı: {query}"

        # Get summary of the best match
        title = search_results[0]
        try:
            summary = wikipedia.summary(title, sentences=5)
            page = wikipedia.page(title)
            return f"{page.title}\n\n{summary}\n\nURL: {page.url}"
        except wikipedia.exceptions.DisambiguationError as e:
            # Multiple possible matches — try the first option
            if e.options:
                try:
                    summary = wikipedia.summary(e.options[0], sentences=5)
                    page = wikipedia.page(e.options[0])
                    return f"{page.title}\n\n{summary}\n\nURL: {page.url}"
                except Exception:
                    pass
            options = ", ".join(e.options[:5])
            return f"Birden fazla sonuç bulundu: {options}. Daha spesifik bir arama yapın."

    except Exception as e:
        return f"Wikipedia araması başarısız: {str(e)}"


class WikipediaSearchTool(BaseTool):
    """Wikipedia search for encyclopedic information"""

    @property
    def name(self) -> str:
        return "wikipedia_search"

    @property
    def description(self) -> str:
        return (
            "Search Wikipedia for encyclopedic information. "
            "Use for history, science, geography, biographies, general knowledge topics. "
            "Returns reliable, structured information with source URL. "
            "Write the query in the same language as the user's question."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The Wikipedia search query (use the same language as the user)",
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> str:
        query = kwargs.get("query", "")
        if not query:
            return "No search query provided"

        try:
            return await asyncio.to_thread(_wikipedia_search_sync, query)
        except Exception as e:
            logger.warning("Wikipedia search failed", query=query, error=str(e))
            return f"Wikipedia search failed: {str(e)}"
