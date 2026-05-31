
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
# 16. Evaluation - Agent Performance Leaderboard
# GET /admin/evaluation/agents
# -------------------------------------------------------------------

@router.get("/agents")
async def get_agent_evaluation(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin_token),
):
    # -----------------------------
    # Base Aggregation Query
    # -----------------------------
    agent_stats_query = (
        select(
            AgentInvocation.agent_name.label("agent_name"),

            func.count(AgentInvocation.id).label("total_invocations"),

            func.coalesce(
                func.sum(case((AgentInvocation.status == "completed", 1), else_=0)), 0
            ).label("completed"),

            func.coalesce(
                func.sum(case((AgentInvocation.status == "failed", 1), else_=0)), 0
            ).label("failed"),

            func.avg(
                func.extract(
                    "epoch",
                    AgentInvocation.completed_at - AgentInvocation.started_at
                )
            ).label("avg_latency"),

            func.avg(AgentInvocation.total_tokens).label("avg_tokens"),

            func.coalesce(func.sum(AgentInvocation.total_tokens), 0).label("total_tokens"),
        )
        .group_by(AgentInvocation.agent_name)
    )

    result = await db.execute(agent_stats_query)
    rows = result.mappings().all()

    total_invocations_global = sum(r["total_invocations"] for r in rows) or 1

    # -----------------------------
    # Derived KPIs per agent
    # -----------------------------
    agents = []

    for row in rows:
        total_invocations = row["total_invocations"] or 0
        completed = row["completed"] or 0
        failed = row["failed"] or 0

        success_rate = (
            (completed / total_invocations) * 100
            if total_invocations > 0
            else 0
        )

        failure_rate = (
            (failed / total_invocations) * 100
            if total_invocations > 0
            else 0
        )

        utilization = total_invocations / total_invocations_global

        agents.append({
            "agent_name": row["agent_name"],
            "total_invocations": total_invocations,

            "success_rate": round(success_rate, 2),
            "failure_rate": round(failure_rate, 2),

            "avg_latency_sec": round(row["avg_latency"] or 0, 2),

            "avg_tokens": round(row["avg_tokens"] or 0, 2),
            "total_tokens": row["total_tokens"] or 0,

            "utilization": round(utilization, 4),
        })

    # -----------------------------
    # Sort leaderboard (by success rate desc)
    # -----------------------------
    agents_sorted = sorted(
        agents,
        key=lambda x: (x["success_rate"], -x["avg_latency_sec"]),
        reverse=True,
    )

    return {
        "total_agents": len(agents_sorted),
        "agents": agents_sorted
    }
