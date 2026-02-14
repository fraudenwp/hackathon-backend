from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
from typing import List, Optional

from src.models.sqlmodels.document import Document


async def create_document(
    db: AsyncSession,
    user_id: str,
    filename: str,
    r2_key: str,
    content_type: str,
) -> Document:
    doc = Document(
        user_id=user_id,
        filename=filename,
        r2_key=r2_key,
        content_type=content_type,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


async def get_document(db: AsyncSession, doc_id: str) -> Optional[Document]:
    result = await db.execute(select(Document).where(Document.id == doc_id))
    return result.scalar_one_or_none()


async def list_user_documents(db: AsyncSession, user_id: str) -> List[Document]:
    result = await db.execute(
        select(Document)
        .where(Document.user_id == user_id)
        .order_by(Document.created_at.desc())
    )
    return result.scalars().all()


async def update_document_status(
    db: AsyncSession,
    doc_id: str,
    status: str,
    chunk_count: int = 0,
    error_message: Optional[str] = None,
    description: Optional[str] = None,
) -> Optional[Document]:
    doc = await get_document(db, doc_id)
    if not doc:
        return None
    doc.status = status
    doc.chunk_count = chunk_count
    if error_message:
        doc.error_message = error_message
    if description:
        doc.description = description
    await db.commit()
    await db.refresh(doc)
    return doc


async def delete_document(db: AsyncSession, doc_id: str) -> bool:
    doc = await get_document(db, doc_id)
    if not doc:
        return False
    await db.delete(doc)
    await db.commit()
    return True
