"""
routers/history_router.py — REST API for chat history (session-based).

✅ Uses session_id as single source of truth
✅ No full conversation overwrite
✅ Works with SessionManager (ADK-backed sessions)
✅ Clean contract for frontend + middleware

Endpoints
─────────
GET    /api/history/sessions                → list sessions
GET    /api/history/sessions/{session_id}   → load chat history
POST   /api/history/messages                → append single message
PATCH  /api/history/sessions/{session_id}   → rename
DELETE /api/history/sessions/{session_id}   → delete
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from services.chat_history_service import chat_history_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/history", tags=["chat-history"])


# ────────────────────────────────────────────────────────────────────────────
# ✅ Identity from middleware headers
# ────────────────────────────────────────────────────────────────────────────

def _identity(request: Request) -> dict:
    uid = request.headers.get("x-user-id", "").strip()
    tid = request.headers.get("x-tenant-id", "").strip()

    if not uid:
        raise HTTPException(401, "Authentication required for chat history")

    return {"user_id": uid, "tenant_id": tid or None}


# ────────────────────────────────────────────────────────────────────────────
# ✅ Schemas
# ────────────────────────────────────────────────────────────────────────────

class _Msg(BaseModel):
    type: str = "user"
    content: Any = None
    model_config = {"extra": "allow"}


class _AppendBody(BaseModel):
    session_id: str
    message: _Msg


class _RenameBody(BaseModel):
    title: str


# ────────────────────────────────────────────────────────────────────────────
# ✅ Append Message (CORE WRITE API)
# ────────────────────────────────────────────────────────────────────────────

@router.post("/messages")
async def append_message(
    body: _AppendBody,
    request: Request,
    identity=Depends(_identity),
):
    session_manager = request.app.state.session_manager

    ok = await chat_history_service.append_message(
        session_manager=session_manager,
        user_id=identity["user_id"],
        tenant_id=identity.get("tenant_id"),
        session_id=body.session_id,
        message=body.message.model_dump(),
    )

    if not ok:
        raise HTTPException(500, "Failed to save message")

    return {"ok": True}


# ────────────────────────────────────────────────────────────────────────────
# ✅ List Sessions (Sidebar)
# ────────────────────────────────────────────────────────────────────────────

@router.get("/sessions")
async def list_sessions(identity=Depends(_identity)):

    sessions = await chat_history_service.list_sessions(
        user_id=identity["user_id"],
        tenant_id=identity.get("tenant_id"),
    )

    return {"sessions": sessions}


# ────────────────────────────────────────────────────────────────────────────
# ✅ Load Session (Chat View)
# ────────────────────────────────────────────────────────────────────────────

@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    request: Request,
    identity=Depends(_identity),
):
    session_manager = request.app.state.session_manager

    # ✅ optional safety: ensure session exists in ADK
    await session_manager.ensure_session(
        identity["user_id"],
        session_id,
    )

    convo = await chat_history_service.load_session(
        user_id=identity["user_id"],
        tenant_id=identity.get("tenant_id"),
        session_id=session_id,
    )

    if not convo:
        raise HTTPException(404, "Session not found")

    return convo


# ────────────────────────────────────────────────────────────────────────────
# ✅ Rename Session
# ────────────────────────────────────────────────────────────────────────────

@router.patch("/sessions/{session_id}")
async def rename_session(
    session_id: str,
    body: _RenameBody,
    identity=Depends(_identity),
):
    ok = await chat_history_service.rename_session(
        user_id=identity["user_id"],
        tenant_id=identity.get("tenant_id"),
        session_id=session_id,
        title=body.title.strip(),
    )

    if not ok:
        raise HTTPException(404, "Session not found")

    return {
        "ok": True,
        "title": body.title.strip()[:200] or "Untitled",
    }


# ────────────────────────────────────────────────────────────────────────────
# ✅ Delete Session
# ────────────────────────────────────────────────────────────────────────────

@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    identity=Depends(_identity),
):
    ok = await chat_history_service.delete_session(
        user_id=identity["user_id"],
        tenant_id=identity.get("tenant_id"),
        session_id=session_id,
    )

    if not ok:
        raise HTTPException(404, "Session not found")

    return {"ok": True}