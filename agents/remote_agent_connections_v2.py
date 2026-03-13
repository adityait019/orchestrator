# remote_server_manager.py
from __future__ import annotations

import dataclasses
import json
import logging
import uuid
from pathlib import Path
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Optional,
    Sequence,
    Tuple,
    MutableMapping,
    cast,
)
from urllib.parse import urlparse

import httpx

from a2a.client.client import ClientConfig as A2AClientConfig
from a2a.client.client_factory import ClientFactory as A2AClientFactory
from a2a.client.card_resolver import A2ACardResolver
from a2a.client.middleware import ClientCallContext
from a2a.types import (
    AgentCard,
    Message as A2AMessage,
    Part as A2APart,
    Role,
    Task,
    TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent,
    TextPart,
    FilePart,
    DataPart,
)

from google.adk.agents.remote_a2a_agent import RemoteA2aAgent

logger = logging.getLogger(__name__)

# Stream/update aliases
UpdateEvent = TaskStatusUpdateEvent | TaskArtifactUpdateEvent | None
ClientEvent = Tuple[Task, UpdateEvent]

# Type for a function that converts "your" part -> A2A Part (RootModel)
PartConverter = Callable[[Any], list[A2APart] | A2APart | None]
# Extract context_id from your session events (optional)
ContextIdExtractor = Callable[[Sequence[Any]], Optional[str]]
# Adapt A2A response into whatever your app expects
ResponseAdapter = Callable[[ClientEvent | A2AMessage], Any]


@dataclasses.dataclass
class RemoteServerConfig:
    """Configuration for RemoteServerManager."""
    timeout: float = 600.0
    streaming: bool = False                 # Let server handle streaming if it can
    polling: bool = False
    supported_transports: list[str] = dataclasses.field(
        default_factory=lambda: ["JSONRPC"]
    )
    use_client_preference: bool = False
    accepted_output_modes: list[str] = dataclasses.field(default_factory=list)


class RemoteServerManager(RemoteA2aAgent):
    """
    A2A Remote Manager.

    Responsibilities:
      - Resolve AgentCard (URL or file)
      - Initialize A2A client via ClientFactory
      - Send messages either from explicit A2A Part(s) or from the last user event
      - Optional orchestration-noise filtering
      - Optional response adapter for your app's event model
    """

    def __init__(
        self,
        *args,
        name: str,
        agent_card: AgentCard | str,
        description: str = "",
        httpx_client: Optional[httpx.AsyncClient] = None,
        client_factory: Optional[A2AClientFactory] = None,
        config: Optional[RemoteServerConfig] = None,
        # Converters/adapters you can inject from your app:
        genai_part_converter: Optional[PartConverter] = None,
        context_id_extractor: Optional[ContextIdExtractor] = None,
        response_adapter: Optional[ResponseAdapter] = None,
        # Outbound filtering/logging
        filter_orchestration_noise: bool = True,
        text_preview_len: int = 160,
        max_text_previews: int = 6,
        **kwargs,
    ) -> None:
        super().__init__(*args,**kwargs)
        self.name = name
        self.description = description

        self._agent_card_input = agent_card
        self._agent_card: Optional[AgentCard] = agent_card if isinstance(agent_card, AgentCard) else None

        self._httpx_client = httpx_client
        self._owns_httpx = httpx_client is None

        self._config = config or RemoteServerConfig()
        self._client_factory = client_factory
        self._a2a_client = None  # set after ensure_ready
        self._resolved = False

        self._genai_part_converter = genai_part_converter
        self._context_id_extractor = context_id_extractor
        self._response_adapter = response_adapter

        self._filter_orchestration_noise = filter_orchestration_noise
        self._text_preview_len = text_preview_len
        self._max_text_previews = max_text_previews

    # ------------------------------
    # Lifecycle / resolution
    # ------------------------------
    async def _ensure_httpx_client(self) -> httpx.AsyncClient:
        if not self._httpx_client:
            self._httpx_client = httpx.AsyncClient(
                timeout=httpx.Timeout(timeout=self._config.timeout)
            )
            self._owns_httpx = True
        return self._httpx_client

    async def _ensure_factory(self) -> A2AClientFactory:
        await self._ensure_httpx_client()
        if self._client_factory is None:
            cc = A2AClientConfig(
                httpx_client=self._httpx_client,
                streaming=self._config.streaming,
                polling=self._config.polling,
                supported_transports=self._config.supported_transports,
                use_client_preference=self._config.use_client_preference,
                accepted_output_modes=self._config.accepted_output_modes,
            )
            self._client_factory = A2AClientFactory(config=cc)
        return self._client_factory

    async def _resolve_agent_card_from_url(self, url: str) -> AgentCard:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"Invalid agent card URL: {url}")

        base_url = f"{parsed.scheme}://{parsed.netloc}"
        rel_path = parsed.path or "/.well-known/agent.json"

        httpx_client = await self._ensure_httpx_client()
        resolver = A2ACardResolver(httpx_client=httpx_client, base_url=base_url)
        return await resolver.get_agent_card(relative_card_path=rel_path)

    def _resolve_agent_card_from_file(self, file_path: str) -> AgentCard:
        p = Path(file_path)
        if not p.exists() or not p.is_file():
            raise FileNotFoundError(f"Agent card not found: {file_path}")
        data = json.loads(p.read_text(encoding="utf-8"))
        return AgentCard(**data)

    async def _resolve_agent_card(self) -> AgentCard:
        if self._agent_card:
            return self._agent_card

        if not isinstance(self._agent_card_input, str):
            raise ValueError("agent_card must be AgentCard or str (URL or file path)")

        s = self._agent_card_input.strip()
        if s.startswith(("http://", "https://")):
            self._agent_card = await self._resolve_agent_card_from_url(s)
        else:
            self._agent_card = self._resolve_agent_card_from_file(s)

        if not self._agent_card.url:
            raise ValueError("Resolved AgentCard has no RPC URL")
        if not urlparse(str(self._agent_card.url)).scheme:
            raise ValueError(f"AgentCard has invalid RPC URL: {self._agent_card.url}")

        if not self.description and getattr(self._agent_card, "description", None):
            self.description = self._agent_card.description

        return self._agent_card

    async def ensure_ready(self) -> None:
        """Resolve card & create A2A client."""
        if self._resolved and self._a2a_client is not None:
            return
        card = await self._resolve_agent_card()
        factory = await self._ensure_factory()
        self._a2a_client = factory.create(card)
        if self._a2a_client is None:
            raise RuntimeError("Failed to create A2A client")
        self._resolved = True
        logger.info("RemoteServerManager '%s' ready (agent: %s)", self.name, getattr(card, "name", None))

    async def close(self) -> None:
        """Close owned HTTP client if created by this manager."""
        if self._owns_httpx and self._httpx_client:
            try:
                await self._httpx_client.aclose()
            finally:
                self._httpx_client = None

    # ------------------------------
    # Helpers
    # ------------------------------
    def _is_noise_text(self, s: str) -> bool:
        s = (s or "").strip()
        return (
            s.startswith("For context:")
            or s.startswith("[Cortex]")
            or s.startswith("[Tool]")
            or "`transfer_to_agent`" in s
        )

    def _shorten_uri(self, uri: str, keep_tail: int = 36) -> str:
        try:
            u = urlparse(uri)
            path = u.path or ""
            tail = path[-keep_tail:] if len(path) > keep_tail else path
            base = f"{u.scheme}://{u.netloc}" if (u.scheme and u.netloc) else ""
            return f"{base}/…{tail}"
        except Exception:
            return (uri[:keep_tail] + "…") if len(uri) > keep_tail else uri

    def _summarize_parts_for_log(self, parts: list[A2APart]) -> str:
        text_parts = 0
        file_parts = 0
        text_previews: list[str] = []
        file_previews: list[str] = []

        for p in parts:
            root = p.root
            if isinstance(root, TextPart):
                t = (root.text or "").strip()
                if t:
                    text_parts += 1
                    one = " ".join(t.split())
                    prev = (one[: self._text_preview_len] + "…") if len(one) > self._text_preview_len else one
                    if len(text_previews) < self._max_text_previews:
                        text_previews.append(f"- {prev}")
            elif isinstance(root, FilePart):
                file_parts += 1
                uri = getattr(root.file, "uri", None)
                mime = getattr(root.file, "mime_type", None)
                if uri:
                    file_previews.append(f"- {mime or 'unknown'} | { self._shorten_uri(uri) }")
            elif isinstance(root, DataPart):
                # DataPart: count as text preview of JSON keys
                text_parts += 1
                keys = ", ".join(list(root.data.keys())[:4])
                text_previews.append(f"- data keys: [{keys}]")

        return (
            f"Outbound parts={len(parts)} | text={text_parts} | files={file_parts}\n"
            f"Text previews:\n{('\n'.join(text_previews) if text_previews else '(none)')}\n"
            f"Files:\n{('\n'.join(file_previews) if file_previews else '(none)')}"
        )

    def _convert_last_user_event_to_parts(self, session_events: Sequence[Any]) -> list[A2APart]:
        """
        Extract parts ONLY from the last user event to avoid token bleed.
        If you pass a converter, it must output A2A `Part` RootModels.
        If your parts are already A2A Parts, they'll be passed through.
        """
        if not session_events:
            return []

        # Find last user event with content.parts
        last_user = None
        for e in reversed(session_events):
            if getattr(e, "author", None) == "user":
                last_user = e
                break
        if not last_user or not getattr(last_user, "content", None):
            return []

        parts_out: list[A2APart] = []
        for part in getattr(last_user.content, "parts", []) or []:
            # Convert if necessary
            if self._genai_part_converter:
                converted = self._genai_part_converter(part)
            else:
                converted = part if isinstance(part, A2APart) else None

            if converted is None:
                continue

            if isinstance(converted, list):
                candidates = converted
            else:
                candidates = [converted]

            for c in candidates:
                # Optionally filter orchestration noise for text parts
                if isinstance(c.root, TextPart) and self._filter_orchestration_noise:
                    txt = (c.root.text or "").strip()
                    if txt and self._is_noise_text(txt):
                        continue
                parts_out.append(c)

        return parts_out

    # ------------------------------
    # Public send APIs
    # ------------------------------
    async def send_message_parts(
        self,
        parts: list[A2APart],
        *,
        context_id: Optional[str] = None,
        request_metadata: Optional[dict[str, Any]] = None,
        state: Optional[dict[str, Any]] = None,
    ) -> AsyncIterator[ClientEvent | A2AMessage]:
        """
        Send explicit A2A parts to the remote agent.

        Yields:
            - (Task, UpdateEvent) for streaming; or
            - A2AMessage for non-streaming
        """
        await self.ensure_ready()
        assert self._a2a_client is not None, "A2A client not initialized"
        client = self._a2a_client  # non-optional binding

        if not parts:
            logger.debug("[%s] No parts to send; returning", self.name)
            # appease strict type-checkers so they see this as a generator
            if False:
                yield  # pragma: no cover
            return

        if logger.isEnabledFor(logging.DEBUG):
            try:
                logger.debug("[%s]\n%s", self.name, self._summarize_parts_for_log(parts))
            except Exception:
                pass

        req = A2AMessage(
            message_id=str(uuid.uuid4()),
            parts=parts,
            role=Role.user,          # enum per your schema
            context_id=context_id,
        )

        safe_state: MutableMapping[str, Any] = cast(MutableMapping[str, Any], state or {})
        context = ClientCallContext(state=safe_state)

        async for resp in client.send_message(
            request=req,
            request_metadata=request_metadata,
            context=context,
        ):
            yield (self._response_adapter(resp) if self._response_adapter else resp)

    async def send_last_user_event(
        self,
        session_events: Sequence[Any],
        *,
        context_id: Optional[str] = None,
        request_metadata: Optional[dict[str, Any]] = None,
        state: Optional[dict[str, Any]] = None,
    ) -> AsyncIterator[ClientEvent | A2AMessage]:
        """
        Build parts from ONLY the last user event and send.
        Provide context_id directly or inject a context_id_extractor in __init__.
        """
        parts = self._convert_last_user_event_to_parts(session_events)
        if not parts:
            logger.debug("[%s] No parts extracted from last user event.", self.name)
            if False:
                yield  # pragma: no cover
            return

        if context_id is None and self._context_id_extractor:
            try:
                context_id = self._context_id_extractor(session_events)
            except Exception as ex:
                logger.debug("context_id_extractor failed: %s", ex)

        async for resp in self.send_message_parts(
            parts,
            context_id=context_id,
            request_metadata=request_metadata,
            state=state,
        ):
            yield resp

    # ------------------------------
    # Pass-through A2A APIs
    # ------------------------------
    async def get_card(self) -> AgentCard:
        await self.ensure_ready()
        assert self._a2a_client is not None
        return await self._a2a_client.get_card()

    async def get_task(self, *args, **kwargs):
        await self.ensure_ready()
        assert self._a2a_client is not None
        return await self._a2a_client.get_task(*args, **kwargs)

    async def cancel_task(self, *args, **kwargs):
        await self.ensure_ready()
        assert self._a2a_client is not None
        return await self._a2a_client.cancel_task(*args, **kwargs)

    async def set_task_callback(self, *args, **kwargs):
        await self.ensure_ready()
        assert self._a2a_client is not None
        return await self._a2a_client.set_task_callback(*args, **kwargs)

    async def get_task_callback(self, *args, **kwargs):
        await self.ensure_ready()
        assert self._a2a_client is not None
        return await self._a2a_client.get_task_callback(*args, **kwargs)

    async def resubscribe(self, *args, **kwargs):
        await self.ensure_ready()
        assert self._a2a_client is not None
        async for ev in self._a2a_client.resubscribe(*args, **kwargs):
            yield (self._response_adapter(ev) if self._response_adapter else ev)



# from pydantic import PrivateAttr

# class RemoteProxyAgent(RemoteA2aAgent):
#     """RemoteProxyAgent"""

#     _manager=PrivateAttr()
#     def __init__(self,name,manager,description,*args,**kwargs):
#         super().__init__(
#             agent_card=manager.get_card(),
#             name=name,
#             description=description,
#             *args,
#             **kwargs,
#         )

#         self._manager=manager