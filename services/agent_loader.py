# loaders/agents_loader.py

import logging
import asyncio
from typing import Any, Dict, Optional, List, cast
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from a2a.client.card_resolver import A2ACardResolver

from database.session import AsyncSessionLocal
from database.models import AgentRegistry

from agents.remote_agent_connections import RemoteServerManager
from google.adk.agents import BaseAgent   # ✅ ADD THIS
from infrastructure.a2a_factory import a2a_client_factory
from utils.agent_card_extractor import extract_description_capabilities_skills

logger = logging.getLogger(__name__)

AGENT_CARD_PATH = "/.well-known/agent-card.json"

MAX_CONCURRENT_AGENT_LOADS = 5
AGENT_CARD_TIMEOUT = 30.0


async def _resolve_agent_card_json(
    agent_card_url: str,
    httpx_client: httpx.AsyncClient,
) -> Dict[str, Any]:
    parsed = urlparse(agent_card_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid agent card URL: {agent_card_url}")

    base_url = f"{parsed.scheme}://{parsed.netloc}"
    rel_path = parsed.path or AGENT_CARD_PATH

    resolver = A2ACardResolver(
        httpx_client=httpx_client,
        base_url=base_url,
    )
    agent_card = await resolver.get_agent_card(relative_card_path=rel_path)
    return agent_card.model_dump(exclude_none=True, by_alias=True)


# ---------------------------------------------------------------------
# FINAL optimized loader (TYPE-SAFE)
# ---------------------------------------------------------------------
async def load_active_agents() -> List[BaseAgent]:
    """
    Optimized remote agent loader.

    ✅ Parallel loading with bounded concurrency
    ✅ Single shared HTTP client
    ✅ Returns List[BaseAgent] (type-safe)
    ✅ Safe for 20+ agents
    """

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AgentRegistry).where(
                AgentRegistry.is_active.is_(True),
                AgentRegistry.is_healthy.is_(True),
            )
        )
        rows = result.scalars().all()

    if not rows:
        logger.info("No active remote agents found.")
        return []

    cfg = getattr(a2a_client_factory, "_config", None)
    shared_httpx = getattr(cfg, "httpx_client", None)

    if shared_httpx is None:
        shared_httpx = httpx.AsyncClient(
            timeout=httpx.Timeout(AGENT_CARD_TIMEOUT)
        )
        if cfg is not None:
            a2a_client_factory._config = cfg.copy(
                update={"httpx_client": shared_httpx}
            )

    sem = asyncio.Semaphore(MAX_CONCURRENT_AGENT_LOADS)
    completed = 0
    completed_lock = asyncio.Lock()

    async def _build_agent(a: AgentRegistry) -> Optional[RemoteServerManager]:
        nonlocal completed

        async with sem:
            agent_card_url = f"http://{a.host}:{a.port}{AGENT_CARD_PATH}"

            try:
                card_dict = await _resolve_agent_card_json(
                    agent_card_url,
                    httpx_client=shared_httpx,
                )
            except Exception as ex:
                logger.warning(
                    "Failed to fetch agent card for %s (%s): %s",
                    a.name,
                    agent_card_url,
                    ex,
                )
                card_dict = {}

            description, capabilities, skills, skills_full = (
                extract_description_capabilities_skills(card_dict)
            )

            agent = RemoteServerManager(
                name=a.name,
                agent_card=agent_card_url,
                a2a_client_factory=a2a_client_factory,
                description=description,
            )

            agent._capabilities = capabilities
            agent._skills = skills
            agent._skills_full = skills_full

            async with completed_lock:
                completed += 1
                logger.info(
                    "Loaded agent %d/%d: %s",
                    completed,
                    len(rows),
                    a.name,
                )

            return agent

    results = await asyncio.gather(
        *[_build_agent(a) for a in rows],
        return_exceptions=False,
    )

    # ✅ The critical fix: cast to List[BaseAgent]
    agents: List[BaseAgent] = cast(
        List[BaseAgent],
        [a for a in results if a is not None],
    )

    logger.info("✅ Finished loading %d remote agents.", len(agents))
    return agents