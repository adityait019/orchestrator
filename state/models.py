# state/models.py

from dataclasses import dataclass, field
from typing import Optional, Dict, Any


@dataclass
class RemoteAgentState:
    agent_name: str
    scope_key: str

    remote_context_id: Optional[str] = None
    remote_task_id: Optional[str] = None

    last_status: Optional[str] = None

    metadata: Dict[str, Any] = field(default_factory=dict)