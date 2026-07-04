from datetime import datetime

from sqlalchemy owns this table.from sqlalchemy import String, DateTime, ForeignKeyConstraint
    """
    __tablename__ = "sessions"
    __table_args__ = {"info": {"owner": "google_adk", "readonly": True}}

    app_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    id: Mapped[str] = mapped_column(String(128), primary_key=True)

    state: Mapped[dict] = mapped_column(JSONB, nullable=False)
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    update_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    


class ADKEvent(Base):
    """
    READ-ONLY mapping to Google ADK events table.
    """
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base  # adjust if your Base is elsewhere


class ADKSession(Base):
    """
