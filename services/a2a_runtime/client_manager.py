# services/a2a_runtime/client_manager.py

from __future__ import annotations

import logging
from urllib.parse import urlparse

import httpx

from a2a.client.card_resolver import A2ACardResolver
from a2a.client.client import Client, ClientConfig
from a2a.client.client_factory import ClientFactory
from a2a.types import AgentCard, TransportProtocol

logger = logging.getLogger(__name__)


class A2AClientManager:
    """
    Owns A2A AgentCard resolution and A2A client caching.

    Depends only on:
    - a2a-sdk
    - httpx

    No Google ADK dependency.
    """

    def __init__(
        self,
        *,
        httpx_client: httpx.AsyncClient | None = None,
        client_factory: ClientFactory | None = None,
        timeout: float = 600.0,
    ):
        self._httpx_client = httpx_client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout=timeout)
        )

        self._owns_httpx = httpx_client is None

        if client_factory is not None:
            self._client_factory = client_factory
        else:
            config = ClientConfig(
                httpx_client=self._httpx_client,
                supported_transports=[
                    TransportProtocol.jsonrpc,
                    TransportProtocol.http_json,
                ],
            )
            self._client_factory = ClientFactory(config)

        self._cards: dict[str, AgentCard] = {}
        self._clients: dict[str, Client] = {}

    async def resolve_card(self, agent_card_url: str) -> AgentCard:
        if agent_card_url in self._cards:
            return self._cards[agent_card_url]

        parsed = urlparse(agent_card_url)

        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"Invalid agent card URL: {agent_card_url}")

        base_url = f"{parsed.scheme}://{parsed.netloc}"
        relative_path = parsed.path or "/.well-known/agent-card.json"

        resolver = A2ACardResolver(
            httpx_client=self._httpx_client,
            base_url=base_url,
        )

        card = await resolver.get_agent_card(
            relative_card_path=relative_path
        )

        self._cards[agent_card_url] = card

        logger.info(
            "[A2A CARD RESOLVED] name=%s url=%s",
            getattr(card, "name", None),
            agent_card_url,
        )

        return card

    async def get_client(self, agent_card_url: str) -> Client:
        if agent_card_url in self._clients:
            return self._clients[agent_card_url]

        card = await self.resolve_card(agent_card_url)
        client = self._client_factory.create(card)

        self._clients[agent_card_url] = client

        logger.info(
            "[A2A CLIENT CREATED] agent=%s",
            getattr(card, "name", None),
        )

        return client

    async def close(self):
        if self._owns_httpx:
            await self._httpx_client.aclose()