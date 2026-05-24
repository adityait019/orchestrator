from typing import Any, Optional

from pydantic import BaseModel, Field


class AgentCreateRequest(BaseModel):
    name: str
    host: str
    port: int
    is_active: bool = True
    is_healthy: bool = False
    agent_card: dict[str, Any] = Field(default_factory=dict)


class AgentUpdateRequest(BaseModel):
    host: Optional[str] = None
    port: Optional[int] = None
    is_active: Optional[bool] = None
    is_healthy: Optional[bool] = None
    agent_card: Optional[dict[str, Any]] = None