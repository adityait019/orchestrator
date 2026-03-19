# loaders/agents_loader.py

from sqlalchemy import select
from database.session import AsyncSessionLocal
from database.models import AgentRegistry
from agents.remote_agent_connections import RemoteServerManager
from infrastructure.a2a_factory import a2a_client_factory

from a2a.client.card_resolver import A2ACardResolver
from urllib.parse import urlparse
import httpx
import logging
from typing import Any, Dict, Optional
import asyncio
from utils.agent_card_extractor import extract_description_capabilities_skills

logger = logging.getLogger(__name__)

AGENT_CARD_PATH = "/.well-known/agent-card.json"


async def _resolve_agent_card_json(
    agent_card_url: str,
    httpx_client: Optional[httpx.AsyncClient] = None,
) -> Dict[str, Any]:
    parsed = urlparse(agent_card_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid agent card URL: {agent_card_url}")

    base_url = f"{parsed.scheme}://{parsed.netloc}"
    rel_path = parsed.path or AGENT_CARD_PATH

    own_client = False
    if httpx_client is None:
        httpx_client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        own_client = True

    try:
        resolver = A2ACardResolver(httpx_client=httpx_client, base_url=base_url)
        agent_card = await resolver.get_agent_card(relative_card_path=rel_path)
        return agent_card.model_dump(exclude_none=True, by_alias=True)
    finally:
        if own_client:
            try:
                await httpx_client.aclose()
            except Exception:
                pass


async def load_active_agents():
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AgentRegistry).where(
                AgentRegistry.is_active.is_(True),
                AgentRegistry.is_healthy.is_(True),
            )
        )
        rows = result.scalars().all()

    dynamic_agents = []

    # Reuse the HTTP client from the factory if available
    shared_httpx = getattr(getattr(a2a_client_factory, "_config", None), "httpx_client", None)

    for a in rows:
        agent_card_url = f"http://{a.host}:{a.port}{AGENT_CARD_PATH}"

        try:
            card_dict = await _resolve_agent_card_json(agent_card_url, httpx_client=shared_httpx)
        except Exception as ex:
            logger.warning("Failed to fetch agent card for %s (%s): %s", a.name, agent_card_url, ex)
            card_dict = {}

        description, capabilities, skills, skills_full = extract_description_capabilities_skills(card_dict)

        # Build the agent and attach metadata
        agent = RemoteServerManager(
            name=a.name,
            agent_card=agent_card_url,
            a2a_client_factory=a2a_client_factory,
        )
         # optional: handy for admin screens

        agent.description=description
        agent._capabilities=capabilities
        agent._skills=skills
        agent._skills_full=skills_full

        dynamic_agents.append(agent)
        await asyncio.sleep(2)
    return dynamic_agents