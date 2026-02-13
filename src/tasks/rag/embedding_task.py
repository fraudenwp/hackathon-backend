"""Document embedding background task"""

import tempfile

from pypdf import PdfReader
from docx import Document as DocxDocument

from src.constants.env import R2_BUCKET_NAME
from src.models.database import db as database
from src.crud.document import get_document, update_document_status
from src.services.rag_service import rag_service
from src.tasks.taskiq_setup import broker
from src.utils.logger import logger
from src.utils.s3_wrapper import S3ClientWrapper


def _extract_text(file_path: str, content_type: str) -> str:
    """Extract text from file based on content type"""
    if content_type == "application/pdf" or file_path.endswith(".pdf"):
        reader = PdfReader(file_path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    elif content_type in (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    ) or file_path.endswith(".docx"):
        doc = DocxDocument(file_path)
        return "\n".join(para.text for para in doc.paragraphs)

    else:
        # Default: plain text
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()


@broker.task
async def process_document_embedding(doc_id: str):
    """Download document from R2, extract text, chunk & embed into ChromaDB"""
    logger.info("Starting document embedding", doc_id=doc_id)

    async with database.get_session_context() as db:
        doc = await get_document(db, doc_id)
        if not doc:
            logger.error("Document not found", doc_id=doc_id)
            return {"success": False, "error": "Document not found"}

        # Mark as processing
        await update_document_status(db, doc_id, status="processing")

    try:
        # Download from R2
        with tempfile.NamedTemporaryFile(suffix=f"_{doc.filename}", delete=True) as tmp:
            async with S3ClientWrapper() as s3:
                await s3.download_file(
                    bucket=R2_BUCKET_NAME,
                    key=doc.r2_key,
                    download_path=tmp.name,
                )

            # Extract text
            text = _extract_text(tmp.name, doc.content_type)

        if not text.strip():
            async with database.get_session_context() as db:
                await update_document_status(
                    db, doc_id, status="failed", error_message="Dosyadan metin cikarilamadi"
                )
            return {"success": False, "error": "No text extracted"}

        # Embed into ChromaDB
        chunk_count = rag_service.add_document(
            user_id=doc.user_id,
            doc_id=doc_id,
            text=text,
            filename=doc.filename,
        )

        # Update status to ready
        async with database.get_session_context() as db:
            await update_document_status(
                db, doc_id, status="ready", chunk_count=chunk_count
            )

        logger.info(
            "Document embedding completed",
            doc_id=doc_id,
            chunk_count=chunk_count,
        )
        return {"success": True, "doc_id": doc_id, "chunk_count": chunk_count}

    except Exception as e:
        logger.error("Document embedding failed", doc_id=doc_id, error=str(e))
        async with database.get_session_context() as db:
            await update_document_status(
                db, doc_id, status="failed", error_message=str(e)[:500]
            )
        raise
