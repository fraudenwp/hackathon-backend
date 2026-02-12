"""Google Search Tool for LLM agent"""

from typing import Any

import httpx

from src.services.tools.base import BaseTool
from src.utils.logger import get_logger

logger = get_logger(__name__)


class GoogleSearchTool(BaseTool):
    """Web search using Google Custom Search API (or fallback to DuckDuckGo)"""

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "Search the web for current information. Use when the user asks about recent events, facts, or anything not in their documents."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query",
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> str:
        query = kwargs.get("query", "")
        if not query:
            return "No search query provided"

        try:
            # DuckDuckGo instant answer API (no API key needed)
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.duckduckgo.com/",
                    params={"q": query, "format": "json", "no_html": 1},
                )
                resp.raise_for_status()
                data = resp.json()

            # Extract useful info
            results = []
            if data.get("AbstractText"):
                results.append(data["AbstractText"])
            if data.get("Answer"):
                results.append(data["Answer"])
            for topic in data.get("RelatedTopics", [])[:3]:
                if isinstance(topic, dict) and topic.get("Text"):
                    results.append(topic["Text"])

            if results:
                return "\n\n".join(results)
            return f"No results found for: {query}"

        except Exception as e:
            logger.warning("Web search failed", query=query, error=str(e))
            return f"Search failed: {str(e)}"
