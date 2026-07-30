# services/agents_loader.py

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
from google.adk.agents import BaseAgent
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


def _get_shared_httpx() -> httpx.AsyncClient:
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

    return shared_httpx


# ---------------------------------------------------------------------
# Row-level fetch — cheap, DB only, no HTTP. Used by both the bulk
# startup loader and the sync loop's diffing step.
# ---------------------------------------------------------------------
async def fetch_active_agent_rows() -> List[AgentRegistry]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AgentRegistry).where(
                AgentRegistry.is_active.is_(True),
                AgentRegistry.is_healthy.is_(True),
            )
        )
        return list(result.scalars().all())


# ---------------------------------------------------------------------
# Row -> RemoteServerManager. This is the part that does the network
# call (agent card fetch) — only call it for rows you actually need
# to (re)build.
# ---------------------------------------------------------------------
async def build_agents_for_rows(
    rows: List[AgentRegistry],
    session_manager: Any,
    shared_httpx: Optional[httpx.AsyncClient] = None,
) -> List[BaseAgent]:
    if not rows:
        return []

    shared_httpx = shared_httpx or _get_shared_httpx()

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
                session_manager=session_manager,
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

    return cast(
        List[BaseAgent],
        [a for a in results if a is not None],
    )


# ---------------------------------------------------------------------
# FINAL optimized loader — startup path, builds everything.
# ---------------------------------------------------------------------
async def load_active_agents(session_manager: Any) -> List[BaseAgent]:
    """
    Full bulk load — used once at startup. Fetches + builds every
    active/healthy agent. The sync loop should NOT call this on every
    poll; use fetch_active_agent_rows() + build_agents_for_rows() for
    incremental updates instead.
    """
    rows = await fetch_active_agent_rows()

    if not rows:
        logger.info("No active remote agents found.")
        return []

    shared_httpx = _get_shared_httpx()
    agents = await build_agents_for_rows(rows, session_manager, shared_httpx)

    logger.info("✅ Finished loading %d remote agents.", len(agents))
    return agents


async def build_single_agent(agent_row, session_manager: Any) -> Optional[BaseAgent]:
    import httpx

    agent_card_url = f"http://{agent_row.host}:{agent_row.port}/.well-known/agent-card.json"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            card_dict = await _resolve_agent_card_json(
                agent_card_url,
                httpx_client=client,
            )
    except Exception as ex:
        logger.warning(f"Failed to load agent {agent_row.name}: {ex}")
        return None

    description, capabilities, skills, skills_full = (
        extract_description_capabilities_skills(card_dict)
    )

    agent = RemoteServerManager(
        name=agent_row.name,
        agent_card=agent_card_url,
        a2a_client_factory=a2a_client_factory,
        description=description,
        session_manager=session_manager,
    )

    agent._capabilities = capabilities
    agent._skills = skills
    agent._skills_full = skills_full

    return agent