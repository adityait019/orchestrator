from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pathlib import Path
import os
from database.session import AsyncSessionLocal
from database.models import Artifact
from services.file_service import FileService
from sqlalchemy import select

router = APIRouter(prefix="/files", tags=["Files"])



file_service = FileService(
    signing_secret=os.getenv("SECRET_KEY", "dev-only-secret"),
    base_url=os.getenv("PUBLIC_BASE_URL", "http://localhost:8000"),
)
FILE_ROOT = Path("upload_folder")

@router.get(
    "/{tenant_id}/{user_id}/{session_id}/{file_id}/{filename}"
)
async def get_file(
    tenant_id: str,
    user_id: str,
    session_id: str,
    file_id: str,
    filename: str,
    exp: int = Query(...),
    sig: str = Query(...),
):
    # -------------------------------------------------
    # ✅ Verify signed URL
    # -------------------------------------------------
    if not file_service.verify_sig(
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        file_id=file_id,
        filename=filename,
        exp=exp,
        sig=sig,
    ):
        raise HTTPException(status_code=403, detail="Invalid or expired signature")

    # -------------------------------------------------
    # ✅ Artifact lookup (optional but safe)
    # -------------------------------------------------
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Artifact).where(
                Artifact.file_id == file_id,
                Artifact.filename == filename,
                Artifact.user_id == user_id,
                Artifact.tenant_id == tenant_id,
                Artifact.session_id == session_id,
            )
        )
        artifact = result.scalar_one_or_none()

        if artifact:
            path = Path(artifact.path)
            if path.exists():
                return FileResponse(
                    str(path),
                    media_type="application/octet-stream",
                    filename=filename,
                )

    # -------------------------------------------------
    # ✅ Filesystem fallback (strict path)
    # -------------------------------------------------
    safe_path = (
        FILE_ROOT
        / tenant_id
        / user_id
        / session_id
        / file_id
        / filename
    ).resolve()

    # 🚨 Prevent directory traversal
    expected_root = (
        FILE_ROOT / tenant_id / user_id / session_id / file_id
    ).resolve()

    if not str(safe_path).startswith(str(expected_root)):
        raise HTTPException(status_code=403, detail="Invalid file path")

    if not safe_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        str(safe_path),
        media_type="application/octet-stream",
        filename=filename,
    )
