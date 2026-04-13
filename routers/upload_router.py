from fastapi import APIRouter, Form, HTTPException, UploadFile, File,Request
import uuid
import shutil
from pathlib import Path
from datetime import datetime
from fastapi.responses import JSONResponse
from typing import Dict, List
import logging
from services.file_service import FileService 
from session.session_manager import SessionManager
from core.config import APP_NAME, DEFAULT_USER
import os

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/upload", tags=["Upload"])


UPLOAD_DIR = Path("upload_folder")

PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000")
file_saver = Path("upload_folder")
file_service = FileService(
    signing_secret=os.getenv("SECRET_KEY", "dev-only-secret"),
    base_url=PUBLIC_BASE_URL,
)



@router.post("/")
async def upload_files(request:Request,files: List[UploadFile] = File(...), session_id: str = Form("main")):
    session_manager=request.app.state.session_manager
    file_id = uuid.uuid4().hex
    target_dir = file_saver / file_id

    try:
        file_saver.mkdir(exist_ok=True)
        target_dir.mkdir(exist_ok=True)

        uploaded_files = []
        for uploaded_file in files:
            project_path = target_dir / str(uploaded_file.filename)
            with open(project_path, "wb") as buffer:
                shutil.copyfileobj(uploaded_file.file, buffer)

            uploaded_files.append({
                "file_name": uploaded_file.filename,
                "file_path": str(project_path),
                "file_size": project_path.stat().st_size,
            })

        for f in uploaded_files:
            f["file_url"] = file_service.make_signed_url(file_id, f["file_name"])

        upload_details = {
            "file_id": file_id,
            "files": uploaded_files,
            "file_urls": [f["file_url"] for f in uploaded_files],
            "timestamp": datetime.now().isoformat(),
            "file_count": len(uploaded_files),
        }

        await session_manager.set_last_upload(
            user_id=DEFAULT_USER,
            session_id=session_id,
            upload_details=upload_details,
        )

 

        logger.info(f"Uploaded file successfully {file_id}, {session_id}, {uploaded_files} total file count {len(uploaded_files)}")
        return JSONResponse({
            "status": "success",
            "file_id": file_id,
            "session_id": session_id,
            "files_uploaded": uploaded_files,
            "file_count": len(uploaded_files),
        })

    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))