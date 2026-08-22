"""initial baseline

Revision ID: 3a15e3ed22f7
Revises: 
Create Date: 2026-05-26 00:45:24.889181

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '3a15e3ed22f7'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the Nexus-owned PostgreSQL schema.

    Google ADK owns its ``sessions`` and ``events`` tables, so those are
    intentionally not created here even though they have read-only ORM maps.
    """
    op.create_table(
        "agents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("host", sa.String(), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_healthy", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("agent_card", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_health_check", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "orchestration_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.String(length=255), nullable=False, unique=True),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('active','running','completed','failed','deleted')", name="chk_orchestration_status"),
    )
    op.create_index("ix_orchestration_sessions_session_id", "orchestration_sessions", ["session_id"])
    op.create_index("ix_orchestration_sessions_user_id", "orchestration_sessions", ["user_id"])
    op.create_index("ix_orchestration_sessions_tenant_id", "orchestration_sessions", ["tenant_id"])

    op.create_table(
        "agent_invocations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("orchestration_session_id", sa.String(length=255), nullable=False),
        sa.Column("agent_name", sa.String(length=150), nullable=False),
        sa.Column("agent_session_id", sa.String(length=255), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("input_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("output_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("plan_id", sa.String(), nullable=True),
        sa.Column("task_node_id", sa.String(), nullable=True),
        sa.Column("parent_invocation_id", sa.Integer(), nullable=True),
        sa.Column("input_artifacts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("output_artifacts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["orchestration_session_id"], ["orchestration_sessions.session_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_invocation_id"], ["agent_invocations.id"]),
    )
    for name, columns in (
        ("ix_agent_invocations_orchestration_session_id", ["orchestration_session_id"]),
        ("ix_agent_invocations_agent_name", ["agent_name"]),
        ("ix_agent_invocations_agent_session_id", ["agent_session_id"]),
        ("ix_agent_invocations_plan_id", ["plan_id"]),
        ("ix_agent_invocations_task_node_id", ["task_node_id"]),
        ("ix_agent_invocation_session_step", ["orchestration_session_id", "step_order"]),
        ("ix_agent_invocation_session", ["orchestration_session_id"]),
    ):
        op.create_index(name, "agent_invocations", columns)

    op.create_table(
        "agent_dependencies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("parent_invocation_id", sa.Integer(), nullable=False),
        sa.Column("child_invocation_id", sa.Integer(), nullable=False),
        sa.Column("dependency_type", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["parent_invocation_id"], ["agent_invocations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["child_invocation_id"], ["agent_invocations.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_agent_dependencies_parent_invocation_id", "agent_dependencies", ["parent_invocation_id"])
    op.create_index("ix_agent_dependencies_child_invocation_id", "agent_dependencies", ["child_invocation_id"])

    op.create_table(
        "agent_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("invocation_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["invocation_id"], ["agent_invocations.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_agent_events_invocation_id", "agent_events", ["invocation_id"])

    op.create_table(
        "artifacts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("session_id", sa.String(length=255), nullable=False),
        sa.Column("invocation_id", sa.Integer(), nullable=True),
        sa.Column("file_id", sa.String(length=255), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["invocation_id"], ["agent_invocations.id"], ondelete="CASCADE"),
    )
    for name, column in (("ix_artifacts_tenant_id", "tenant_id"), ("ix_artifacts_user_id", "user_id"), ("ix_artifacts_session_id", "session_id"), ("ix_artifacts_invocation_id", "invocation_id"), ("ix_artifacts_file_id", "file_id")):
        op.create_index(name, "artifacts", [column])

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(length=32), nullable=False, server_default="text"),
        sa.Column("agent_name", sa.String(length=255), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("artifact_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    for name, column in (("ix_chat_messages_session_id", "session_id"), ("ix_chat_messages_user_id", "user_id"), ("ix_chat_messages_tenant_id", "tenant_id"), ("ix_chat_messages_created_at", "created_at")):
        op.create_index(name, "chat_messages", [column])
    op.create_index("ix_chat_messages_session_created", "chat_messages", ["session_id", "created_at"])


def downgrade() -> None:
    """Drop Nexus-owned tables in dependency order."""
    op.drop_table("chat_messages")
    op.drop_table("artifacts")
    op.drop_table("agent_events")
    op.drop_table("agent_dependencies")
    op.drop_table("agent_invocations")
    op.drop_table("orchestration_sessions")
    op.drop_table("agents")
