import asyncio
import httpx
from datetime import datetime,timezone
from sqlalchemy import select
from database.session import AsyncSessionLocal
from database.models import AgentRegistry
import logging

async def health_check_loop():
    while True:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(AgentRegistry))
            agents = result.scalars().all()

            for agent in agents:
                previous_status = agent.is_healthy
                url = f"http://{agent.host}:{agent.port}/health"

                try:
                    async with httpx.AsyncClient(timeout=3.0) as client:
                        response = await client.get(url)
                        current_status = response.status_code == 200
                except Exception:
                    current_status = False

                if previous_status != current_status:
                    logging.info(
                        f"[HEALTH CHANGE] {agent.name} → {'UP' if current_status else 'DOWN'}"
                    )

                agent.is_healthy = current_status
                agent.last_health_check = datetime.now(timezone.utc)

            await db.commit()

        await asyncio.sleep(10)