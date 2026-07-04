import asyncio
import httpx
from datetime import datetime,timezone
from sqlalchemy import select
from database.session import AsyncSessionLocal
from database.models import AgentRegistry
import logging

logger = logging.getLogger(__name__)

AGENT_CARD_ENDPOINT = "/.well-known/agent-card.json"

async def health_check_loop():
    while True:
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(AgentRegistry))
                agents = result.scalars().all()

                async with httpx.AsyncClient(timeout=3.0) as client:
                    for agent in agents:
                        # -----------------------------
                        # URLs
                        # -----------------------------
                        base_url = f"http://{agent.host}:{agent.port}"
                        health_url = f"{base_url}/health"
                        card_url = f"{base_url}{AGENT_CARD_ENDPOINT}"

                        previous_health = agent.is_healthy
                        previous_active = agent.is_active

                        # -----------------------------
                        # ✅ 1. HEALTH CHECK
                        # -----------------------------
                        try:
                            health_resp = await client.get(health_url)
                            is_healthy = health_resp.status_code == 200
                        except Exception as e:
                            logger.error(f"[Health] {agent.name}: {e}")
                            is_healthy = False

                        # -----------------------------
                        # ✅ 2. AGENT CARD CHECK
                        # -----------------------------
                        try:
                            card_resp = await client.get(card_url)
                            is_active = card_resp.status_code == 200
                        except Exception as e:
                            logger.error(f"[AgentCard] {agent.name}: {e}")
                            is_active = False

                        # -----------------------------
                        # ✅ LOG CHANGES
                        # -----------------------------
                        if previous_health != is_healthy:
                            logger.info(
                                f"[HEALTH CHANGE] {agent.name} → {'UP' if is_healthy else 'DOWN'}"
                            )

                        if previous_active != is_active:
                            logger.info(
                                f"[ACTIVE CHANGE] {agent.name} → {'ACTIVE' if is_active else 'INACTIVE'}"
                            )

                        # -----------------------------
                        # ✅ UPDATE DB ONLY IF NEEDED
                        # -----------------------------
                        if previous_health != is_healthy:
                            agent.is_healthy = is_healthy

                        if previous_active != is_active:
                            agent.is_active = is_active

                        # Always update timestamp
                        agent.last_health_check = datetime.now(timezone.utc)

                await db.flush()
                await db.commit()

        except Exception:
            logger.exception("Health check loop crashed")

        await asyncio.sleep(10)