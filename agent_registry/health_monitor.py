import asyncio
import httpx
from datetime import datetime,timezone, timedelta
from sqlalchemy import select
from database.session import AsyncSessionLocal
from database.models import AgentRegistry
import logging

logger = logging.getLogger(__name__)


HEARTBEAT_STALE_SECONDS = 90


async def health_check_loop():
    while True:
        try:
            async with AsyncSessionLocal() as db:

                result = await db.execute(
                    select(AgentRegistry).where(
                        AgentRegistry.is_active.is_(True)
                    )
                )

                agents = result.scalars().all()

                now = datetime.now(timezone.utc)

                async with httpx.AsyncClient(timeout=3.0) as client:

                    for agent in agents:

                        previous_health = agent.is_healthy

                        # ==================================================
                        # HEARTBEAT IS PRIMARY SOURCE OF TRUTH
                        # ==================================================

                        if agent.last_seen:

                            age_seconds = (
                                now - agent.last_seen
                            ).total_seconds()

                            # Recent heartbeat -> healthy
                            if age_seconds < HEARTBEAT_STALE_SECONDS:

                                if not agent.is_healthy:
                                    logger.info(
                                        f"[HEALTH CHANGE] "
                                        f"{agent.name} → UP "
                                        f"(heartbeat)"
                                    )

                                agent.is_healthy = True
                                agent.failure_count = 0
                                agent.next_health_check = None
                                agent.last_health_check = now

                                continue

                        # ==================================================
                        # BACKOFF
                        # ==================================================

                        if (
                            agent.next_health_check
                            and now < agent.next_health_check
                        ):
                            continue

                        # ==================================================
                        # FALLBACK VERIFICATION
                        # ==================================================

                        base_url = (
                            f"http://{agent.host}:{agent.port}"
                        )

                        health_url = (
                            f"{base_url}/health"
                        )

                        try:

                            resp = await client.get(
                                health_url
                            )

                            is_healthy = (
                                resp.status_code == 200
                            )

                            if is_healthy:

                                agent.is_healthy = True

                                agent.last_seen = now
                                agent.last_health_check = now

                                agent.failure_count = 0
                                agent.next_health_check = None

                            else:

                                agent.is_healthy = False

                        except httpx.ConnectError:

                            agent.is_healthy = False

                        except Exception:

                            logger.exception(
                                "Unexpected health check "
                                f"error for {agent.name}"
                            )

                            agent.is_healthy = False

                        # ==================================================
                        # FAILURE HANDLING
                        # ==================================================

                        if not agent.is_healthy:

                            agent.failure_count += 1

                            delay = min(
                                900,  # max 15 min
                                10 * (
                                    2 ** agent.failure_count
                                )
                            )

                            agent.next_health_check = (
                                now
                                + timedelta(
                                    seconds=delay
                                )
                            )

                            agent.last_health_check = now

                        # ==================================================
                        # STATE CHANGE LOGGING
                        # ==================================================

                        if (
                            previous_health
                            and not agent.is_healthy
                        ):
                            logger.warning(
                                f"[HEALTH CHANGE] "
                                f"{agent.name} → DOWN"
                            )

                        elif (
                            not previous_health
                            and agent.is_healthy
                        ):
                            logger.info(
                                f"[HEALTH CHANGE] "
                                f"{agent.name} → UP"
                            )

                await db.commit()

        except Exception:
            logger.exception(
                "Health check loop crashed"
            )

        await asyncio.sleep(10)