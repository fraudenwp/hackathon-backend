from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select, col
from typing import List, Optional

from src.models.sqlmodels.agent import Agent, AgentDocument
from src.models.sqlmodels.document import Document


async def create_agent(
    db: AsyncSession,
    user_id: str,
    name: str,
    description: str,
) -> Agent:
    agent = Agent(user_id=user_id, name=name, description=description)
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return agent


async def get_agent(db: AsyncSession, agent_id: str) -> Optional[Agent]:
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    return result.scalar_one_or_none()


async def list_user_agents(db: AsyncSession, user_id: str) -> List[Agent]:
    result = await db.execute(
        select(Agent)
        .where(Agent.user_id == user_id)
        .order_by(Agent.created_at.desc())
    )
    return result.scalars().all()


async def update_agent(
    db: AsyncSession,
    agent_id: str,
    **fields,
) -> Optional[Agent]:
    agent = await get_agent(db, agent_id)
    if not agent:
        return None
    for key, value in fields.items():
        if value is not None and hasattr(agent, key):
            setattr(agent, key, value)
    await db.commit()
    await db.refresh(agent)
    return agent


async def delete_agent(db: AsyncSession, agent_id: str) -> bool:
    agent = await get_agent(db, agent_id)
    if not agent:
        return False
    # Delete agent-document associations
    result = await db.execute(
        select(AgentDocument).where(AgentDocument.agent_id == agent_id)
    )
    for ad in result.scalars().all():
        await db.delete(ad)
    await db.delete(agent)
    await db.commit()
    return True


async def assign_documents(
    db: AsyncSession,
    agent_id: str,
    document_ids: List[str],
) -> None:
    # Remove existing assignments
    result = await db.execute(
        select(AgentDocument).where(AgentDocument.agent_id == agent_id)
    )
    for ad in result.scalars().all():
        await db.delete(ad)

    # Add new assignments
    for doc_id in document_ids:
        ad = AgentDocument(agent_id=agent_id, document_id=doc_id)
        db.add(ad)

    await db.commit()


async def get_agent_document_ids(db: AsyncSession, agent_id: str) -> List[str]:
    """Get document IDs assigned to an agent"""
    result = await db.execute(
        select(AgentDocument.document_id).where(AgentDocument.agent_id == agent_id)
    )
    return [row[0] for row in result.all()]


async def get_agent_documents(db: AsyncSession, agent_id: str) -> List[Document]:
    """Get full document objects assigned to an agent"""
    result = await db.execute(
        select(Document)
        .join(AgentDocument, AgentDocument.document_id == Document.id)
        .where(AgentDocument.agent_id == agent_id)
    )
    return result.scalars().all()


async def get_document_agents(db: AsyncSession, document_id: str) -> List[Agent]:
    """Get agents that have access to a document"""
    result = await db.execute(
        select(Agent)
        .join(AgentDocument, AgentDocument.agent_id == Agent.id)
        .where(AgentDocument.document_id == document_id)
    )
    return result.scalars().all()


async def assign_document_to_agents(
    db: AsyncSession,
    document_id: str,
    agent_ids: List[str],
) -> None:
    """Replace all agent assignments for a document"""
    # Remove existing assignments for this document
    result = await db.execute(
        select(AgentDocument).where(AgentDocument.document_id == document_id)
    )
    for ad in result.scalars().all():
        await db.delete(ad)

    # Add new assignments
    for agent_id in agent_ids:
        ad = AgentDocument(agent_id=agent_id, document_id=document_id)
        db.add(ad)

    await db.commit()


async def get_agent_document_count(db: AsyncSession, agent_id: str) -> int:
    """Get count of documents assigned to an agent"""
    result = await db.execute(
        select(AgentDocument).where(AgentDocument.agent_id == agent_id)
    )
    return len(result.scalars().all())
