from pydantic import BaseModel


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


