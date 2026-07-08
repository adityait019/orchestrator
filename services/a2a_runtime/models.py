# services/a2a_runtime/models.py

from dataclasses import dataclass, field
from typing import Any


@dataclass
class A2AAdapterEvent:
    """
    Normalized A2A event returned by our pure a2a-sdk adapter.
    This keeps the rest of the orchestrator independent from raw A2A objects.
    """

    text: str | None = None

    task_id: str | None = None
    context_id: str | None = None
    state: str | None = None

    metadata: dict[str, Any] = field(default_factory=dict)

    request_dump: dict[str, Any] | None = None
    response_dump: dict[str, Any] | None = None

    is_terminal: bool = False