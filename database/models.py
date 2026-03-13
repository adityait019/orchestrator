from datetime import datetime
from sqlalchemy import (
    String,
    Integer,
    Text,
    DateTime,
    Boolean,
    ForeignKey,
    Index,
    JSON,
)

from sqlalchemy.sql import func
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


# -------------------------------------------------------------------
# Base
# -------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


# -------------------------------------------------------------------
# 1️⃣ Agent Registry (Already in your system)
# -------------------------------------------------------------------

class AgentRegistry(Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    host: Mapped[str] = mapped_column(String, nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_healthy: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_health_check: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# -------------------------------------------------------------------
# 2️⃣ Orchestration Session (Top-level workflow)
# -------------------------------------------------------------------

class OrchestrationSession(Base):
    __tablename__ = "orchestration_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)

    session_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(String(255), index=True)

    status: Mapped[str] = mapped_column(String(50), default="active")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now().astimezone())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    invocations: Mapped[list["AgentInvocation"]] = relationship(
        back_populates="orchestration_session",
        cascade="all, delete-orphan"
    )


# -------------------------------------------------------------------
# 3️⃣ Agent Invocation (Each sub-agent execution)
# -------------------------------------------------------------------

class AgentInvocation(Base):
    __tablename__ = "agent_invocations"

    id: Mapped[int] = mapped_column(primary_key=True)

    orchestration_session_id: Mapped[int] = mapped_column(
        ForeignKey("orchestration_sessions.id"),
        index=True
    )

    agent_name: Mapped[str] = mapped_column(String(150), index=True)
    agent_session_id: Mapped[str] = mapped_column(String(255), index=True)

    step_order: Mapped[int] = mapped_column(Integer)

    status: Mapped[str] = mapped_column(String(50))  # queued, working, completed, failed

    input_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_payload: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    orchestration_session: Mapped["OrchestrationSession"] = relationship(
        back_populates="invocations"
    )

    events: Mapped[list["AgentEvent"]] = relationship(
        back_populates="invocation",
        cascade="all, delete-orphan"
    )

    artifacts: Mapped[list["Artifact"]] = relationship(
        back_populates="invocation",
        cascade="all, delete-orphan"
    )


# Helpful composite index
Index(
    "ix_agent_invocation_session_step",
    AgentInvocation.orchestration_session_id,
    AgentInvocation.step_order,
)


# -------------------------------------------------------------------
# 4️⃣ Agent Dependencies (A → B relationships)
# -------------------------------------------------------------------

class AgentDependency(Base):
    __tablename__ = "agent_dependencies"

    id: Mapped[int] = mapped_column(primary_key=True)

    parent_invocation_id: Mapped[int] = mapped_column(
        ForeignKey("agent_invocations.id"),
        index=True
    )

    child_invocation_id: Mapped[int] = mapped_column(
        ForeignKey("agent_invocations.id"),
        index=True
    )

    dependency_type: Mapped[str] = mapped_column(String(50))  # data, artifact, summary

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# -------------------------------------------------------------------
# 5️⃣ Agent Events (Streaming trace)
# -------------------------------------------------------------------

class AgentEvent(Base):
    __tablename__ = "agent_events"

    id: Mapped[int] = mapped_column(primary_key=True)

    invocation_id: Mapped[int] = mapped_column(
        ForeignKey("agent_invocations.id"),
        index=True
    )

    event_type: Mapped[str] = mapped_column(String(100))
    payload: Mapped[str] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),)

    # Relationship
    invocation: Mapped["AgentInvocation"] = relationship(
        back_populates="events"
    )


# -------------------------------------------------------------------
# 6️⃣ Artifacts (Generated files)
# -------------------------------------------------------------------

class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(primary_key=True)

    invocation_id: Mapped[int] = mapped_column(
        ForeignKey("agent_invocations.id"),
        index=True
    )

    file_id: Mapped[str] = mapped_column(String(255))
    filename: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(500))
    path: Mapped[str]= mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    invocation: Mapped["AgentInvocation"] = relationship(
        back_populates="artifacts"
    )

