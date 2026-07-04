# memory_management/adk-base-memory/service.py

"""A durable memory service backed by any SQLAlchemy-compatible async database.

Supported dialects include SQLite (via ``aiosqlite``), PostgreSQL (via
``asyncpg``), MySQL / MariaDB, and any other database for which an async
SQLAlchemy driver is available.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from datetime import datetime
from typing import TYPE_CHECKING, Any

from google.adk.memory.base_memory_service import BaseMemoryService, SearchMemoryResponse
from google.adk.memory.memory_entry import MemoryEntry
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.ext.asyncio import AsyncSession as DatabaseSessionFactory
from sqlalchemy.pool import StaticPool
from typing_extensions import override


from memory_management.adk_base_memory._schemas import Base,StorageMemoryEntry

if TYPE_CHECKING:
    from google.adk.events.event import Event
    from google.adk.sessions.session import Session

logger = logging.getLogger(__name__)

_SQLITE_DIALECT = "sqlite"
DEFAULT_STOP_WORDS: frozenset[str] = frozenset(
    {
        "a", "about", "above", "after", "again", "against", "all", "am", "an",
        "and", "any", "are", "as", "at", "be", "because", "been", "before",
        "being", "below", "between", "both", "but", "by", "can", "could",
        "did", "do", "does", "doing", "don", "down", "during", "each", "else",
        "few", "for", "from", "further", "had", "has", "have", "having", "he",
        "her", "here", "hers", "herself", "him", "himself", "his", "how", "i",
        "if", "in", "into", "is", "it", "its", "itself", "just", "may", "me",
        "might", "more", "most", "must", "my", "myself", "no", "nor", "not",
        "now", "of", "off", "on", "once", "only", "or", "other", "our", "ours",
        "ourselves", "out", "over", "own", "s", "same", "shall", "she",
        "should", "so", "some", "such", "t", "than", "that", "the", "their",
        "theirs", "them", "themselves", "then", "there", "these", "they",
        "this", "those", "through", "to", "too", "under", "until", "up",
        "very", "was", "we", "were", "what", "when", "where", "which", "who",
        "whom", "why", "will", "with", "would", "you", "your", "yours",
        "yourself", "yourselves",
    }
)

def _format_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).isoformat()


class DatabaseMemoryService(BaseMemoryService):

    def __init__(
        self,
        db_url: str,
        *,
        stop_words: set[str] | None = None,
        **engine_kwargs: Any,
    ) -> None:

        try:
            url = make_url(db_url)

            if url.get_backend_name() == _SQLITE_DIALECT and url.database == ":memory:":
                engine_kwargs.setdefault("poolclass", StaticPool)
                connect_args = dict(engine_kwargs.get("connect_args", {}))
                connect_args.setdefault("check_same_thread", False)
                engine_kwargs["connect_args"] = connect_args
            elif url.get_backend_name() != _SQLITE_DIALECT:
                engine_kwargs.setdefault("pool_pre_ping", True)

            self._engine: AsyncEngine = create_async_engine(db_url, **engine_kwargs)

        except Exception as e:
            if isinstance(e, ArgumentError):
                raise ValueError(f"Invalid database URL format: '{db_url}'") from e
            raise ValueError(f"Failed to create database engine for URL '{db_url}'.") from e

        self._session_factory: async_sessionmaker[DatabaseSessionFactory] = (
            async_sessionmaker(bind=self._engine, expire_on_commit=False)
        )

        self._tables_created = False
        self._table_creation_lock = asyncio.Lock()

        self.stop_words =(set(stop_words) if stop_words is not None else set(DEFAULT_STOP_WORDS))

    # =============================
    # DB LIFECYCLE
    # =============================

    @asynccontextmanager
    async def _db_session(self) -> AsyncIterator[DatabaseSessionFactory]:
        async with self._session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    async def _prepare_tables(self) -> None:
        if self._tables_created:
            return

        async with self._table_creation_lock:
            if self._tables_created:
                return

            async with self._engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            self._tables_created = True

    # =============================
    # KEYWORD EXTRACTION ✅ IMPROVED
    # =============================

    def _extract_keywords(self, text: str) -> set[str]:
        words = re.findall(r"[A-Za-z0-9_]+", text.lower())
        return {w for w in words if w not in self.stop_words and len(w) > 2}

    # =============================
    # ENTRY BUILDER ✅ CLEAN FILTER
    # =============================

    def _build_entry(
        self,
        *,
        app_name: str,
        user_id: str,
        event: Event,
    ) -> StorageMemoryEntry | None:

        if not event.content or not event.content.parts:
            return None

        # ✅ keep only meaningful actors
        if event.author not in {"user", "model"}:
            return None

        text = " ".join(p.text for p in event.content.parts if p.text)
        if not text.strip():
            return None

        keywords = self._extract_keywords(text)
        if not keywords:
            return None

        return StorageMemoryEntry(
            app_name=app_name,
            user_id=user_id,
            keywords=" ".join(sorted(keywords)),
            author=event.author,
            content=event.content.model_dump(exclude_none=True, mode="json"),
            timestamp=event.timestamp,
        )

    # =============================
    # MEMORY WRITE ✅ DEDUP FIX
    # =============================

    @override
    async def add_session_to_memory(self, session: Session) -> None:
        await self._prepare_tables()

        if not session.events:
            return

        entries = [
            self._build_entry(
                app_name=session.app_name,
                user_id=session.user_id,
                event=event,
            )
            for event in session.events
        ]

        entries = [e for e in entries if e is not None]

        if not entries:
            return

        async with self._db_session() as db:
            # ✅ deduplicate before insert
            existing_stmt = select(
                StorageMemoryEntry.author,
                StorageMemoryEntry.timestamp
            ).filter(
                StorageMemoryEntry.app_name == session.app_name,
                StorageMemoryEntry.user_id == session.user_id,
            )

            result = await db.execute(existing_stmt)
            existing = {(row[0], row[1]) for row in result.all()}

            new_entries = [
                e for e in entries if (e.author, e.timestamp) not in existing
            ]

            if not new_entries:
                return

            db.add_all(new_entries)
            await db.commit()

    # =============================
    # SEARCH ✅ OPTIMIZED
    # =============================

    @override
    async def search_memory(
        self,
        *,
        app_name: str,
        user_id: str,
        query: str,
    ) -> SearchMemoryResponse:

        keywords = self._extract_keywords(query)
        if not keywords:
            return SearchMemoryResponse()

        await self._prepare_tables()

        async with self._db_session() as db:
            stmt = (
                select(StorageMemoryEntry)
                .filter(StorageMemoryEntry.app_name == app_name)
                .filter(StorageMemoryEntry.user_id == user_id)
            )

            result = await db.execute(stmt)
            rows = result.scalars().all()

        seen = set()
        memories: list[MemoryEntry] = []

        for row in rows:

            stored_keywords = set(row.keywords.split())
            if not stored_keywords.intersection(keywords):
                continue

            try:
                from google.genai import types
                content = types.Content.model_validate(row.content)
            except Exception:
                continue

            text = ""
            if content.parts:
                text = " ".join(p.text for p in content.parts if p.text)

            ts = _format_timestamp(row.timestamp or 0.0)
            key = (row.author, text)

            if key in seen:
                continue

            seen.add(key)

            memories.append(
                MemoryEntry(
                    content=content,
                    author=row.author or "",
                    timestamp=ts,
                )
            )

        return SearchMemoryResponse(memories=memories)