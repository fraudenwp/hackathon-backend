from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class AgentCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1, max_length=1000)


class AgentUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=1000)
    system_prompt: Optional[str] = None
    teaching_mode: Optional[str] = None


class AgentResponse(BaseModel):
    id: str
    name: str
    description: str
    system_prompt: str
    status: str
    teaching_mode: str = "default"
    created_at: datetime
    document_count: int = 0


class AgentListResponse(BaseModel):
    agents: List[AgentResponse]


class AgentDocumentAssignRequest(BaseModel):
    document_ids: List[str]


class DocumentAgentAssignRequest(BaseModel):
    agent_ids: List[str]


class AgentDocumentResponse(BaseModel):
    id: str
    filename: str
    status: str
    content_type: str
    created_at: datetime
