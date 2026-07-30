# agents/remote_agent_connections.py

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from pydantic import PrivateAttr

from google.adk.agents import BaseAgent
from google.adk.events.event import Event
from google.genai import types as genai_types

from services.a2a_runtime.adapter import A2AAgentAdapter
from services.a2a_runtime.client_manager import A2AClientManager

logger = logging.getLogger(__name__)

A2A_METADATA_PREFIX = "a2a:"

_session_manager: Any = PrivateAttr(default=None)

class RemoteAgentInfo:
    def __init__(
        self,
        name,
        description,
        endpoint,
        capabilities=None,
        skills=None,
    ):
        self.name = name
        self.description = description
        self.endpoint = endpoint
        self.capabilities = capabilities or []
        self.skills = skills or []


class RemoteServerManager(BaseAgent):
    """
    ADK-compatible shim around a pure a2a-sdk adapter.

    This class intentionally does NOT inherit from:
        google.adk.agents.remote_a2a_agent.RemoteA2aAgent

    It allows the rest of your current system to keep using:
        root_agent.sub_agents
        transfer_to_agent()

    But A2A task/session state is now controlled by your own code.
    """

    _agent_card_url: str = PrivateAttr()
    _client_manager: A2AClientManager = PrivateAttr()
    _adapter: A2AAgentAdapter = PrivateAttr()

    _capabilities: List[str] = PrivateAttr(default_factory=list)
    _skills: List[str] = PrivateAttr(default_factory=list)
    _skills_full: List[Dict[str, Any]] = PrivateAttr(default_factory=list)
    _card_url: Optional[str] = PrivateAttr(default=None)
    _version: Optional[str] = PrivateAttr(default=None)

    def __init__(
        self,
        *,
        name: str,
        agent_card: str | None = None,
        agent_card_url: str | None = None,
        description: str = "",
        a2a_client_factory: Any | None = None,
        httpx_client: Any | None = None,
        timeout: float = 600.0,
        session_manager:Any =None,
        **kwargs: Any,
    ):
        super().__init__(
            name=name,
            description=description,
            **kwargs,
        )
        self._session_manager = session_manager
        resolved_card_url = agent_card_url or agent_card

        if not resolved_card_url:
            raise ValueError(
                "RemoteServerManager requires agent_card or agent_card_url"
            )

        self._agent_card_url = resolved_card_url
        self._card_url = resolved_card_url

        self._client_manager = A2AClientManager(
            httpx_client=httpx_client,
            client_factory=a2a_client_factory,
            timeout=timeout,
        )

        self._adapter = A2AAgentAdapter(
            client_manager=self._client_manager,
            agent_name=name,
            agent_card_url=resolved_card_url,
        )

    # --------------------------------------------------
    # Metadata properties
    # --------------------------------------------------

    @property
    def capabilities(self) -> List[str]:
        return self._capabilities

    @capabilities.setter
    def capabilities(self, value: Optional[List[str]]) -> None:
        self._capabilities = list(value or [])

    @property
    def skills(self) -> List[str]:
        return self._skills

    @skills.setter
    def skills(self, value: Optional[List[str]]) -> None:
        self._skills = list(value or [])

    @property
    def skills_full(self) -> List[Dict[str, Any]]:
        return self._skills_full

    @skills_full.setter
    def skills_full(self, value: Optional[List[Dict[str, Any]]]) -> None:
        self._skills_full = list(value or [])

    @property
    def card_url(self) -> Optional[str]:
        return self._card_url

    @card_url.setter
    def card_url(self, value: Optional[str]) -> None:
        self._card_url = value

    @property
    def version(self) -> Optional[str]:
        return self._version

    @version.setter
    def version(self, value: Optional[str]) -> None:
        self._version = value

    async def ensure_metadata(self):
        """
        Compatibility hook for your dashboard/registry layer.
        The loader already hydrates skills/capabilities.
        """
        return

    # --------------------------------------------------
    # ADK Context helpers
    # --------------------------------------------------

    def _get_orchestrator_state(self, ctx) -> dict:
        session = getattr(ctx, "session", None)
        state = getattr(session, "state", None) or {}

        orch = state.get("orchestrator", {})

        if isinstance(orch, dict):
            return orch

        return {}

    def _get_current_task(self, ctx) -> dict:
        orch = self._get_orchestrator_state(ctx)
        task = orch.get("task")

        if isinstance(task, dict):
            return task

        return {}

    def _get_remote_continuation_ids(
        self,
        ctx,
    ) -> tuple[str | None, str | None]:
        """
        Returns existing task_id/context_id only if this agent owns
        the active orchestration task.
        """

        task = self._get_current_task(ctx)

        task_id = task.get("task_id")
        context_id = task.get("context_id")
        owner = task.get("owner")
        state = task.get("state")
        interaction = task.get("interaction")

        if owner != self.name:
            logger.info(
                "[A2A NO CONTINUATION] agent=%s owner=%s state=%s interaction=%s task_id=%s context_id=%s",
                self.name,
                owner,
                state,
                interaction,
                task_id,
                context_id,
            )
            return None, None

        logger.info(
            "[A2A CONTINUATION IDS] agent=%s state=%s interaction=%s task_id=%s context_id=%s",
            self.name,
            state,
            interaction,
            task_id,
            context_id,
        )

        return task_id, context_id

    def _get_current_transfer_args(self, ctx) -> dict:
        """
        Reads transfer_to_agent args only from the current invocation.

        This prevents stale _remote_message values from previous HITL transfers
        being reused for a new user request.
        """

        session = getattr(ctx, "session", None)
        events = getattr(session, "events", None) or []

        current_invocation_id = getattr(ctx, "invocation_id", None)

        for event in reversed(events[-20:]):
            event_invocation_id = getattr(event, "invocation_id", None)

            # Only trust transfer calls from the current invocation when possible.
            if (
                current_invocation_id
                and event_invocation_id
                and event_invocation_id != current_invocation_id
            ):
                continue

            content = getattr(event, "content", None)
            parts = getattr(content, "parts", None) if content else None

            if not parts:
                continue

            for part in parts:
                fc = getattr(part, "function_call", None)

                if not fc:
                    continue

                if getattr(fc, "name", None) != "transfer_to_agent":
                    continue

                args = dict(getattr(fc, "args", None) or {})

                if args.get("agent_name") != self.name:
                    continue

                logger.info(
                    "[A2A CURRENT TRANSFER ARGS] agent=%s args_keys=%s remote_message=%s",
                    self.name,
                    list(args.keys()),
                    str(args.get("_remote_message", ""))[:250],
                )

                return args

        return {}

    def _get_remote_message_from_recent_transfer(self, ctx) -> str | None:
        """
        Reads explicit _remote_message from the current transfer_to_agent function_call only.

        Avoids stale _remote_message from older HITL transfers.
        """

        session = getattr(ctx, "session", None)
        events = getattr(session, "events", None) or []
        current_invocation_id = getattr(ctx, "invocation_id", None)

        for event in reversed(events[-20:]):
            event_invocation_id = getattr(event, "invocation_id", None)

            if (
                current_invocation_id
                and event_invocation_id
                and event_invocation_id != current_invocation_id
            ):
                continue

            content = getattr(event, "content", None)
            parts = getattr(content, "parts", None) if content else None

            if not parts:
                continue

            for part in parts:
                fc = getattr(part, "function_call", None)

                if not fc:
                    continue

                if getattr(fc, "name", None) != "transfer_to_agent":
                    continue

                args = dict(getattr(fc, "args", None) or {})

                if args.get("agent_name") != self.name:
                    continue

                remote_message = args.get("_remote_message")

                if isinstance(remote_message, str) and remote_message.strip():
                    logger.info(
                        "[A2A REMOTE MESSAGE FROM CURRENT TRANSFER] agent=%s message=%s",
                        self.name,
                        remote_message[:250],
                    )
                    return remote_message.strip()

        return None


    def _extract_meta_text_parts(self, ctx) -> list[str]:
        """
        Extract META text parts such as tool tokens from current user content/session.
        """

        user_content = getattr(ctx, "user_content", None)

        if user_content and getattr(user_content, "parts", None):
            parts = user_content.parts
        else:
            session = getattr(ctx, "session", None)
            events = getattr(session, "events", None) or []

            latest_user_event = None

            for event in reversed(events):
                if getattr(event, "author", None) == "user":
                    latest_user_event = event
                    break

            if (
                not latest_user_event
                or not getattr(latest_user_event, "content", None)
            ):
                return []

            parts = getattr(latest_user_event.content, "parts", None) or []

        extras: list[str] = []

        for part in parts:
            text = getattr(part, "text", None)

            if not isinstance(text, str):
                continue

            text = text.strip()

            if text.startswith("[META:"):
                extras.append(text)

        return extras


    def _extract_file_parts(self, ctx) -> list[genai_types.Part]:
        """
        Extract non-text parts (uploaded files, inline data) from the
        current user content / latest user session event.

        These carry no `.text`, so `_extract_user_message_and_extra_parts`
        (which only reads `part.text`) skips right past them. This walks
        the same source but keeps `file_data` / `inline_data` parts instead
        of discarding them.
        """

        user_content = getattr(ctx, "user_content", None)

        if user_content and getattr(user_content, "parts", None):
            parts = user_content.parts
        else:
            session = getattr(ctx, "session", None)
            events = getattr(session, "events", None) or []

            latest_user_event = None

            for event in reversed(events):
                if getattr(event, "author", None) == "user":
                    latest_user_event = event
                    break

            if (
                not latest_user_event
                or not getattr(latest_user_event, "content", None)
            ):
                return []

            parts = getattr(latest_user_event.content, "parts", None) or []

        file_parts: list[genai_types.Part] = []

        for part in parts:
            if getattr(part, "file_data", None) is not None:
                file_parts.append(part)
            elif getattr(part, "inline_data", None) is not None:
                file_parts.append(part)

        if file_parts:
            logger.info(
                "[A2A FILE PARTS FOUND] agent=%s count=%s",
                self.name,
                len(file_parts),
            )

        return file_parts

    def _is_noise_text(self, text: str) -> bool:
        stripped = (text or "").strip()

        return (
            stripped.startswith("For context:")
            or stripped.startswith("[Cortex]")
            or "`transfer_to_agent`" in stripped
            or stripped.startswith("[Tool]")
        )

    def _extract_user_message_and_extra_parts(
        self,
        ctx,
    ) -> tuple[str, list[str]]:
        """
        Extract the current user message.

        Priority:
        1. ctx.user_content
        2. latest ADK session user event

        This avoids reconstructing entire ADK session history.
        """
        transfer_message = self._get_remote_message_from_recent_transfer(ctx)

        if transfer_message:
            return transfer_message, self._extract_meta_text_parts(ctx)
        
        user_content = getattr(ctx, "user_content", None)

        if user_content and getattr(user_content, "parts", None):
            parts = user_content.parts
        else:
            session = getattr(ctx, "session", None)
            events = getattr(session, "events", None) or []

            latest_user_event = None

            for event in reversed(events):
                if getattr(event, "author", None) == "user":
                    latest_user_event = event
                    break

            if (
                not latest_user_event
                or not getattr(latest_user_event, "content", None)
            ):
                return "", []

            parts = getattr(latest_user_event.content, "parts", None) or []

        text_parts: list[str] = []

        for part in parts:
            text = getattr(part, "text", None)

            if not isinstance(text, str):
                continue

            if not text.strip():
                continue

            if self._is_noise_text(text):
                continue

            text_parts.append(text.strip())

        if not text_parts:
            return "", []

        primary_message = text_parts[0]
        extra_parts = text_parts[1:]

        return primary_message, extra_parts

    # --------------------------------------------------
    # ADK Event builder
    # --------------------------------------------------

    def _build_adk_event(self, parsed, ctx) -> Event:
        parts = []

        if parsed.text:
            parts.append(
                genai_types.Part(text=parsed.text)
            )

        content = genai_types.Content(
            role="model",
            parts=parts,
        )

        custom_metadata: dict[str, Any] = {}

        if parsed.task_id:
            custom_metadata[A2A_METADATA_PREFIX + "task_id"] = parsed.task_id

        if parsed.context_id:
            custom_metadata[A2A_METADATA_PREFIX + "context_id"] = parsed.context_id

        if parsed.request_dump:
            custom_metadata[A2A_METADATA_PREFIX + "request"] = parsed.request_dump

        if parsed.response_dump:
            custom_metadata[A2A_METADATA_PREFIX + "response"] = parsed.response_dump

        if parsed.metadata:
            custom_metadata.update(parsed.metadata)

        return Event(
            author=self.name,
            content=content,
            invocation_id=ctx.invocation_id,
            branch=ctx.branch,
            custom_metadata=custom_metadata,
            partial=False,
        )

    # --------------------------------------------------
    # ADK BaseAgent implementation
    # --------------------------------------------------

    async def _run_async_impl(self, ctx) -> AsyncGenerator[Event, None]:
        user_message, extra_parts = self._extract_user_message_and_extra_parts(ctx)
        file_parts = self._extract_file_parts(ctx)

        tool_context = {}
        if self._session_manager is not None:
            sess_user_id = getattr(ctx.session, "user_id", None)
            sess_id = getattr(ctx.session, "id", None)
            if sess_user_id and sess_id:
                tool_context = await self._session_manager.consume_tool_context(
                    sess_user_id, sess_id
                ) or {}

        if not user_message and not file_parts:
            logger.warning(
                "[A2A EMPTY USER MESSAGE] agent=%s",
                self.name,
            )

            yield Event(
                author=self.name,
                content=genai_types.Content(
                    role="model",
                    parts=[],
                ),
                invocation_id=ctx.invocation_id,
                branch=ctx.branch,
                custom_metadata={
                    "warning": "No user message found for A2A request",
                },
                partial=False,
            )
            return

        task_id, context_id = self._get_remote_continuation_ids(ctx)

        logger.info(
            "[A2A RUN] agent=%s task_id=%s context_id=%s message=%s",
            self.name,
            task_id,
            context_id,
            user_message[:250],
        )

        try:
            async for parsed in self._adapter.stream_message(
                message=user_message,
                task_id=task_id,
                context_id=context_id,
                extra_text_parts=extra_parts,
                extra_genai_parts=file_parts,
                request_metadata=tool_context or None,

            ):
                yield self._build_adk_event(parsed, ctx)

        except Exception as exc:
            logger.exception(
                "[A2A REQUEST FAILED] agent=%s",
                self.name,
            )

            yield Event(
                author=self.name,
                error_message=f"A2A request failed: {exc}",
                invocation_id=ctx.invocation_id,
                branch=ctx.branch,
                custom_metadata={
                    "a2a:error": str(exc),
                },
                partial=False,
            )

    async def _run_live_impl(self, ctx) -> AsyncGenerator[Event, None]:
        raise NotImplementedError(
            f"_run_live_impl for {type(self)} is not implemented."
        )
        yield

    async def cleanup(self):
        try:
            await self._client_manager.close()
        except Exception:
            logger.exception("[A2A CLIENT CLEANUP FAILED]")