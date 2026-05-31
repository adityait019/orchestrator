
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


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def verify_admin_token(x_admin_token: str = Header(...)):
    MASTER_TOKEN = os.getenv("SECRET_KEY", "super-secret")

    if x_admin_token != MASTER_TOKEN:
        raise HTTPException(status_code=403, detail="Unauthorized")




router = APIRouter(
    prefix="/admin/evaluation",
    tags=["Evaluation"],
    dependencies=[Depends(verify_admin_token)],
)
# -------------------------------------------------------------------
# 15. Evaluation Overview
# GET /admin/evaluation/overview
# -------------------------------------------------------------------

@router.get("/overview")
async def get_evaluation_overview(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin_token),
):
    # -----------------------------
    # 1. Session Metrics
    # -----------------------------
    session_stats_query = select(
        func.count(OrchestrationSession.id).label("total_sessions"),
        func.coalesce(
            func.sum(case((OrchestrationSession.status == "completed", 1), else_=0)), 0
        ).label("completed_sessions"),
        func.coalesce(
            func.sum(case((OrchestrationSession.status == "failed", 1), else_=0)), 0
        ).label("failed_sessions"),
        func.avg(
            func.extract(
                "epoch",
                OrchestrationSession.completed_at - OrchestrationSession.created_at,
            )
        ).label("avg_session_latency_sec"),
    )

    # -----------------------------
    # 2. Invocation Metrics
    # -----------------------------
    invocation_stats_query = select(
        func.count(AgentInvocation.id).label("total_invocations"),
        func.coalesce(
            func.sum(case((AgentInvocation.status == "completed", 1), else_=0)), 0
        ).label("completed_invocations"),
        func.coalesce(
            func.sum(case((AgentInvocation.status == "failed", 1), else_=0)), 0
        ).label("failed_invocations"),
        func.avg(
            func.extract(
                "epoch",
                AgentInvocation.completed_at - AgentInvocation.started_at,
            )
        ).label("avg_invocation_latency_sec"),
        func.avg(AgentInvocation.total_tokens).label("avg_tokens"),
        func.coalesce(func.sum(AgentInvocation.total_tokens), 0).label("total_tokens"),
    )

    # -----------------------------
    # 3. Event Metrics
    # -----------------------------
    event_stats_query = select(
        func.count(AgentEvent.id).label("total_events"),
    )

    # -----------------------------
    # 4. Artifact Metrics
    # -----------------------------
    artifact_stats_query = select(
        func.count(Artifact.id).label("total_artifacts"),
    )

    # -----------------------------
    # Execute queries
    # -----------------------------
    session_stats = (await db.execute(session_stats_query)).mappings().one()
    invocation_stats = (await db.execute(invocation_stats_query)).mappings().one()
    event_stats = (await db.execute(event_stats_query)).mappings().one()
    artifact_stats = (await db.execute(artifact_stats_query)).mappings().one()

    # -----------------------------
    # Extract values safely
    # -----------------------------
    total_sessions = session_stats["total_sessions"] or 0
    completed_sessions = session_stats["completed_sessions"] or 0
    failed_sessions = session_stats["failed_sessions"] or 0

    total_invocations = invocation_stats["total_invocations"] or 0
    completed_invocations = invocation_stats["completed_invocations"] or 0
    failed_invocations = invocation_stats["failed_invocations"] or 0

    total_tokens = invocation_stats["total_tokens"] or 0
    avg_tokens = invocation_stats["avg_tokens"] or 0

    total_events = event_stats["total_events"] or 0
    total_artifacts = artifact_stats["total_artifacts"] or 0

    # -----------------------------
    # KPIs (Derived Metrics)
    # -----------------------------
    task_success_rate = (
        (completed_sessions / total_sessions) * 100
        if total_sessions > 0
        else 0
    )

    invocation_success_rate = (
        (completed_invocations / total_invocations) * 100
        if total_invocations > 0
        else 0
    )

    failure_rate = (
        (failed_invocations / total_invocations) * 100
        if total_invocations > 0
        else 0
    )

    event_density = (
        total_events / total_invocations
        if total_invocations > 0
        else 0
    )

    artifact_generation_rate = (
        total_artifacts / total_invocations
        if total_invocations > 0
        else 0
    )

    cost_per_successful_task = (
        total_tokens / completed_sessions
        if completed_sessions > 0
        else 0
    )

    throughput_per_hour_query = select(
        func.count(OrchestrationSession.id) /
        func.greatest(
            func.extract(
                "epoch",
                func.max(OrchestrationSession.created_at)
                - func.min(OrchestrationSession.created_at)
            ) / 3600,
            1
        )
    )

    throughput_per_hour = (await db.execute(throughput_per_hour_query)).scalar() or 0

    # -----------------------------
    # Final response
    # -----------------------------
    return {
        "task_success_rate": round(task_success_rate, 2),
        "invocation_success_rate": round(invocation_success_rate, 2),
        "failure_rate": round(failure_rate, 2),

        "avg_session_latency_sec": round(session_stats["avg_session_latency_sec"] or 0, 2),
        "avg_invocation_latency_sec": round(invocation_stats["avg_invocation_latency_sec"] or 0, 2),

        "avg_tokens_per_invocation": round(avg_tokens or 0, 2),
        "total_tokens": total_tokens,

        "cost_per_successful_task": round(cost_per_successful_task, 2),

        "artifact_generation_rate": round(artifact_generation_rate, 2),
        "event_density": round(event_density, 2),

        "throughput_per_hour": round(throughput_per_hour, 2),
    }
