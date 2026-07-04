# memory_management/adk-base-memory/_schemas.py

"""SQLAlchemy ORM models for DatabaseMemoryService."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Float, Index, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import String

from memory_management.adk_base_memory._types import DynamicJSON

_MAX_KEY_LENGTH = 128


class Base(DeclarativeBase):
    """Base class for memory database tables."""


class StorageMemoryEntry(Base):
    """A single memory entry row."""

    __tablename__ = "adk_memory_entries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    app_name: Mapped[str] = mapped_column(String(_MAX_KEY_LENGTH), index=True)
    user_id: Mapped[str] = mapped_column(String(_MAX_KEY_LENGTH), index=True)

    keywords: Mapped[str] = mapped_column(Text)

    author: Mapped[str | None] = mapped_column(String(_MAX_KEY_LENGTH), nullable=True)
    content: Mapped[dict[str, Any]] = mapped_column(DynamicJSON)
    timestamp: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (Index("idx_memory_app_user", "app_name", "user_id"),)

    def __repr__(self) -> str:
        return (
            f"<StorageMemoryEntry(id={self.id}, app_name={self.app_name!r}, "
            f"user_id={self.user_id!r})>"
        )