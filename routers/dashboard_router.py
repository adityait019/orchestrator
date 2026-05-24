import json
import os
import logging
from typing import Any, Optional
import asyncio
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case, desc, asc, or_
from sqlalchemy.exc import IntegrityError
from math import ceil
from database.session import AsyncSessionLocal
from database.models import (
    AgentRegistry,
    OrchestrationSession,
    AgentInvocation,
    AgentDependency,
    AgentEvent,
    Artifact,
    ADKSession,
    ADKEvent,
)

from schemas.admin import (
    AgentCreateRequest,
    AgentUpdateRequest,
)

from agents.agent import root_agent
from services.agent_loader import build_single_agent


logger = logging.getLogger(__name__)
agent_lock = asyncio.Lock()

router = APIRouter(prefix="/admin", tags=["Admin"])

META_TOOL_TOKEN_PREFIX = "[META:TOOL_TOKENS]"


# -------------------------------------------------------------------
# Dependencies
# -------------------------------------------------------------------

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def verify_admin_token(x_admin_token: str = Header(...)):
    MASTER_TOKEN = os.getenv("SECRET_KEY", "super-secret")

    if x_admin_token != MASTER_TOKEN:
        raise HTTPException(status_code=403, detail="Unauthorized")


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def get_pagination(page: int, page_size: int):
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    offset = (page - 1) * page_size
    return page, page_size, offset


def build_paginated_response(items, total: int, page: int, page_size: int):
    return {
        "items": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": ceil(total / page_size) if page_size else 0,
        },
    }


def calculate_duration_seconds(started_at, completed_at):
    if started_at and completed_at:
        return (completed_at - started_at).total_seconds()
    return None


def pydantic_to_dict(model):
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_unset=True)
    return model.dict(exclude_unset=True)


def redact_sensitive_data(value: Any):
    if value is None:
        return None

    if isinstance(value, dict):
        redacted = {}

        for key, val in value.items():
            lower_key = str(key).lower()

            if lower_key in {
                "access_token",
                "refresh_token",
                "id_token",
                "authorization",
                "token",
                "api_key",
                "secret",
                "client_secret",
            }:
                redacted[key] = "***REDACTED***"
            else:
                redacted[key] = redact_sensitive_data(val)

        return redacted

    if isinstance(value, list):
        return [redact_sensitive_data(item) for item in value]

    if isinstance(value, str):
        if META_TOOL_TOKEN_PREFIX in value:
            return f"{META_TOOL_TOKEN_PREFIX} ***REDACTED***"

        try:
            parsed = json.loads(value)
            return redact_sensitive_data(parsed)
        except Exception:
            return value

    return value


# -------------------------------------------------------------------
# 1. Dashboard Summary
# GET /admin/dashboard/summary
# -------------------------------------------------------------------

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin_token),
):
    agent_stats_query = select(
        func.count(AgentRegistry.id).label("total"),
        func.coalesce(
            func.sum(case((AgentRegistry.is_active.is_(True), 1), else_=0)),
            0,
        ).label("active"),
        func.coalesce(
            func.sum(case((AgentRegistry.is_active.is_(False), 1), else_=0)),
            0,
        ).label("inactive"),
        func.coalesce(
            func.sum(case((AgentRegistry.is_healthy.is_(True), 1), else_=0)),
            0,
        ).label("healthy"),
        func.coalesce(
            func.sum(case((AgentRegistry.is_healthy.is_(False), 1), else_=0)),
            0,
        ).label("unhealthy"),
    )

    orchestration_stats_query = select(
        func.count(OrchestrationSession.id).label("total"),
        func.coalesce(
            func.sum(case((OrchestrationSession.status == "running", 1), else_=0)),
            0,
        ).label("running"),
        func.coalesce(
            func.sum(case((OrchestrationSession.status == "completed", 1), else_=0)),
            0,
        ).label("completed"),
        func.coalesce(
            func.sum(case((OrchestrationSession.status == "failed", 1), else_=0)),
            0,
        ).label("failed"),
    )

    invocation_stats_query = select(
        func.count(AgentInvocation.id).label("total"),
        func.coalesce(func.sum(AgentInvocation.total_tokens), 0).label("total_tokens"),
    )

    artifact_stats_query = select(func.count(Artifact.id).label("total"))

    users_query = select(
        func.count(func.distinct(ADKSession.user_id)).label("total")
    )

    adk_sessions_query = select(
        func.count().label("total")
    ).select_from(ADKSession)

    agent_stats = (await db.execute(agent_stats_query)).mappings().one()
    orchestration_stats = (await db.execute(orchestration_stats_query)).mappings().one()
    invocation_stats = (await db.execute(invocation_stats_query)).mappings().one()
    artifact_stats = (await db.execute(artifact_stats_query)).mappings().one()
    users_stats = (await db.execute(users_query)).mappings().one()
    adk_session_stats = (await db.execute(adk_sessions_query)).mappings().one()

    return {
        "agents": {
            "total": agent_stats["total"] or 0,
            "active": agent_stats["active"] or 0,
            "inactive": agent_stats["inactive"] or 0,
            "healthy": agent_stats["healthy"] or 0,
            "unhealthy": agent_stats["unhealthy"] or 0,
        },
        "orchestration_sessions": {
            "total": orchestration_stats["total"] or 0,
            "running": orchestration_stats["running"] or 0,
            "completed": orchestration_stats["completed"] or 0,
            "failed": orchestration_stats["failed"] or 0,
        },
        "invocations": {
            "total": invocation_stats["total"] or 0,
            "total_tokens": invocation_stats["total_tokens"] or 0,
        },
        "artifacts": {
            "total": artifact_stats["total"] or 0,
        },
        "users": {
            "total": users_stats["total"] or 0,
        },
        "adk_sessions": {
            "total": adk_session_stats["total"] or 0,
        },
    }


# -------------------------------------------------------------------
# 2. Agent List
# GET /admin/agents
# -------------------------------------------------------------------

@router.get("/agents")
async def list_agents(
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    is_healthy: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin_token),
):
    page, page_size, offset = get_pagination(page, page_size)

    filters = []

    if search:
        filters.append(AgentRegistry.name.ilike(f"%{search}%"))

    if is_active is not None:
        filters.append(AgentRegistry.is_active == is_active)

    if is_healthy is not None:
        filters.append(AgentRegistry.is_healthy == is_healthy)

    count_query = select(func.count(AgentRegistry.id))
    query = select(AgentRegistry).order_by(desc(AgentRegistry.created_at))

    if filters:
        count_query = count_query.where(*filters)
        query = query.where(*filters)

    total = (await db.execute(count_query)).scalar_one()

    result = await db.execute(query.offset(offset).limit(page_size))
    agents = result.scalars().all()

    items = [
        {
            "id": agent.id,
            "name": agent.name,
            "host": agent.host,
            "port": agent.port,
            "is_active": agent.is_active,
            "is_healthy": agent.is_healthy,
            "created_at": agent.created_at,
            "last_health_check": agent.last_health_check,
        }
        for agent in agents
    ]

    return build_paginated_response(items, total, page, page_size)


# -------------------------------------------------------------------
# 3. Agent Detail
# GET /admin/agents/{agent_name}
# -------------------------------------------------------------------

@router.get("/agents/{agent_name}")
async def get_agent_detail(
    agent_name: str,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin_token),
):
    result = await db.execute(
        select(AgentRegistry).where(AgentRegistry.name == agent_name)
    )
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    stats_query = select(
        func.count(AgentInvocation.id).label("total_invocations"),
        func.coalesce(
            func.sum(case((AgentInvocation.status == "completed", 1), else_=0)),
            0,
        ).label("completed"),
        func.coalesce(
            func.sum(case((AgentInvocation.status == "failed", 1), else_=0)),
            0,
        ).label("failed"),
        func.coalesce(
            func.sum(case((AgentInvocation.status == "running", 1), else_=0)),
            0,
        ).label("running"),
        func.coalesce(func.sum(AgentInvocation.total_tokens), 0).label("total_tokens"),
    ).where(AgentInvocation.agent_name == agent_name)

    stats = (await db.execute(stats_query)).mappings().one()

    recent_result = await db.execute(
        select(AgentInvocation)
        .where(AgentInvocation.agent_name == agent_name)
        .order_by(desc(AgentInvocation.started_at))
        .limit(10)
    )

    recent_invocations = recent_result.scalars().all()

    return {
        "agent": {
            "id": agent.id,
            "name": agent.name,
            "host": agent.host,
            "port": agent.port,
            "is_active": agent.is_active,
            "is_healthy": agent.is_healthy,
            "created_at": agent.created_at,
            "last_health_check": agent.last_health_check,
            "agent_card": redact_sensitive_data(agent.agent_card),
        },
        "stats": {
            "total_invocations": stats["total_invocations"] or 0,
            "completed": stats["completed"] or 0,
            "failed": stats["failed"] or 0,
            "running": stats["running"] or 0,
            "total_tokens": stats["total_tokens"] or 0,
        },
        "recent_invocations": [
            {
                "id": invocation.id,
                "orchestration_session_id": invocation.orchestration_session_id,
                "agent_session_id": invocation.agent_session_id,
                "step_order": invocation.step_order,
                "status": invocation.status,
                "started_at": invocation.started_at,
                "completed_at": invocation.completed_at,
                "total_tokens": invocation.total_tokens,
                "duration_seconds": calculate_duration_seconds(
                    invocation.started_at,
                    invocation.completed_at,
                ),
            }
            for invocation in recent_invocations
        ],
    }


# -------------------------------------------------------------------
# 4. Register Agent
# POST /admin/agents
# -------------------------------------------------------------------

@router.post("/agents", status_code=201)
async def create_agent(
    payload: AgentCreateRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin_token),
):
    agent_card = payload.agent_card

    if not agent_card:
        agent_card_url = f"http://{payload.host}:{payload.port}/.well-known/agent-card.json"

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(agent_card_url)
                response.raise_for_status()
                agent_card = response.json()
        except httpx.TimeoutException:
            raise HTTPException(status_code=400, detail="Agent card endpoint timed out")
        except httpx.HTTPError:
            raise HTTPException(status_code=400, detail="Failed to fetch agent card")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid JSON from agent card endpoint")

    if "name" not in agent_card:
        raise HTTPException(status_code=400, detail="Agent card must contain a 'name' field")

    if agent_card["name"] != payload.name:
        raise HTTPException(status_code=400, detail="Agent name in card does not match payload")

    existing_result = await db.execute(
        select(AgentRegistry).where(AgentRegistry.name == payload.name)
    )
    existing_agent = existing_result.scalar_one_or_none()

    if existing_agent:
        raise HTTPException(status_code=409, detail="Agent already exists")

    now = datetime.now(timezone.utc)

    agent = AgentRegistry(
        name=payload.name,
        host=payload.host,
        port=payload.port,
        is_active=payload.is_active,
        is_healthy=payload.is_healthy,
        agent_card=agent_card,
        created_at=now,
        last_health_check=now,
    )

    db.add(agent)

    try:
        await db.commit()
        await db.refresh(agent)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Agent already exists")

    try:
        agent_instance = await build_single_agent(agent)
        existing_names = {a.name for a in root_agent.sub_agents}

        if agent_instance and agent.name not in existing_names:
            async with agent_lock:
                root_agent.sub_agents.append(agent_instance)
            logger.info(f"✅ Agent {agent.name} added dynamically")
    except Exception as e:
        logger.warning(f"⚠️ Failed to dynamically attach agent: {e}")

    return {
        "message": "Agent created successfully",
        "agent": {
            "id": agent.id,
            "name": agent.name,
            "host": agent.host,
            "port": agent.port,
            "is_active": agent.is_active,
            "is_healthy": agent.is_healthy,
            "created_at": agent.created_at,
            "last_health_check": agent.last_health_check,
            "agent_card": redact_sensitive_data(agent.agent_card),
        },
    }


# -------------------------------------------------------------------
# 5. Update Agent
# PATCH /admin/agents/{agent_name}
# -------------------------------------------------------------------

@router.patch("/agents/{agent_name}")
async def update_agent(
    agent_name: str,
    payload: AgentUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin_token),
):
    result = await db.execute(
        select(AgentRegistry).where(AgentRegistry.name == agent_name)
    )
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    update_data = pydantic_to_dict(payload)

    for key, value in update_data.items():
        setattr(agent, key, value)

    await db.commit()
    await db.refresh(agent)

    return {
        "message": "Agent updated successfully",
        "agent": {
            "id": agent.id,
            "name": agent.name,
            "host": agent.host,
            "port": agent.port,
            "is_active": agent.is_active,
            "is_healthy": agent.is_healthy,
            "created_at": agent.created_at,
            "last_health_check": agent.last_health_check,
            "agent_card": redact_sensitive_data(agent.agent_card),
        },
    }


# -------------------------------------------------------------------
# 6. Delete Agent Permanently
# DELETE /admin/agents/{agent_name}
# -------------------------------------------------------------------

@router.delete("/agents/{agent_name}")
async def delete_agent(
    agent_name: str,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin_token),
):
    result = await db.execute(
        select(AgentRegistry).where(AgentRegistry.name == agent_name)
    )
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    async with agent_lock:
        root_agent.sub_agents = [
            a for a in root_agent.sub_agents
            if a.name != agent_name
        ]

    await db.delete(agent)
    await db.commit()

    logger.info(f"🗑️ Agent '{agent_name}' permanently deleted from database")

    return {
        "message": f"Agent '{agent_name}' deleted permanently"
    }


# -------------------------------------------------------------------
# 7. Orchestration Sessions
# GET /admin/orchestration-sessions
# -------------------------------------------------------------------

@router.get("/orchestration-sessions")
async def list_orchestration_sessions(
    status: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin_token),
):
    page, page_size, offset = get_pagination(page, page_size)

    filters = []

    if status:
        filters.append(OrchestrationSession.status == status)

    if user_id:
        filters.append(OrchestrationSession.user_id.ilike(f"%{user_id}%"))

    if session_id:
        filters.append(OrchestrationSession.session_id.ilike(f"%{session_id}%"))

    count_query = select(func.count(OrchestrationSession.id))

    inv_stats_subq = (
        select(
            AgentInvocation.orchestration_session_id.label("session_db_id"),
            func.count(AgentInvocation.id).label("invocation_count"),
            func.coalesce(func.sum(AgentInvocation.total_tokens), 0).label("total_tokens"),
        )
        .group_by(AgentInvocation.orchestration_session_id)
        .subquery()
    )

    artifact_stats_subq = (
        select(
            AgentInvocation.orchestration_session_id.label("session_db_id"),
            func.count(Artifact.id).label("artifact_count"),
        )
        .join(AgentInvocation, AgentInvocation.id == Artifact.invocation_id)
        .group_by(AgentInvocation.orchestration_session_id)
        .subquery()
    )

    query = (
        select(
            OrchestrationSession.id,
            OrchestrationSession.session_id,
            OrchestrationSession.user_id,
            OrchestrationSession.status,
            OrchestrationSession.created_at,
            OrchestrationSession.completed_at,
            func.coalesce(inv_stats_subq.c.invocation_count, 0).label("invocation_count"),
            func.coalesce(inv_stats_subq.c.total_tokens, 0).label("total_tokens"),
            func.coalesce(artifact_stats_subq.c.artifact_count, 0).label("artifact_count"),
        )
        .outerjoin(
            inv_stats_subq,
            inv_stats_subq.c.session_db_id == OrchestrationSession.id,
        )
        .outerjoin(
            artifact_stats_subq,
            artifact_stats_subq.c.session_db_id == OrchestrationSession.id,
        )
        .order_by(desc(OrchestrationSession.created_at))
    )

    if filters:
        count_query = count_query.where(*filters)
        query = query.where(*filters)

    total = (await db.execute(count_query)).scalar_one()

    result = await db.execute(query.offset(offset).limit(page_size))
    rows = result.mappings().all()

    items = [
        {
            "id": row["id"],
            "session_id": row["session_id"],
            "user_id": row["user_id"],
            "status": row["status"],
            "created_at": row["created_at"],
            "completed_at": row["completed_at"],
            "invocation_count": row["invocation_count"] or 0,
            "artifact_count": row["artifact_count"] or 0,
            "total_tokens": row["total_tokens"] or 0,
            "duration_seconds": calculate_duration_seconds(
                row["created_at"],
                row["completed_at"],
            ),
        }
        for row in rows
    ]

    return build_paginated_response(items, total, page, page_size)


# -------------------------------------------------------------------
# 8. Orchestration Session Detail
# GET /admin/orchestration-sessions/{session_db_id}
# -------------------------------------------------------------------

@router.get("/orchestration-sessions/{session_db_id}")
async def get_orchestration_session_detail(
    session_db_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin_token),
):
    session_result = await db.execute(
        select(OrchestrationSession).where(OrchestrationSession.id == session_db_id)
    )
    session = session_result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Orchestration session not found")

    invocations_result = await db.execute(
        select(AgentInvocation)
        .where(AgentInvocation.orchestration_session_id == session_db_id)
        .order_by(asc(AgentInvocation.step_order))
    )

    invocations = invocations_result.scalars().all()
    invocation_ids = [invocation.id for invocation in invocations]

    dependencies = []
    events = []
    artifacts = []

    if invocation_ids:
        dependencies_result = await db.execute(
            select(AgentDependency)
            .where(
                or_(
                    AgentDependency.parent_invocation_id.in_(invocation_ids),
                    AgentDependency.child_invocation_id.in_(invocation_ids),
                )
            )
            .order_by(asc(AgentDependency.created_at))
        )
        dependencies = dependencies_result.scalars().all()

        events_result = await db.execute(
            select(AgentEvent)
            .where(AgentEvent.invocation_id.in_(invocation_ids))
            .order_by(asc(AgentEvent.created_at))
        )
        events = events_result.scalars().all()

        artifacts_result = await db.execute(
            select(Artifact)
            .where(Artifact.invocation_id.in_(invocation_ids))
            .order_by(desc(Artifact.created_at))
        )
        artifacts = artifacts_result.scalars().all()

    return {
        "session": {
            "id": session.id,
            "session_id": session.session_id,
            "user_id": session.user_id,
            "status": session.status,
            "created_at": session.created_at,
            "completed_at": session.completed_at,
            "duration_seconds": calculate_duration_seconds(
                session.created_at,
                session.completed_at,
            ),
        },
        "invocations": [
            {
                "id": invocation.id,
                "agent_name": invocation.agent_name,
                "agent_session_id": invocation.agent_session_id,
                "step_order": invocation.step_order,
                "status": invocation.status,
                "input_payload": redact_sensitive_data(invocation.input_payload),
                "output_payload": redact_sensitive_data(invocation.output_payload),
                "started_at": invocation.started_at,
                "completed_at": invocation.completed_at,
                "input_tokens": invocation.input_tokens,
                "output_tokens": invocation.output_tokens,
                "total_tokens": invocation.total_tokens,
                "duration_seconds": calculate_duration_seconds(
                    invocation.started_at,
                    invocation.completed_at,
                ),
            }
            for invocation in invocations
        ],
        "dependencies": [
            {
                "id": dependency.id,
                "parent_invocation_id": dependency.parent_invocation_id,
                "child_invocation_id": dependency.child_invocation_id,
                "dependency_type": dependency.dependency_type,
                "created_at": dependency.created_at,
            }
            for dependency in dependencies
        ],
        "events": [
            {
                "id": event.id,
                "invocation_id": event.invocation_id,
                "event_type": event.event_type,
                "payload": redact_sensitive_data(event.payload),
                "created_at": event.created_at,
            }
            for event in events
        ],
        "artifacts": [
            {
                "id": artifact.id,
                "invocation_id": artifact.invocation_id,
                "file_id": artifact.file_id,
                "filename": artifact.filename,
                "url": artifact.url,
                "path": artifact.path,
                "tenant_id": artifact.tenant_id,
                "user_id": artifact.user_id,
                "session_id": artifact.session_id,
                "mime_type": artifact.mime_type,
                "file_size": artifact.file_size,
                "created_at": artifact.created_at,
            }
            for artifact in artifacts
        ],
    }


# -------------------------------------------------------------------
# 9. Invocation List
# GET /admin/invocations
# -------------------------------------------------------------------

@router.get("/invocations")
async def list_invocations(
    agent_name: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    orchestration_session_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin_token),
):
    page, page_size, offset = get_pagination(page, page_size)

    filters = []

    if agent_name:
        filters.append(AgentInvocation.agent_name.ilike(f"%{agent_name}%"))

    if status:
        filters.append(AgentInvocation.status == status)

    if orchestration_session_id:
        filters.append(AgentInvocation.orchestration_session_id == orchestration_session_id)

    count_query = select(func.count(AgentInvocation.id))
    query = select(AgentInvocation).order_by(desc(AgentInvocation.started_at))

    if filters:
        count_query = count_query.where(*filters)
        query = query.where(*filters)

    total = (await db.execute(count_query)).scalar_one()

    result = await db.execute(query.offset(offset).limit(page_size))
    invocations = result.scalars().all()

    items = [
        {
            "id": invocation.id,
            "orchestration_session_id": invocation.orchestration_session_id,
            "agent_name": invocation.agent_name,
            "agent_session_id": invocation.agent_session_id,
            "step_order": invocation.step_order,
            "status": invocation.status,
            "started_at": invocation.started_at,
            "completed_at": invocation.completed_at,
            "input_tokens": invocation.input_tokens,
            "output_tokens": invocation.output_tokens,
            "total_tokens": invocation.total_tokens,
            "duration_seconds": calculate_duration_seconds(
                invocation.started_at,
                invocation.completed_at,
            ),
        }
        for invocation in invocations
    ]

    return build_paginated_response(items, total, page, page_size)


# -------------------------------------------------------------------
# 10. Invocation Detail
# GET /admin/invocations/{invocation_id}
# -------------------------------------------------------------------

@router.get("/invocations/{invocation_id}")
async def get_invocation_detail(
    invocation_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin_token),
):
    invocation_result = await db.execute(
        select(AgentInvocation).where(AgentInvocation.id == invocation_id)
    )
    invocation = invocation_result.scalar_one_or_none()

    if not invocation:
        raise HTTPException(status_code=404, detail="Invocation not found")

    events_result = await db.execute(
        select(AgentEvent)
        .where(AgentEvent.invocation_id == invocation_id)
        .order_by(asc(AgentEvent.created_at))
    )
    events = events_result.scalars().all()

    artifacts_result = await db.execute(
        select(Artifact)
        .where(Artifact.invocation_id == invocation_id)
        .order_by(desc(Artifact.created_at))
    )
    artifacts = artifacts_result.scalars().all()

    dependencies_result = await db.execute(
        select(AgentDependency)
        .where(
            or_(
                AgentDependency.parent_invocation_id == invocation_id,
                AgentDependency.child_invocation_id == invocation_id,
            )
        )
        .order_by(asc(AgentDependency.created_at))
    )
    dependencies = dependencies_result.scalars().all()

    return {
        "invocation": {
            "id": invocation.id,
            "orchestration_session_id": invocation.orchestration_session_id,
            "agent_name": invocation.agent_name,
            "agent_session_id": invocation.agent_session_id,
            "step_order": invocation.step_order,
            "status": invocation.status,
            "input_payload": redact_sensitive_data(invocation.input_payload),
            "output_payload": redact_sensitive_data(invocation.output_payload),
            "started_at": invocation.started_at,
            "completed_at": invocation.completed_at,
            "input_tokens": invocation.input_tokens,
            "output_tokens": invocation.output_tokens,
            "total_tokens": invocation.total_tokens,
            "duration_seconds": calculate_duration_seconds(
                invocation.started_at,
                invocation.completed_at,
            ),
        },
        "events": [
            {
                "id": event.id,
                "event_type": event.event_type,
                "payload": redact_sensitive_data(event.payload),
                "created_at": event.created_at,
            }
            for event in events
        ],
        "artifacts": [
            {
                "id": artifact.id,
                "file_id": artifact.file_id,
                "filename": artifact.filename,
                "url": artifact.url,
                "path": artifact.path,
                "tenant_id": artifact.tenant_id,
                "user_id": artifact.user_id,
                "session_id": artifact.session_id,
                "mime_type": artifact.mime_type,
                "file_size": artifact.file_size,
                "created_at": artifact.created_at,
            }
            for artifact in artifacts
        ],
        "dependencies": [
            {
                "id": dependency.id,
                "parent_invocation_id": dependency.parent_invocation_id,
                "child_invocation_id": dependency.child_invocation_id,
                "dependency_type": dependency.dependency_type,
                "created_at": dependency.created_at,
            }
            for dependency in dependencies
        ],
    }


# -------------------------------------------------------------------
# 11. Agent Events
# GET /admin/agent-events
# -------------------------------------------------------------------

@router.get("/agent-events")
async def list_agent_events(
    invocation_id: Optional[int] = Query(None),
    event_type: Optional[str] = Query(None),
    agent_name: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin_token),
):
    page, page_size, offset = get_pagination(page, page_size)

    filters = []

    if invocation_id:
        filters.append(AgentEvent.invocation_id == invocation_id)

    if event_type:
        filters.append(AgentEvent.event_type == event_type)

    if agent_name:
        filters.append(AgentInvocation.agent_name.ilike(f"%{agent_name}%"))

    count_query = (
        select(func.count(AgentEvent.id))
        .join(AgentInvocation, AgentInvocation.id == AgentEvent.invocation_id)
    )

    query = (
        select(
            AgentEvent.id,
            AgentEvent.invocation_id,
            AgentEvent.event_type,
            AgentEvent.payload,
            AgentEvent.created_at,
            AgentInvocation.agent_name,
        )
        .join(AgentInvocation, AgentInvocation.id == AgentEvent.invocation_id)
        .order_by(desc(AgentEvent.created_at))
    )

    if filters:
        count_query = count_query.where(*filters)
        query = query.where(*filters)

    total = (await db.execute(count_query)).scalar_one()

    result = await db.execute(query.offset(offset).limit(page_size))
    rows = result.mappings().all()

    items = [
        {
            "id": row["id"],
            "invocation_id": row["invocation_id"],
            "event_type": row["event_type"],
            "payload": redact_sensitive_data(row["payload"]),
            "created_at": row["created_at"],
            "agent_name": row["agent_name"],
        }
        for row in rows
    ]

    return build_paginated_response(items, total, page, page_size)


# -------------------------------------------------------------------
# 12. Artifacts
# GET /admin/artifacts
# -------------------------------------------------------------------

@router.get("/artifacts")
async def list_artifacts(
    tenant_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
    invocation_id: Optional[int] = Query(None),
    mime_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin_token),
):
    page, page_size, offset = get_pagination(page, page_size)

    filters = []

    if tenant_id:
        filters.append(Artifact.tenant_id == tenant_id)

    if user_id:
        filters.append(Artifact.user_id.ilike(f"%{user_id}%"))

    if session_id:
        filters.append(Artifact.session_id.ilike(f"%{session_id}%"))

    if invocation_id:
        filters.append(Artifact.invocation_id == invocation_id)

    if mime_type:
        filters.append(Artifact.mime_type == mime_type)

    count_query = (
        select(func.count(Artifact.id))
        .outerjoin(AgentInvocation, AgentInvocation.id == Artifact.invocation_id)
    )

    query = (
        select(
            Artifact.id,
            Artifact.invocation_id,
            Artifact.file_id,
            Artifact.filename,
            Artifact.url,
            Artifact.path,
            Artifact.tenant_id,
            Artifact.user_id,
            Artifact.session_id,
            Artifact.mime_type,
            Artifact.file_size,
            Artifact.created_at,
            AgentInvocation.agent_name,
        )
        .outerjoin(AgentInvocation, AgentInvocation.id == Artifact.invocation_id)
        .order_by(desc(Artifact.created_at))
    )

    if filters:
        count_query = count_query.where(*filters)
        query = query.where(*filters)

    total = (await db.execute(count_query)).scalar_one()

    result = await db.execute(query.offset(offset).limit(page_size))
    rows = result.mappings().all()

    items = [
        {
            "id": row["id"],
            "invocation_id": row["invocation_id"],
            "file_id": row["file_id"],
            "filename": row["filename"],
            "url": row["url"],
            "path": row["path"],
            "tenant_id": row["tenant_id"],
            "user_id": row["user_id"],
            "session_id": row["session_id"],
            "mime_type": row["mime_type"],
            "file_size": row["file_size"],
            "created_at": row["created_at"],
            "agent_name": row["agent_name"],
        }
        for row in rows
    ]

    return build_paginated_response(items, total, page, page_size)


# -------------------------------------------------------------------
# 13. ADK Session List
# GET /admin/adk-sessions
# -------------------------------------------------------------------

@router.get("/adk-sessions")
async def list_adk_sessions(
    app_name: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin_token),
):
    page, page_size, offset = get_pagination(page, page_size)

    filters = []

    if app_name:
        filters.append(ADKSession.app_name == app_name)

    if user_id:
        filters.append(ADKSession.user_id.ilike(f"%{user_id}%"))

    if session_id:
        filters.append(ADKSession.id.ilike(f"%{session_id}%"))

    count_query = select(func.count()).select_from(ADKSession)
    query = select(ADKSession).order_by(desc(ADKSession.update_time))

    if filters:
        count_query = count_query.where(*filters)
        query = query.where(*filters)

    total = (await db.execute(count_query)).scalar_one()

    result = await db.execute(query.offset(offset).limit(page_size))
    sessions = result.scalars().all()

    items = [
        {
            "app_name": session.app_name,
            "user_id": session.user_id,
            "session_id": session.id,
            "create_time": session.create_time,
            "update_time": session.update_time,
        }
        for session in sessions
    ]

    return build_paginated_response(items, total, page, page_size)


# -------------------------------------------------------------------
# 14. ADK Session Detail
# GET /admin/adk-sessions/{app_name}/{user_id}/{session_id}
# -------------------------------------------------------------------

@router.get("/adk-sessions/{app_name}/{user_id}/{session_id}")
async def get_adk_session_detail(
    app_name: str,
    user_id: str,
    session_id: str,
    recent_events_limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin_token),
):
    session_result = await db.execute(
        select(ADKSession).where(
            ADKSession.app_name == app_name,
            ADKSession.user_id == user_id,
            ADKSession.id == session_id,
        )
    )

    session = session_result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="ADK session not found")

    events_result = await db.execute(
        select(ADKEvent)
        .where(
            ADKEvent.app_name == app_name,
            ADKEvent.user_id == user_id,
            ADKEvent.session_id == session_id,
        )
        .order_by(desc(ADKEvent.timestamp))
        .limit(recent_events_limit)
    )

    events = events_result.scalars().all()

    return {
        "session": {
            "app_name": session.app_name,
            "user_id": session.user_id,
            "session_id": session.id,
            "state": redact_sensitive_data(session.state),
            "create_time": session.create_time,
            "update_time": session.update_time,
        },
        "recent_events": [
            {
                "id": event.id,
                "app_name": event.app_name,
                "user_id": event.user_id,
                "session_id": event.session_id,
                "invocation_id": event.invocation_id,
                "timestamp": event.timestamp,
                "event_data": redact_sensitive_data(event.event_data),
            }
            for event in events
        ],
    }

