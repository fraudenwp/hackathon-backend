from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class DocumentResponse(BaseModel):
    id: str
    filename: str
    status: str
    chunk_count: int
    content_type: str
    created_at: datetime
    error_message: Optional[str] = None


class DocumentListResponse(BaseModel):
    documents: List[DocumentResponse]
