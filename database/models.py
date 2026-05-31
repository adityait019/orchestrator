from datetime import datetime
from sqlalchemy.dialects.postgresql import JSONB

from sqlalchemy import (
    String,
    Integer,
    Text,
    DateTime,
    Boolean,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    CheckConstraint,
)

from sqlalchemy.sql import func
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)

class SessionStatus:
    ACTIVE = "active"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DELETED = "deleted"

    
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

    # ✅ JSONB to match DB
    agent_card: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # ✅ DB owns timestamp now
    # created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    last_health_check: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# -------------------------------------------------------------------
# 2️⃣ Orchestration Session (Top-level workflow)
# -------------------------------------------------------------------


class OrchestrationSession(Base):
    __tablename__ = "orchestration_sessions"

    __table_args__ = (
        CheckConstraint(
            "status IN ('active','running','completed','failed','deleted')",
            name="chk_orchestration_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    session_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(50))

    # ✅ CRITICAL FIX
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    invocations: Mapped[list["AgentInvocation"]] = relationship(
        back_populates="orchestration_session",
        cascade="all, delete-orphan",
    )

    tenant_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message_count: Mapped[int] = mapped_column(default=0, server_default="0", nullable=False)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# -------------------------------------------------------------------
# 3️⃣ Agent Invocation (Each sub-agent execution)
# -------------------------------------------------------------------

class AgentInvocation(Base):
    __tablename__ = "agent_invocations"

    id: Mapped[int] = mapped_column(primary_key=True)

    orchestration_session_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("orchestration_sessions.session_id",ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    agent_name: Mapped[str] = mapped_column(String(150), index=True)
    agent_session_id: Mapped[str] = mapped_column(String(255), index=True)

    step_order: Mapped[int] = mapped_column(Integer)

    status: Mapped[str] = mapped_column(String(50))

    input_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    output_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ✅ NEW (Phase 1)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

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
Index("ix_agent_invocation_session", AgentInvocation.orchestration_session_id)

# -------------------------------------------------------------------
# 4️⃣ Agent Dependencies (A → B relationships)
# -------------------------------------------------------------------

class AgentDependency(Base):
    __tablename__ = "agent_dependencies"

    id: Mapped[int] = mapped_column(primary_key=True)

    parent_invocation_id: Mapped[int] = mapped_column(
        ForeignKey("agent_invocations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    child_invocation_id: Mapped[int] = mapped_column(
        ForeignKey("agent_invocations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,

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
        ForeignKey("agent_invocations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    event_type: Mapped[str] = mapped_column(String(100))
    payload: Mapped[str] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),)

    # Relationship
    invocation: Mapped["AgentInvocation"] = relationship(
        back_populates="events"
    )




# -------------------------------------------------------------------
# 6️⃣ Artifacts (Generated + Uploaded files)
# -------------------------------------------------------------------

class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(primary_key=True)

    # ✅ Ownership scope
    tenant_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    session_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)

    # ✅ Agent context (optional for uploads)
    invocation_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_invocations.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )

    # ✅ File identity
    file_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)

    # ✅ Storage
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)

    # ✅ Metadata
    mime_type: Mapped[str | None] = mapped_column(String(100))
    file_size: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationship
    invocation: Mapped["AgentInvocation"] = relationship(
        back_populates="artifacts"
    )



# -------------------------------------------------------------------
# 7️⃣ Google ADK Sessions - READ ONLY MAPPING
# -------------------------------------------------------------------
# These tables are created and managed by Google ADK.
# Do NOT manually create/update/delete/migrate these tables.
# We only map them here so admin APIs can read from them.

class ADKSession(Base):
    __tablename__ = "sessions"
    __table_args__ = {"info": {"owner": "google_adk", "readonly": True}}

    app_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    id: Mapped[str] = mapped_column(String(128), primary_key=True)

    state: Mapped[dict] = mapped_column(JSONB, nullable=False)
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    update_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)


# -------------------------------------------------------------------
# 8️⃣ Google ADK Events - READ ONLY MAPPING
# -------------------------------------------------------------------

class ADKEvent(Base):
    __tablename__ = "events"

    __table_args__ = (
        ForeignKeyConstraint(
            ["app_name", "user_id", "session_id"],
            ["sessions.app_name", "sessions.user_id", "sessions.id"],
            ondelete="CASCADE",
        ),
        {"info": {"owner": "google_adk", "readonly": True}},
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    app_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(128), primary_key=True)

    invocation_id: Mapped[str] = mapped_column(String(256), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    event_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

# -------------------------------------------------------------------
# 9️⃣ Chat Messages (chat history persistence)
# -------------------------------------------------------------------

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)

    session_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    tenant_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    role: Mapped[str] = mapped_column(String(32), nullable=False)  # user | assistant | system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(String(32), default="text", server_default="text", nullable=False)

    agent_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(nullable=True)
    artifact_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

Index(
    "ix_chat_messages_session_created",
    ChatMessage.session_id,
    ChatMessage.created_at
)
