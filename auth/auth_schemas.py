from pydantic import BaseModel, Field

class LoginRequest(BaseModel):
    user_id: str = Field(default="user123", examples=["user123"])
    password: str = Field(default="password", examples=["password"])
    role: str = Field(default="user", examples=["user", "admin"])
    tenant_id: str = Field(..., examples=["tenant_001"])
    session_id: str = Field(..., examples=["session_123"])

class LoginResponse(BaseModel):
    user_id: str
    tenant_id: str
    role: str