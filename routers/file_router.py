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
@router.get("/{file_id}/{filename}")
async def get_file(file_id: str, filename: str, exp: int = Query(...), sig: str = Query(...)):
    if not file_service.verify_sig(file_id, filename, exp, sig):
        raise HTTPException(status_code=403, detail="Invalid or expired signature")

    async with AsyncSessionLocal() as db:
        result=await db.execute(
            select(Artifact).where(
                Artifact.file_id==file_id,
                Artifact.filename==filename
            )
        )
        artifact=result.scalar_one_or_none()
        if artifact:
            path=Path(artifact.path)
            if path.exists():
                return FileResponse(
                    str(path),
                    media_type="application/octet-stream",
                    filename=filename
                )
    path = FILE_ROOT / file_id / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(str(path), media_type="application/octet-stream", filename=filename)