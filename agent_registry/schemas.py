from pydantic import BaseModel
from typing import Dict, Any

class AddAgentRequest(BaseModel):
    name:str
    host:str
    port:int

class AgentResponse(BaseModel):
    name:str
    host:str
    port:int
    is_active: bool
    is_healthy: bool
    agent_card: Dict[str, Any]


