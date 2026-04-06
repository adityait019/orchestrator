import asyncio
import logging
from agents.agent import root_agent
from services.agent_loader import load_active_agents

logger = logging.getLogger(__name__)

agent_lock = asyncio.Lock()


async def agent_sync_loop(interval: int = 10):
    """
    Keeps root_agent.sub_agents in sync with DB (active + healthy agents)
    """

    while True:
        try:
            latest_agents = await load_active_agents()

            latest_map = {a.name: a for a in latest_agents}

            async with agent_lock:
                current_map = {a.name: a for a in root_agent.sub_agents}

                current_names = set(current_map.keys())
                latest_names = set(latest_map.keys())

                # 🔴 Agents to remove
                removed = current_names - latest_names

                # 🟢 Agents to add
                added = latest_names - current_names

                # ✅ Build new list (atomic update)
                updated_agents = [
                    a for a in root_agent.sub_agents
                    if a.name not in removed
                ]

                for name in added:
                    updated_agents.append(latest_map[name])

                # 🔁 Replace in one shot (safe)
                root_agent.sub_agents = updated_agents

            # Logging outside lock
            if removed:
                logger.info(f"🗑️ Removed agents: {list(removed)}")

            if added:
                logger.info(f"✅ Added agents: {list(added)}")

        except Exception as e:
            logger.error(f"❌ Agent sync failed: {e}")

        await asyncio.sleep(interval)