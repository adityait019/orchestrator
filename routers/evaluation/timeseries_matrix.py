import os
import logging
from typing import Any, Optional
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case, desc, asc, or_
from sqlalchemy.exc import IntegrityError
from math import ceil
from database.session import AsyncSessionLocal
from database.models import (
    OrchestrationSession,
    AgentInvocation,
)


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
# 17. Evaluation - Time Series Metrics
# GET /admin/evaluation/timeseries
# -------------------------------------------------------------------

@router.get("/timeseries")
async def get_timeseries_metrics(
    metric: str = Query("success_rate", pattern="^(success_rate|latency|tokens|invocations)$"),
    interval: str = Query("hour", pattern="^(hour|day)$"),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin_token),
):
    # -----------------------------
    # Time bucket (safe label reuse)
    # -----------------------------
    bucket = func.date_trunc(interval, OrchestrationSession.created_at).label("bucket")

    # -----------------------------
    # Metric Queries
    # -----------------------------
    if metric == "success_rate":
        query = (
            select(
                bucket,
                (
                    func.coalesce(
                        func.sum(
                            case(
                                (OrchestrationSession.status == "completed", 1),
                                else_=0
                            )
                        ),
                        0,
                    )
                    * 100.0
                    / func.nullif(func.count(OrchestrationSession.session_id), 0)
                ).label("value"),
            )
            .group_by(bucket)
        )

    elif metric == "latency":
        query = (
            select(
                bucket,
                func.avg(
                    func.extract(
                        "epoch",
                        OrchestrationSession.completed_at
                        - OrchestrationSession.created_at,
                    )
                ).label("value"),
            )
            .group_by(bucket)
        )

    elif metric == "tokens":
        query = (
            select(
                bucket,
                func.coalesce(
                    func.sum(AgentInvocation.total_tokens),
                    0
                ).label("value"),
            )
            .join(
                AgentInvocation,
                AgentInvocation.orchestration_session_id
                == OrchestrationSession.session_id,  # ✅ FIXED
            )
            .group_by(bucket)
        )

    elif metric == "invocations":
        query = (
            select(
                bucket,
                func.count(AgentInvocation.id).label("value"),
            )
            .join(
                AgentInvocation,
                AgentInvocation.orchestration_session_id
                == OrchestrationSession.session_id,  # ✅ FIXED
            )
            .group_by(bucket)
        )

    else:
        raise HTTPException(status_code=400, detail="Invalid metric")

    # -----------------------------
    # Execute Query
    # -----------------------------
    result = await db.execute(query.order_by(bucket))
    rows = result.mappings().all()

    # -----------------------------
    # Format Response
    # -----------------------------
    data = [
        {
            "timestamp": row["bucket"],
            "value": round(row["value"] or 0, 2),
        }
        for row in rows
    ]

    return {
        "metric": metric,
        "interval": interval,
        "data": data,
    }
