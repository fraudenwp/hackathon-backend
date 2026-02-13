"""List Documents Tool for LLM agent"""

from typing import Any

from src.services.tools.base import BaseTool
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ListDocumentsTool(BaseTool):
    """List user's uploaded documents by name"""

    @property
    def name(self) -> str:
        return "list_documents"

    @property
    def description(self) -> str:
        return (
            "List the names of documents the user has uploaded. "
            "Use when the user asks what documents they have, "
            "or asks about their files. Does NOT search content."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {},
        }

    async def execute(self, **kwargs: Any) -> str:
        user_id = kwargs.get("user_id", "")
        if not user_id:
            return "No user context available"

        try:
            from src.services.rag_service import rag_service

            docs = rag_service.list_documents(user_id)
            if not docs:
                return "Henuz yuklenmiş döküman bulunmuyor."

            lines = [f"- {d['filename']}" for d in docs]
            return f"Yuklu dokumanlar ({len(docs)} adet):\n" + "\n".join(lines)

        except Exception as e:
            logger.warning("List documents failed", error=str(e))
            return f"Failed to list documents: {str(e)}"
