from fastapi import APIRouter, Depends, HTTPException,Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import httpx
import os
from datetime import datetime,timezone

from database.session import AsyncSessionLocal
from database.models import AgentRegistry
from agent_registry.schemas import AddAgentRequest, AgentResponse
from agents.agent import root_agent
from services.agent_loader import build_single_agent
import logging
import asyncio

agent_lock = asyncio.Lock()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


router = APIRouter(prefix="/agents", tags=["Agent Registry"])

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

async def verify_admin_token(x_admin_token:str = Header(...)):
    MASTER_TOKEN = os.getenv("SECRET_KEY", "super-secret")

    if x_admin_token != MASTER_TOKEN:
        raise HTTPException(status_code=403,detail="Unauthorized")

@router.post("/add")
async def add_agent(payload: AddAgentRequest, db: AsyncSession = Depends(get_db),_:None =Depends(verify_admin_token) ):


    agent_card_url = f"http://{payload.host}:{payload.port}/.well-known/agent-card.json"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(agent_card_url)
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

    result = await db.execute(select(AgentRegistry).where(AgentRegistry.name == payload.name,AgentRegistry.host==payload.host,AgentRegistry.port==payload.port))
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(status_code=400, detail="Agent already registered")


    now=datetime.now(timezone.utc)
    new_agent = AgentRegistry(
        name=payload.name,
        host=payload.host,
        port=payload.port,
        is_active=True,
        is_healthy=True,
        agent_card=agent_card,
        created_at=now,
        last_health_check=now,
    )

    db.add(new_agent)
    await db.commit()
    await db.refresh(new_agent)

    # 🔥 Dynamically load into root agent
    try:
        agent_instance = await build_single_agent(new_agent)

        existing_names = {a.name for a in root_agent.sub_agents}

        if agent_instance and new_agent.name not in existing_names:
            async with agent_lock:
                root_agent.sub_agents.append(agent_instance)
            logger.info(f"✅ Agent {new_agent.name} added dynamically")
        else:
            logger.warning(f"⚠️ Agent {new_agent.name} already exists in runtime")

    except Exception as e:
        logger.warning(f"⚠️ Failed to dynamically attach agent: {e}")

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

    # Remove from root agent
    async with agent_lock:
        root_agent.sub_agents = [
            a for a in root_agent.sub_agents
            if a.name != agent_name
        ]
    await db.commit()
    logger.info(f"✅ Agent '{agent_name}' deactivated and removed from orchestrator")
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


    agent.is_active = True
    await db.commit()
    await db.refresh(agent)

    try:
        agent_instance = await build_single_agent(agent)

        existing_names = {a.name for a in root_agent.sub_agents}

        if agent_instance and agent.name not in existing_names:
            async with agent_lock:
                root_agent.sub_agents.append(agent_instance)
            logger.info(f"✅ Agent {agent.name} activated and added to orchestrator")

    except Exception as e:
        logger.warning(f"⚠️ Failed to attach activated agent: {e}")

    return{
        "message": f"Agent '{agent_name}' activated successfully"
    }