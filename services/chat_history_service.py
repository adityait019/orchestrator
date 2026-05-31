"""
services/chat_history_service.py — Chat history persistence (session-based).

✅ Uses session_id as single source of truth
✅ Append-only model (no overwrite)
✅ Integrates with SessionManager (ADK-backed sessions)
✅ Safe for WebSocket + REST usage
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from database.engine import IS_LOCAL
from database.json_store import jdb

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ChatHistoryService:

    # ─────────────────────────────────────────────────────────────
    # ✅ Append Message (CORE)
    # ─────────────────────────────────────────────────────────────

    async def append_message(
        self,
        *,
        session_manager,   # ✅ injected from request.app.state
        user_id: str,
        tenant_id: Optional[str],
        session_id: str,
        message: Dict,
    ) -> bool:

        from sqlalchemy import select
        from database.session import AsyncSessionLocal
        from database.models import ChatMessage, OrchestrationSession

        role = self._fe_type_to_role(message.get("type"))
        content = message.get("content", "")

        try:
            # ✅ 1. Ensure ADK session (same pattern as upload router)
            await session_manager.ensure_session(user_id, session_id)

            async with AsyncSessionLocal() as db:
                async with db.begin():

                    # ✅ 2. Dedup guard (prevents spam + retries)
                    res = await db.execute(
                        select(ChatMessage.id).where(
                            ChatMessage.session_id == session_id,
                            ChatMessage.user_id == user_id,
                            ChatMessage.tenant_id == tenant_id,
                            ChatMessage.role == role,
                            ChatMessage.content == content,
                        ).limit(1)
                    )
                    if res.scalar_one_or_none():
                        return True

                    # ✅ 3. Insert message (append-only)
                    db.add(
                        ChatMessage(
                            session_id=session_id,
                            user_id=user_id,
                            tenant_id=tenant_id,
                            role=role,
                            content=content,
                            content_type=message.get("type", "text"),
                            agent_name=message.get("agent_name"),
                            input_tokens=message.get("input_tokens"),
                            output_tokens=message.get("output_tokens"),
                            artifact_ids=message.get("artifact_ids", []),
                        )
                    )

                    # ✅ 4. Update session metadata (non-authoritative)
                    res2 = await db.execute(
                        select(OrchestrationSession).where(
                            OrchestrationSession.session_id == session_id,
                            OrchestrationSession.user_id == user_id,
                            OrchestrationSession.tenant_id == tenant_id,
                        )
                    )
                    sess = res2.scalar_one_or_none()

                    if sess:
                        sess.message_count += 1
                        sess.last_message_at = datetime.now(timezone.utc)

                    return True

        except Exception as e:
            logger.error("append_message failed: %s", e)
            return False

    # ─────────────────────────────────────────────────────────────
    # ✅ List Sessions (History Sidebar)
    # ─────────────────────────────────────────────────────────────

    async def list_sessions(
        self,
        *,
        user_id: str,
        tenant_id: Optional[str],
    ) -> List[Dict[str, Any]]:

        if IS_LOCAL:
            sessions, _ = jdb.sessions.paginate(
                lambda s: (
                    s.get("user_id") == user_id
                    and s.get("tenant_id") == tenant_id
                    and s.get("status") != "deleted"
                ),
                sort_key="updated_at",
                reverse=True,
                skip=0,
                limit=100,
            )

            return [
                {
                    "id": s.get("id") or s.get("session_id"),
                    "title": s.get("title") or "New conversation",
                    "updatedAt": s.get("updated_at") or s.get("created_at"),
                    "messageCount": s.get("message_count", 0),
                }
                for s in sessions
            ]

        try:
            from sqlalchemy import select
            from database.session import AsyncSessionLocal
            from database.models import OrchestrationSession

            async with AsyncSessionLocal() as db:
                res = await db.execute(
                    select(OrchestrationSession)
                    .where(
                        OrchestrationSession.user_id == user_id,
                        OrchestrationSession.tenant_id == tenant_id,
                        OrchestrationSession.status != "deleted",
                    )
                    .order_by(
                        OrchestrationSession.last_message_at.desc().nullslast(),
                        OrchestrationSession.created_at.desc(),
                    )
                    .limit(100)
                )
                rows = res.scalars().all()

            return [
                {
                    "id": r.session_id,
                    "title": r.title or "New conversation",
                    "updatedAt": (
                        (r.last_message_at or r.created_at).isoformat()
                        if (r.last_message_at or r.created_at)
                        else None
                    ),
                    "messageCount": r.message_count or 0,
                }
                for r in rows
            ]

        except Exception as e:
            logger.error("list_sessions failed: %s", e)
            return []

    # ─────────────────────────────────────────────────────────────
    # ✅ Load Session (Chat screen)
    # ─────────────────────────────────────────────────────────────

    async def load_session(
        self,
        *,
        user_id: str,
        tenant_id: Optional[str],
        session_id: str,
    ) -> Optional[Dict[str, Any]]:

        if IS_LOCAL:
            sess = jdb.sessions.find_one(
                lambda s: (
                    (s.get("session_id") == session_id or s.get("id") == session_id)
                    and s.get("user_id") == user_id
                    and s.get("tenant_id") == tenant_id
                    and s.get("status") != "deleted"
                )
            )
            if not sess:
                return None

            msgs = jdb.messages.find(
                lambda m: (
                    m.get("session_id") == session_id
                    and m.get("user_id") == user_id
                    and m.get("tenant_id") == tenant_id
                )
            )
            msgs.sort(key=lambda m: m.get("created_at") or "")

            return {
                "id": session_id,
                "title": sess.get("title") or "New conversation",
                "updatedAt": sess.get("updated_at") or sess.get("created_at"),
                "messages": [self._msg_to_fe(m) for m in msgs],
            }

        try:
            from sqlalchemy import select
            from database.session import AsyncSessionLocal
            from database.models import OrchestrationSession, ChatMessage

            async with AsyncSessionLocal() as db:
                res = await db.execute(
                    select(OrchestrationSession).where(
                        OrchestrationSession.session_id == session_id,
                        OrchestrationSession.user_id == user_id,
                        OrchestrationSession.tenant_id == tenant_id,
                    )
                )
                sess = res.scalar_one_or_none()

                if not sess or sess.status == "deleted":
                    return None

                res2 = await db.execute(
                    select(ChatMessage)
                    .where(
                        ChatMessage.session_id == session_id,
                        ChatMessage.user_id == user_id,
                        ChatMessage.tenant_id == tenant_id,
                    )
                    .order_by(ChatMessage.created_at.asc())
                )
                msgs = res2.scalars().all()

            return {
                "id": session_id,
                "title": sess.title or "New conversation",
                "updatedAt": (sess.last_message_at or sess.created_at).isoformat(),
                "messages": [self._orm_msg_to_fe(m) for m in msgs],
            }

        except Exception as e:
            logger.error("load_session failed: %s", e)
            return None

    # ─────────────────────────────────────────────────────────────
    # ✅ Rename Session
    # ─────────────────────────────────────────────────────────────

    async def rename_session(
        self,
        *,
        user_id: str,
        tenant_id: Optional[str],
        session_id: str,
        title: str,
    ) -> bool:

        try:
            from sqlalchemy import update
            from database.session import AsyncSessionLocal
            from database.models import OrchestrationSession

            async with AsyncSessionLocal() as db:
                async with db.begin():
                    res = await db.execute(
                        update(OrchestrationSession)
                        .where(
                            OrchestrationSession.session_id == session_id,
                            OrchestrationSession.user_id == user_id,
                            OrchestrationSession.tenant_id == tenant_id,
                        )
                        .values(
                            title=(title or "")[:200] or "Untitled",
                            last_message_at=datetime.now(timezone.utc),
                        )
                    )

            return getattr(res, "rowcount", 0) > 0

        except Exception as e:
            logger.error("rename_session failed: %s", e)
            return False

    # ─────────────────────────────────────────────────────────────
    # ✅ Delete Session (soft delete)
    # ─────────────────────────────────────────────────────────────

    async def delete_session(
        self,
        *,
        user_id: str,
        tenant_id: Optional[str],
        session_id: str,
    ) -> bool:

        try:
            from sqlalchemy import delete, update
            from database.session import AsyncSessionLocal
            from database.models import OrchestrationSession, ChatMessage

            async with AsyncSessionLocal() as db:
                async with db.begin():

                    # delete messages
                    await db.execute(
                        delete(ChatMessage).where(
                            ChatMessage.session_id == session_id,
                            ChatMessage.user_id == user_id,
                            ChatMessage.tenant_id == tenant_id,
                        )
                    )

                    # soft delete session
                    res = await db.execute(
                        update(OrchestrationSession)
                        .where(
                            OrchestrationSession.session_id == session_id,
                            OrchestrationSession.user_id == user_id,
                            OrchestrationSession.tenant_id == tenant_id,
                        )
                        .values(
                            status="deleted",
                            title="[Deleted]",
                            message_count=0,
                            last_message_at=None,
                        )
                    )

            return getattr(res, "rowcount", 0) > 0

        except Exception as e:
            logger.error("delete_session failed: %s", e)
            return False

    # ─────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────

    @staticmethod
    def _fe_type_to_role(t: Optional[str]) -> str:
        if t == "user":
            return "user"
        if t in ("ai", "bot", "assistant"):
            return "assistant"
        return "system"

    @staticmethod
    def _msg_to_fe(m: Dict) -> Dict:
        return m.get("data") or {
            "type": m.get("type") or m.get("role") or "user",
            "content": m.get("content", ""),
        }

    @staticmethod
    def _orm_msg_to_fe(m) -> Dict:
        role = m.role or "user"
        return {
            "type": "user" if role == "user" else "ai",
            "content": m.content or "",
            "createdAt": m.created_at.isoformat() if m.created_at else None,
        }


chat_history_service = ChatHistoryService()
