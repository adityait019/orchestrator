"""
routes/upload.py — File upload endpoint (segregated by tenant/user/session).

Storage layout (all uploads are strictly isolated):

    upload_folder/
    └── {tenant_id}/
        └── {user_id}/
            └── {session_id}/       ← WS session, ties file to conversation
                └── {file_id}/      ← UUID per upload batch
                    └── {filename}

Auth: Bearer token in the Authorization header, verified by calling the
tenant service /auth/me. The middleware always injects this token when
proxying file uploads from the browser (the browser itself never holds
the JWT — it uses an HttpOnly cookie).

The session_id comes from the browser's form data. It matches the WS
session_id so the orchestrator can attach the uploaded file to the
right conversation context.
"""
from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List
import uuid
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import JSONResponse

from auth.deps import get_current_user
from services.file_service import FileService
from session.session_manager import SessionManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/upload", tags=["Upload"])

UPLOAD_DIR = Path("upload_folder")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000")

file_service = FileService(
    signing_secret=os.getenv("SECRET_KEY", "dev-only-secret"),
    base_url=PUBLIC_BASE_URL,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helper: idempotent ensure_session
# (same fix as ws_handler — AlreadyExistsError = session already open, resume)
# ─────────────────────────────────────────────────────────────────────────────
async def _ensure_session_idempotent(
    session_manager: SessionManager,
    user_id: str,
    session_id: str,
) -> None:
    try:
        await session_manager.ensure_session(user_id=user_id, session_id=session_id)
    except Exception as e:
        if "AlreadyExists" in type(e).__name__ or "already exists" in str(e).lower():
            logger.debug(
                "Session %s already exists for user %s — resuming for upload.",
                session_id, user_id,
            )
        else:
            raise


# ─────────────────────────────────────────────────────────────────────────────
# POST /upload/ — multi-file upload with full isolation
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/")
async def upload_files(
    request: Request,
    files: List[UploadFile] = File(...),
    session_id: str = Form(...),
    current_user: dict = Depends(get_current_user),
):
    """
    Upload one or more files, segregated by tenant / user / session / file_id.

    Authentication
    --------------
    The BFF middleware injects `Authorization: Bearer <jwt>` on every
    proxied upload. `get_current_user` verifies the JWT with the tenant
    service and returns {user_id, tenant_id, roles}.

    The browser NEVER calls this endpoint directly — it goes through the
    middleware's /upload proxy which enforces the session cookie check
    before forwarding here.

    Storage path
    ------------
    upload_folder/{tenant_id}/{user_id}/{session_id}/{file_id}/{filename}

    session_id is the WebSocket session that spawned this conversation,
    so every file is tied to the exact conversation it was uploaded in.
    """
    session_manager: SessionManager = request.app.state.session_manager

    user_id = current_user["user_id"]
    tenant_id = current_user["tenant_id"]

    if not user_id or not tenant_id:
        raise HTTPException(status_code=401, detail="Invalid authenticated user")

    # Create/resume the session (idempotent — won't throw if WS already
    # created it).
    await _ensure_session_idempotent(session_manager, user_id, session_id)

    file_id = uuid.uuid4().hex

    # Fully-scoped storage path: no file from one user/session can
    # collide with or be accessed by another.
    target_dir = UPLOAD_DIR / tenant_id / user_id / session_id / file_id

    try:
        target_dir.mkdir(parents=True, exist_ok=True)

        uploaded_files: list[dict] = []

        for uploaded_file in files:
            # Prevent path traversal via crafted filenames.
            safe_name = os.path.basename(uploaded_file.filename or "unknown_file")
            file_path = target_dir / safe_name

            with open(file_path, "wb") as buf:
                shutil.copyfileobj(uploaded_file.file, buf)

            uploaded_files.append(
                {
                    "file_name": safe_name,
                    "file_path": str(file_path),
                    "file_size": file_path.stat().st_size,
                }
            )

        # Generate signed download URLs so the browser can fetch the files
        # back through /files/... without needing a bearer token.
        for f in uploaded_files:
            f["file_url"] = file_service.make_signed_url(
                tenant_id=tenant_id,
                user_id=user_id,
                session_id=session_id,
                file_id=file_id,
                filename=f["file_name"],
            )

        upload_details = {
            "file_id": file_id,
            "files": uploaded_files,
            "file_urls": [f["file_url"] for f in uploaded_files],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "file_count": len(uploaded_files),
        }

        # Attach to the session so the WS handler can reference the files.
        await session_manager.set_last_upload(
            user_id=user_id,
            session_id=session_id,
            upload_details=upload_details,
        )

        logger.info(
            "✅ Uploaded %d file(s) | tenant=%s | user=%s | session=%s | file_id=%s",
            len(uploaded_files),
            tenant_id,
            user_id,
            session_id,
            file_id,
        )

        return JSONResponse(
            {
                "status": "success",
                "user_id": user_id,
                "tenant_id": tenant_id,
                "session_id": session_id,
                "file_id": file_id,
                "file_count": len(uploaded_files),
                "files": uploaded_files,
                # Convenience: flat list of signed URLs, easiest for the
                # frontend to attach to the next WS message.
                "file_urls": [f["file_url"] for f in uploaded_files],
            }
        )

    except Exception as e:
        logger.exception("❌ Upload failed")
        raise HTTPException(status_code=500, detail=str(e))