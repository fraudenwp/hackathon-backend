from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Security, UploadFile, File
from fastapi.responses import Response
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette import status

from src.constants.env import R2_BUCKET_NAME
from src.crud.auth import AuthCRUD
from src.crud.document import (
    create_document,
    delete_document as delete_document_db,
    get_document,
    list_user_documents,
)
from src.models.basemodels.document import DocumentListResponse, DocumentResponse
from src.models.dependency import get_session
from src.models.sqlmodels.user import User
from src.services.rag_service import rag_service
from src.tasks.rag.embedding_task import process_document_embedding
from src.utils.logger import logger
from src.utils.s3_wrapper import S3ClientWrapper

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "text/plain",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
}


class DocumentController:
    tags = ["document"]
    router = APIRouter(tags=tags)

    @router.post("/upload")
    async def upload_document(
        current_user: Annotated[
            User, Security(AuthCRUD.get_current_user_with_access())
        ],
        db: AsyncSession = Depends(get_session),
        file: UploadFile = File(...),
    ) -> DocumentResponse:
        """Dosya yukle, R2'ye kaydet, embedding task'i baslat"""
        if file.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Desteklenmeyen dosya tipi: {file.content_type}. PDF, TXT veya DOCX yukleyin.",
            )

        r2_key = f"documents/{current_user.id}/{file.filename}"

        # Upload to R2
        await file.seek(0)
        content = await file.read()
        async with S3ClientWrapper() as s3:
            await s3.put_object(
                bucket=R2_BUCKET_NAME,
                key=r2_key,
                body=content,
                content_type=file.content_type,
            )

        # Save to DB
        doc = await create_document(
            db=db,
            user_id=current_user.id,
            filename=file.filename,
            r2_key=r2_key,
            content_type=file.content_type,
        )

        # Trigger embedding in background
        await process_document_embedding.kiq(doc.id)
        logger.info("Document upload started", doc_id=doc.id, filename=file.filename)

        return DocumentResponse(
            id=doc.id,
            filename=doc.filename,
            status=doc.status,
            chunk_count=doc.chunk_count,
            content_type=doc.content_type,
            created_at=doc.created_at,
        )

    @router.get("/")
    async def list_documents(
        current_user: Annotated[
            User, Security(AuthCRUD.get_current_user_with_access())
        ],
        db: AsyncSession = Depends(get_session),
    ) -> DocumentListResponse:
        """Kullanicinin dokumanlari"""
        docs = await list_user_documents(db, current_user.id)
        return DocumentListResponse(
            documents=[
                DocumentResponse(
                    id=d.id,
                    filename=d.filename,
                    status=d.status,
                    chunk_count=d.chunk_count,
                    content_type=d.content_type,
                    created_at=d.created_at,
                    error_message=d.error_message,
                )
                for d in docs
            ]
        )

    @router.get("/{doc_id}/view")
    async def view_document(
        doc_id: str,
        current_user: Annotated[
            User, Security(AuthCRUD.get_current_user_with_access())
        ],
        db: AsyncSession = Depends(get_session),
    ):
        """Dokümanı görüntülemek için içerik döndür (text) veya stream et (PDF)"""
        doc = await get_document(db, doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Doküman bulunamadı")

        if doc.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Yetkisiz işlem")

        logger.info("Viewing document", doc_id=doc_id, r2_key=doc.r2_key, bucket=R2_BUCKET_NAME, content_type=doc.content_type)

        # Text dosyaları için içeriği JSON olarak döndür
        if doc.content_type == "text/plain":
            async with S3ClientWrapper() as s3:
                obj = await s3.get_object(bucket=R2_BUCKET_NAME, key=doc.r2_key)
                body = await obj["Body"].read()
                text_content = body.decode("utf-8")
            return {"type": "text", "content": text_content, "filename": doc.filename}

        # PDF ve diğer dosyalar için dosyayı R2'den çekip döndür
        async with S3ClientWrapper() as s3:
            obj = await s3.get_object(bucket=R2_BUCKET_NAME, key=doc.r2_key)
            body = await obj["Body"].read()

        return Response(
            content=body,
            media_type=doc.content_type,
            headers={
                "Content-Disposition": f'inline; filename="{doc.filename}"',
            },
        )

    @router.delete("/{doc_id}")
    async def delete_document(
        doc_id: str,
        current_user: Annotated[
            User, Security(AuthCRUD.get_current_user_with_access())
        ],
        db: AsyncSession = Depends(get_session),
    ) -> dict:
        """Dokumani sil (R2 + ChromaDB + DB)"""
        doc = await get_document(db, doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Dokuman bulunamadi")

        if doc.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Yetkisiz islem")

        # Delete from R2
        try:
            async with S3ClientWrapper() as s3:
                await s3.delete_object(bucket=R2_BUCKET_NAME, key=doc.r2_key)
        except Exception:
            logger.warning("R2 delete failed, continuing", doc_id=doc_id)

        # Delete from ChromaDB
        rag_service.delete_document(user_id=current_user.id, doc_id=doc_id)

        # Delete from DB
        await delete_document_db(db, doc_id)

        return {"message": "Dokuman silindi"}
