# services/a2a_runtime/adapter.py

from __future__ import annotations

import logging
import uuid
from typing import Any, AsyncGenerator

from a2a.types import Message, Part, Role, TextPart
from google.adk.a2a.converters.part_converter import convert_genai_part_to_a2a_part
from google.genai import types as genai_types

from .client_manager import A2AClientManager
from .models import A2AAdapterEvent
from .response_parser import parse_a2a_raw_event

logger = logging.getLogger(__name__)


class A2AAgentAdapter:
    """
    Pure a2a-sdk adapter.

    Owns:
    - A2A Message construction
    - task_id continuation
    - context_id continuation
    - streaming/non-streaming event normalization

    No Google ADK dependency.
    """

    def __init__(
        self,
        *,
        client_manager: A2AClientManager,
        agent_name: str,
        agent_card_url: str,
    ):
        self.client_manager = client_manager
        self.agent_name = agent_name
        self.agent_card_url = agent_card_url

    async def stream_message(
        self,
        *,
        message: str,
        task_id: str | None = None,
        context_id: str | None = None,
        extra_text_parts: list[str] | None = None,
        extra_genai_parts: list[genai_types.Part] | None = None,
        request_metadata: dict | None = None,
    ) -> AsyncGenerator[A2AAdapterEvent, None]:

        client = await self.client_manager.get_client(self.agent_card_url)

        parts: list[Part] = []

        if message and message.strip():
            parts.append(Part(root=TextPart(text=message)))

        for extra in extra_text_parts or []:
            if isinstance(extra, str) and extra.strip():
                parts.append(
                    Part(root=TextPart(text=extra.strip()))
                )

        # Non-text genai Parts (file_data / inline_data, i.e. uploaded files)
        # go through ADK's own converter so they come out as proper A2A
        # FileParts instead of being silently dropped.
        for genai_part in extra_genai_parts or []:
            try:
                converted = convert_genai_part_to_a2a_part(genai_part)
            except Exception:
                logger.exception(
                    "[A2A FILE PART CONVERSION FAILED] agent=%s part=%s",
                    self.agent_name,
                    genai_part,
                )
                continue

            if converted is None:
                logger.warning(
                    "[A2A FILE PART DROPPED] agent=%s part=%s "
                    "(converter returned None)",
                    self.agent_name,
                    genai_part,
                )
                continue

            parts.append(converted)

        request_message = Message(
            role=Role.user,
            message_id=str(uuid.uuid4()),
            parts=parts,
            context_id=context_id,
            task_id=task_id,
            metadata=request_metadata,
        )

        request_dump = request_message.model_dump(
            exclude_none=True,
            by_alias=True,
            mode="json",
        )

        logger.info(
            "[A2A SEND] agent=%s task_id=%s context_id=%s text_preview=%s",
            self.agent_name,
            task_id,
            context_id,
            message[:250],
        )

        async for raw_event in client.send_message(
            request=request_message,
            request_metadata=request_metadata,
        ):
            parsed = parse_a2a_raw_event(
                raw_event,
                request_dump=request_dump,
            )

            logger.info(
                "[A2A EVENT] agent=%s state=%s task_id=%s context_id=%s terminal=%s",
                self.agent_name,
                parsed.state,
                parsed.task_id,
                parsed.context_id,
                parsed.is_terminal,
            )

            yield parsed