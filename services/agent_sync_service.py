#services/agent_sync_service.py
import asyncio
import logging
from typing import Any

from agents.agent import root_agent
from services.agent_loader import fetch_active_agent_rows, build_agents_for_rows, deduplicate_runtime_agents

logger = logging.getLogger(__name__)

agent_lock = asyncio.Lock()


async def agent_sync_loop(session_manager: Any, interval: int = 10):
    """
    Keeps root_agent.sub_agents in sync with DB (active + healthy agents).

    Only fetches agent cards over HTTP for names that are genuinely new
    since the last poll — existing agents keep their already-built
    RemoteServerManager instance and are never re-fetched.
    """

    while True:
        try:
            rows = await fetch_active_agent_rows()   # DB only, no HTTP
            latest_names_by_row = {r.name: r for r in rows}
            latest_names = set(latest_names_by_row.keys())

            async with agent_lock:
                current_names = {a.name for a in root_agent.sub_agents}

                removed = current_names - latest_names
                added_names = latest_names - current_names

            # HTTP card fetches happen outside the lock, only for new rows
            added_rows = [latest_names_by_row[n] for n in added_names]
            new_agents = await build_agents_for_rows(added_rows, session_manager)

            async with agent_lock:
                updated_agents = [
                    a for a in root_agent.sub_agents
                    if a.name not in removed
                ]
                updated_agents.extend(new_agents)
                root_agent.sub_agents = deduplicate_runtime_agents(updated_agents)

            if removed:
                logger.info(f"🗑️ Removed agents: {list(removed)}")

            if added_names:
                logger.info(f"✅ Added agents: {list(added_names)}")

        except Exception as e:
            logger.error(f"❌ Agent sync failed: {e}")

        await asyncio.sleep(interval)
