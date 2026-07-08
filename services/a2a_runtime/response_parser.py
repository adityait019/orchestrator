# services/a2a_runtime/response_parser.py

from __future__ import annotations

import json
import logging
from typing import Any

from a2a.types import (
    Message,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatusUpdateEvent,
)

from .models import A2AAdapterEvent

logger = logging.getLogger(__name__)


TERMINAL_STATES = {
    "completed",
    "canceled",
    "failed",
    "input_required",
    "unknown",
    "input-required",
}

INPUT_REQUIRED_STATES = {
    "input_required",
    "input-required",
    "inputrequired",
}

def _enum_value(value: Any) -> Any:
    if value is None:
        return None

    if hasattr(value, "value"):
        return value.value

    return value


def _model_dump(obj: Any) -> dict[str, Any] | None:
    if obj is None:
        return None

    try:
        return obj.model_dump(
            exclude_none=True,
            by_alias=True,
            mode="json",
        )
    except Exception:
        pass

    try:
        return obj.dict(exclude_none=True, by_alias=True)
    except Exception:
        pass

    try:
        return json.loads(json.dumps(obj, default=str))
    except Exception:
        return {"value": str(obj)}


def _extract_text_from_part(part: Any) -> str | None:
    root = getattr(part, "root", None)

    if root is not None:
        text = getattr(root, "text", None)
        if isinstance(text, str) and text.strip():
            return text.strip()

    text = getattr(part, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()

    return None


def _extract_text_from_parts(parts: list[Any] | None) -> str | None:
    if not parts:
        return None

    chunks: list[str] = []

    for part in parts:
        txt = _extract_text_from_part(part)
        if txt:
            chunks.append(txt)

    if not chunks:
        return None

    return "\n".join(chunks).strip()


def _extract_text_from_message(message: Message | None) -> str | None:
    if not message:
        return None

    return _extract_text_from_parts(getattr(message, "parts", None))


def _extract_interaction_from_text(text: str | None) -> str | None:
    if not text:
        return None

    try:
        payload = json.loads(text)

        if isinstance(payload, dict):
            value = payload.get("interaction")
            if isinstance(value, str) and value.strip():
                return value.strip()

    except Exception:
        return None

    return None


def _task_state(task: Task | None) -> str | None:
    if not task or not getattr(task, "status", None):
        return None

    state = getattr(task.status, "state", None)
    return _enum_value(state)


def _task_metadata(task: Task | None) -> dict[str, Any]:
    if not task:
        return {}

    meta = getattr(task, "metadata", None)
    if isinstance(meta, dict):
        return dict(meta)

    status = getattr(task, "status", None)
    if status:
        status_meta = getattr(status, "metadata", None)
        if isinstance(status_meta, dict):
            return dict(status_meta)

    return {}


def _task_status_message(task: Task | None) -> Message | None:
    if not task or not getattr(task, "status", None):
        return None

    return getattr(task.status, "message", None)


def parse_a2a_raw_event(
    raw_event: Any,
    *,
    request_dump: dict[str, Any] | None = None,
) -> A2AAdapterEvent:
    """
    Converts raw a2a-sdk output into A2AAdapterEvent.

    Supports:
    - Message
    - Task
    - tuple(Task, update)
    - TaskStatusUpdateEvent
    - TaskArtifactUpdateEvent
    """

    # ----------------------------------------------------
    # Case 1: streaming tuple -> (Task, update)
    # ----------------------------------------------------
    if isinstance(raw_event, tuple):
        task = raw_event[0] if len(raw_event) > 0 else None
        update = raw_event[1] if len(raw_event) > 1 else None

        text = None
        metadata = _task_metadata(task)

        if isinstance(update, TaskStatusUpdateEvent):
            status = getattr(update, "status", None)
            if status:
                msg = getattr(status, "message", None)
                text = _extract_text_from_message(msg)

                update_meta = getattr(status, "metadata", None)
                if isinstance(update_meta, dict):
                    metadata.update(update_meta)

        elif isinstance(update, TaskArtifactUpdateEvent):
            # For now artifacts are handled from task dump / EventProcessor path.
            text = None

        if not text:
            text = _extract_text_from_message(_task_status_message(task))

        state = _task_state(task)
        interaction = _extract_interaction_from_text(text)
        normalized_state = str(state or "").lower().strip()

        if not interaction and normalized_state in INPUT_REQUIRED_STATES:
            interaction = "request_input"
            
        if interaction:
            metadata["interaction"] = interaction

        return A2AAdapterEvent(
            text=text,
            task_id=getattr(task, "id", None) if task else None,
            context_id=getattr(task, "context_id", None) if task else None,
            state=state,
            metadata=metadata,
            request_dump=request_dump,
            response_dump=_model_dump(task),
            is_terminal=state in TERMINAL_STATES,
        )

    # ----------------------------------------------------
    # Case 2: direct Message
    # ----------------------------------------------------
    if isinstance(raw_event, Message):
        text = _extract_text_from_message(raw_event)
        interaction = _extract_interaction_from_text(text)

        metadata: dict[str, Any] = {}
        if interaction:
            metadata["interaction"] = interaction

        return A2AAdapterEvent(
            text=text,
            task_id=getattr(raw_event, "task_id", None),
            context_id=getattr(raw_event, "context_id", None),
            state=None,
            metadata=metadata,
            request_dump=request_dump,
            response_dump=_model_dump(raw_event),
            is_terminal=True,
        )

    # ----------------------------------------------------
    # Case 3: direct Task
    # ----------------------------------------------------
    if isinstance(raw_event, Task):
        task = raw_event
        text = _extract_text_from_message(_task_status_message(task))

        metadata = _task_metadata(task)
        interaction = _extract_interaction_from_text(text)

        if interaction:
            metadata["interaction"] = interaction

        state = _task_state(task)

        return A2AAdapterEvent(
            text=text,
            task_id=getattr(task, "id", None),
            context_id=getattr(task, "context_id", None),
            state=state,
            metadata=metadata,
            request_dump=request_dump,
            response_dump=_model_dump(task),
            is_terminal=state in TERMINAL_STATES,
        )

    # ----------------------------------------------------
    # Unknown
    # ----------------------------------------------------
    logger.warning("[A2A UNKNOWN EVENT] %s", type(raw_event))

    return A2AAdapterEvent(
        text=None,
        metadata={"unknown_event": str(type(raw_event))},
        request_dump=request_dump,
        response_dump={"value": str(raw_event)},
        is_terminal=False,
    )