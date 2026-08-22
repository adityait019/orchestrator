from fastapi import APIRouter, Depends, HTTPException,Header,Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import httpx
import os
from datetime import datetime,timezone
from agent_registry.schemas import AgentHeartbeat
from database.session import AsyncSessionLocal
from database.models import AgentRegistry
from agent_registry.schemas import AddAgentRequest, AgentResponse
from agents.agent import root_agent
from services.agent_loader import build_single_agent
import logging
from services.agent_runtime import agent_runtime_lock as agent_lock
from utils.compute_card_hash import compute_agent_card_hash
# logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


router = APIRouter(prefix="/agents", tags=["Agent Registry"])

def extract_agent_metadata(card: dict):

    try:
        params = (
            card["capabilities"]
            ["extensions"][0]
            ["params"]
        )

        return {
            "agent_id": params["agent_id"],
            "agent_type": params.get("agent_type"),
            "agent_version": params.get("version"),
        }

    except (KeyError, IndexError, TypeError):
        raise ValueError(
            "Invalid agent card structure"
        )


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

async def verify_admin_token(x_admin_token:str = Header(...)):
    MASTER_TOKEN = os.getenv("SECRET_KEY", "super-secret")

    if x_admin_token != MASTER_TOKEN:
        raise HTTPException(status_code=403,detail="Unauthorized")



@router.post("/add")
async def add_agent(
    payload: AddAgentRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin_token),
):

    agent_card_url = (
        f"http://{payload.host}:{payload.port}"
        "/.well-known/agent-card.json"
    )

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(agent_card_url)
            response.raise_for_status()

            agent_card = response.json()
            card_hash = compute_agent_card_hash(
                agent_card
            )

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=400,
            detail="Agent card endpoint timed out",
        )

    except httpx.HTTPError:
        raise HTTPException(
            status_code=400,
            detail="Failed to fetch agent card",
        )

    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid JSON from agent card endpoint",
        )

    # --------------------------------------------------
    # Validate agent card
    # --------------------------------------------------

    if "name" not in agent_card:
        raise HTTPException(
            status_code=400,
            detail="Agent card must contain a 'name' field",
        )

    if agent_card["name"] != payload.name:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Agent name in card does not match payload. "
                f"Expected '{agent_card['name']}'"
            ),
        )

    try:
        metadata = extract_agent_metadata(agent_card)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )

    agent_id = metadata["agent_id"]
    agent_type = metadata["agent_type"]
    agent_version = metadata["agent_version"]

    now = datetime.now(timezone.utc)

    # --------------------------------------------------
    # Check for endpoint reuse
    # --------------------------------------------------

    endpoint_result = await db.execute(
        select(AgentRegistry).where(
            AgentRegistry.host == payload.host,
            AgentRegistry.port == payload.port,
            AgentRegistry.is_active.is_(True),
        )
    )

    endpoint_owner = endpoint_result.scalar_one_or_none()

    if (
        endpoint_owner
        and endpoint_owner.agent_id != agent_id
    ):
        logger.warning(
            f"Endpoint {payload.host}:{payload.port} "
            f"reassigned from "
            f"{endpoint_owner.name} "
            f"({endpoint_owner.agent_id}) "
            f"to "
            f"{payload.name} "
            f"({agent_id})"
        )

        endpoint_owner.is_active = False
        endpoint_owner.is_healthy = False

        async with agent_lock:
            root_agent.sub_agents = [
                a
                for a in root_agent.sub_agents
                if a.name != endpoint_owner.name
            ]

    # --------------------------------------------------
    # Lookup by stable identity
    # --------------------------------------------------

    result = await db.execute(
        select(AgentRegistry).where(
            AgentRegistry.agent_id == agent_id
        )
    )

    existing = result.scalar_one_or_none()

    # ==================================================
    # UPDATE EXISTING AGENT
    # ==================================================

    if existing:
        old_version = existing.agent_version if existing else None
        old_hash = existing.agent_card_hash
        old_host = existing.host
        old_port = existing.port

        version_changed = (
            old_version is not None and old_version != agent_version
        )

        card_changed = (
            old_hash != card_hash
        )

        endpoint_changed = (
            old_host != payload.host
            or old_port != payload.port
        )
        metadata_changed = (
            version_changed
            or card_changed
            or endpoint_changed
        )

        if version_changed:
            logger.info(
                f"🚀 Agent upgraded {existing.name} "
                f"{old_version} -> {agent_version}"
            )

        if card_changed:
            logger.info(
                f"🔄 Agent card changed for "
                f"{existing.name}"
            )

        if endpoint_changed:
            logger.info(
                f"🌐 Agent endpoint changed for "
                f"{existing.name}: "
                f"{existing.host}:{existing.port} "
                f"-> "
                f"{payload.host}:{payload.port}")
            
        old_name = existing.name

        existing.name = payload.name
        existing.host = payload.host
        existing.port = payload.port

        existing.agent_type = agent_type
        existing.agent_version = agent_version

        existing.agent_card = agent_card

        existing.is_active = True
        existing.is_healthy = True

        existing.failure_count = 0
        existing.last_seen = now
        existing.last_health_check = now
        existing.next_health_check = None
        existing.agent_card_hash = card_hash

        await db.commit()
        await db.refresh(existing)

        #-------------------------------
        # Dynamically rebuild runtime agent if metadata changed
        #-------------------------------

        if metadata_changed:

            try:
                session_manager = request.app.state.session_manager

                async with agent_lock:
                    root_agent.sub_agents = [
                        a
                        for a in root_agent.sub_agents
                        if a.name != old_name
                    ]

                agent_instance = await build_single_agent(
                    existing,
                    session_manager=session_manager,
                )

                if agent_instance is not None:
                    async with agent_lock:
                        root_agent.sub_agents.append(
                            agent_instance
                        )

                    logger.info(
                        f"✅ Agent {existing.name} "
                        f"runtime rebuilt"
                    )

                else:
                    logger.warning(
                        f"⚠️ Unable to rebuild "
                        f"{existing.name}"
                    )

            except Exception as e:
                logger.warning(
                    f"⚠️ Failed to rebuild "
                    f"{existing.name}: {e}"
                )

        else:
            logger.info(
                f"ℹ️ Agent {existing.name} "
                f"heartbeat/re-registration received. "
                f"No metadata changes detected."
            )
        return {
            "message":
                f"Agent '{existing.name}' updated successfully"
        }

    # ==================================================
    # CREATE NEW AGENT
    # ==================================================

    new_agent = AgentRegistry(
        agent_id=agent_id,

        name=payload.name,

        host=payload.host,
        port=payload.port,

        agent_type=agent_type,
        agent_version=agent_version,

        is_active=True,
        is_healthy=True,

        failure_count=0,

        last_seen=now,
        last_health_check=now,

        agent_card=agent_card,
        agent_card_hash=card_hash,
        created_at=now,
    )

    db.add(new_agent)

    await db.commit()
    await db.refresh(new_agent)

    # ------------------------------------------
    # Dynamically load runtime agent
    # ------------------------------------------

    try:
        session_manager = request.app.state.session_manager

        agent_instance = await build_single_agent(
            new_agent,
            session_manager=session_manager,
        )

        existing_names = {
            a.name
            for a in root_agent.sub_agents
        }

        if (
            agent_instance
            and new_agent.name not in existing_names
        ):
            async with agent_lock:
                root_agent.sub_agents.append(
                    agent_instance
                )

            logger.info(
                f"✅ Agent {new_agent.name} "
                f"added dynamically"
            )

        else:
            logger.warning(
                f"⚠️ Agent {new_agent.name} "
                f"already exists in runtime"
            )

    except Exception as e:
        logger.warning(
            f"⚠️ Failed to dynamically attach agent: {e}"
        )

    return {
        "message": "Agent registered successfully"
    }

#=======================================
# HEARTBEAT ENDPOINT
#=======================================

@router.post("/heartbeat")
async def heartbeat(
    payload: AgentHeartbeat,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(AgentRegistry).where(
            AgentRegistry.agent_id == payload.agent_id
        )
    )

    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(
            404,
            "Agent not found"
        )
    if (
        payload.version
        and agent.agent_version
        and payload.version != agent.agent_version
    ):
        logger.warning(
            f"Version mismatch for {agent.name}: "
            f"registry={agent.agent_version}, "
            f"heartbeat={payload.version}"
        )


    now = datetime.now(timezone.utc)

    agent.last_seen = now
    agent.last_health_check = now
    agent.is_healthy = True

    agent.failure_count = 0
    agent.next_health_check = None

    await db.commit()

    return {"status": "ok"}


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
    request:Request,
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
        session_manager = request.app.state.session_manager
        agent_instance = await build_single_agent(agent, session_manager=session_manager)

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

@router.get("/total_agents", response_model=list[AgentResponse])
async def get_all_agents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AgentRegistry)
    )
    return result.scalars().all()



@router.delete("/agent_registry/{agent_name}")
async def delete_agent(
    agent_name: str,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin_token),
):
    # Fetch agent
    result = await db.execute(
        select(AgentRegistry).where(AgentRegistry.name == agent_name)
    )
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Remove from orchestrator (in-memory)
    async with agent_lock:
        root_agent.sub_agents = [
            a for a in root_agent.sub_agents
            if a.name != agent_name
        ]

    # Permanently delete from DB
    await db.delete(agent)
    await db.commit()

    logger.info(f"🗑️ Agent '{agent_name}' permanently deleted from database")

    return {
        "message": f"Agent '{agent_name}' deleted permanently"
    }