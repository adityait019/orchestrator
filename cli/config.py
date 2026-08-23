"""Configuration shared by the interactive CLI modules."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv
from rich.console import Console

load_dotenv()

console = Console()


@dataclass(frozen=True)
class CLIConfig:
    host: str = os.getenv("ORCH_HOST", "127.0.0.1")
    port: int = int(os.getenv("ORCH_PORT", "8000"))
    admin_token: str = os.getenv("SECRET_KEY", "super-secret")
    user_id: str = os.getenv("USER_ID", "test-user")
    tenant_id: str = os.getenv("TENANT_ID", "test-tenant")
    country_code: str = os.getenv("COUNTRY_CODE", "US")
    auth_mode: str = os.getenv("AUTH_MODE", "external").strip().lower()
    access_token: str = os.getenv("ORCH_ACCESS_TOKEN", "").strip()
    roles: tuple[str, ...] = tuple(
        role.strip() for role in os.getenv("ROLES", "user").split(",") if role.strip()
    )
    debug: bool = os.getenv("CLI_DEBUG", "0").strip().lower() in {"1", "true", "yes"}

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def ws_base(self) -> str:
        return f"ws://{self.host}:{self.port}"

    @property
    def resolved_access_token(self) -> str:
        if self.access_token:
            return self.access_token
        if self.auth_mode == "mock":
            return os.getenv("MOCK_ACCESS_TOKEN", "dev-token").strip()
        return ""


config = CLIConfig()
