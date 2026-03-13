from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import httpx
from datetime import datetime
from fastapi import (
    FastAPI,APIRouter,HTTPException
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
import asyncio
import os
import logging
from database import AsyncSessionLocal
from models import AgentRegistry
from schemas import AddAgentRequest, AgentResponse
from contextlib import asynccontextmanager


logger=logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
app=FastAPI(title="Agent Registry Testing.")
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def health_check_loop():
    while True:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(AgentRegistry))
            agents = result.scalars().all()

            for agent in agents:
                url = f"http://{agent.host}:{agent.port}/health"

                try:
                    async with httpx.AsyncClient(timeout=3.0) as client:
                        response = await client.get(url)

                        agent.is_healthy = response.status_code == 200

                except Exception:
                    agent.is_healthy = False

                agent.last_health_check = datetime.now()

            await db.commit()

        await asyncio.sleep(10)

@app.post("/agents/add")
async def add_agent(
    payload: AddAgentRequest,
    db: AsyncSession = Depends(get_db),
):
    # 1️⃣ Validate Authorization Token (simple example)
    MASTER_TOKEN = os.getenv("MASTER_AGENT_TOKEN", "super-secret")

    if payload.auth_token != MASTER_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid authorization token")

    # 2️⃣ Validate Agent Card Exists
    agent_card_url = f"http://{payload.host}:{payload.port}/.well-known/agent-card.json"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(agent_card_url)
            if response.status_code != 200:
                raise HTTPException(status_code=400, detail="Invalid agent card endpoint")
    except Exception:
        raise HTTPException(status_code=400, detail="Agent not reachable")

    # 3️⃣ Check if already exists
    result = await db.execute(select(AgentRegistry).where(AgentRegistry.name == payload.name))
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(status_code=400, detail="Agent already registered")

    # 4️⃣ Save Agent
    new_agent = AgentRegistry(
        name=payload.name,
        host=payload.host,
        port=payload.port,
        auth_token=payload.auth_token,
        is_active=True,
        is_healthy=True,
        last_health_check=datetime.utcnow(),
    )

    db.add(new_agent)
    await db.commit()

    return {
        "message": "Agent registered successfully",
        "agent": payload.name
    }

@app.get("/agents/active", response_model=list[AgentResponse])
async def get_active_agents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AgentRegistry).where(
            AgentRegistry.is_active.is_(True),
            AgentRegistry.is_healthy.is_(True)
        )
    )

    agents = result.scalars().all()

    return agents



@asynccontextmanager
async def lifespan(app:FastAPI):

    task=asyncio.create_task(health_check_loop())
    logger.info("Health monitor start")

    yield

    task.cancel()

    logger.info("Health monitor stopped")


app=FastAPI(lifespan=lifespan)