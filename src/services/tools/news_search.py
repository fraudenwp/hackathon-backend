"""News Search Tool for LLM agent — using duckduckgo-search news API"""

import asyncio
from typing import Any

from src.services.tools.base import BaseTool
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _news_search_sync(query: str) -> str:
    """Run DuckDuckGo news search synchronously (called via asyncio.to_thread)"""
    from duckduckgo_search import DDGS

    with DDGS() as ddgs:
        results = []
        for r in ddgs.news(
            query,
            region="tr-tr",
            safesearch="moderate",
            backend="lite",
            max_results=5,
        ):
            title = r.get("title", "")
            body = r.get("body", "")
            source = r.get("source", "")
            date = r.get("date", "")
            url = r.get("url", "")
            results.append(f"{title}\n{body}\nKaynak: {source} — {date}\nURL: {url}")

        if results:
            return "\n\n---\n\n".join(results)
        return f"No news found for: {query}"


class NewsSearchTool(BaseTool):
    """News search using DuckDuckGo News"""

    @property
    def name(self) -> str:
        return "news_search"

    @property
    def description(self) -> str:
        return (
            "Search for recent news articles and headlines. "
            "Use when the user asks about current events, breaking news, "
            "or recent developments. Returns news with source and date. "
            "Write the query in the same language as the user's question."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The news search query (use the same language as the user)",
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> str:
        query = kwargs.get("query", "")
        if not query:
            return "No search query provided"

        try:
            return await asyncio.to_thread(_news_search_sync, query)
        except Exception as e:
            logger.warning("News search failed", query=query, error=str(e))
            return f"News search failed: {str(e)}"
