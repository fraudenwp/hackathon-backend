"""Web Search Tool for LLM agent — using duckduckgo-search"""

import asyncio
from typing import Any

from src.services.tools.base import BaseTool
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _search_sync(query: str) -> str:
    """Run DuckDuckGo search synchronously (called via asyncio.to_thread)"""
    from duckduckgo_search import DDGS

    with DDGS() as ddgs:
        results = []
        for r in ddgs.text(
            query,
            region="tr-tr",
            safesearch="moderate",
            backend="lite",
            max_results=5,
        ):
            title = r.get("title", "")
            body = r.get("body", "")
            href = r.get("href", "")
            results.append(f"{title}\n{body}\nURL: {href}")

        if results:
            return "\n\n---\n\n".join(results)
        return f"No results found for: {query}"


class GoogleSearchTool(BaseTool):
    """Web search using DuckDuckGo"""

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return (
            "Search the web for current and accurate information. "
            "MUST use for uncertain topics — never guess! "
            "Auto-fallback to web when documents yield no results. "
            "Use for questions requiring current data (statistics, recent findings). "
            "Write query in user's language."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query (use the same language as the user)",
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> str:
        query = kwargs.get("query", "")
        if not query:
            return "No search query provided"

        try:
            return await asyncio.to_thread(_search_sync, query)
        except Exception as e:
            logger.warning("Web search failed", query=query, error=str(e))
            return f"Search failed: {str(e)}"
