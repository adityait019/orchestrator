from fastapi import APIRouter, Depends, HTTPException,Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import httpx
import os
from datetime import datetime,timezone

from database.session import AsyncSessionLocal
from database.models import AgentRegistry
from agent_registry.schemas import AddAgentRequest, AgentResponse

router = APIRouter(prefix="/agents", tags=["Agent Registry"])

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

async def verify_admin_token(x_admin_token:str = Header(...)):
    MASTER_TOKEN = os.getenv("MASTER_AGENT_TOKEN", "super-secret")

    if x_admin_token != MASTER_TOKEN:
        raise HTTPException(status_code=403,detail="Unauthorized")

@router.post("/add")
async def add_agent(payload: AddAgentRequest, db: AsyncSession = Depends(get_db),_:None =Depends(verify_admin_token) ):


    agent_card_url = f"http://{payload.host}:{payload.port}/.well-known/agent-card.json"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(agent_card_url)
            if response.status_code != 200:
                raise HTTPException(status_code=400, detail="Invalid agent card endpoint")
    except Exception:
        raise HTTPException(status_code=400, detail="Agent not reachable")

    result = await db.execute(select(AgentRegistry).where(AgentRegistry.name == payload.name,AgentRegistry.host==payload.host,AgentRegistry.port==payload.port))
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(status_code=400, detail="Agent already registered")

    new_agent = AgentRegistry(
        name=payload.name,
        host=payload.host,
        port=payload.port,
        is_active=True,
        is_healthy=True,
        created_at=datetime.now(timezone.utc),
        last_health_check=datetime.now(timezone.utc),
    )

    db.add(new_agent)
    await db.commit()

    return {"message": "Agent registered successfully"}


@router.get("/active", response_model=list[AgentResponse])
async def get_active_agents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AgentRegistry).where(
            AgentRegistry.is_active.is_(True),
            AgentRegistry.is_healthy.is_(True)
        )
    )
    return result.scalars().all()


@router.delete("/{agent_name}")
async def deactivate_agent(
    agent_name:str,
    db: AsyncSession =Depends(get_db),
    _:None =Depends(verify_admin_token),

):
    result=await db.execute(
        select(AgentRegistry).where(AgentRegistry.name== agent_name)
    )
    agent=result.scalar_one_or_none()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent.is_active=False
    agent.is_healthy=False
    await db.commit()
    return{
        "message":f"Agent '{agent_name}' deactivated successfully"
    }



@router.patch("/{agent_name}/activate")
async def activate_agent(
    agent_name:str,
    db:AsyncSession =Depends(get_db),
    _: None =Depends(verify_admin_token)
):
    result=await db.execute(
        select(AgentRegistry).where(AgentRegistry.name== agent_name)
    )
    
    agent=result.scalar_one_or_none()

    if not agent:
        raise HTTPException(status_code=404,detail="Agent not found")

    agent.is_active=True
    await db.commit()

    return{
        "message": f"Agent '{agent_name}' activated successfully"
    }