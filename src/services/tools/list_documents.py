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
            "Show list of student's uploaded documents. "
            "ONLY use when student asks 'what files do I have?' or 'what did I upload?'. "
            "This tool does NOT search content, only lists filenames."
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

            doc_ids = kwargs.get("doc_ids")
            docs = rag_service.list_documents(user_id, doc_ids=doc_ids)
            if not docs:
                return "Henuz yuklenmiş döküman bulunmuyor."

            lines = [f"- {d['filename']}" for d in docs]
            return f"Yuklu dokumanlar ({len(docs)} adet):\n" + "\n".join(lines)

        except Exception as e:
            logger.warning("List documents failed", error=str(e))
            return f"Failed to list documents: {str(e)}"
