from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Boolean, String, Integer, DateTime
from agent_registry.database import Base
from datetime import datetime

class AgentRegistry(Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    host: Mapped[str] = mapped_column(String, nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    auth_token: Mapped[str] = mapped_column(String, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_healthy: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_health_check: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)