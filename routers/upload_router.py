from fastapi import APIRouter, Form, HTTPException, UploadFile, File
import uuid
import shutil
from pathlib import Path
from datetime import datetime
from fastapi.responses import JSONResponse
from typing import Dict, List
import logging
from main import APP_NAME
from services.file_service import FileService 
from session.session_manager import SessionManager
import os

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/upload", tags=["Upload"])


UPLOAD_DIR = Path("upload_folder")

PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://10.73.83.83:8000")
file_saver = Path("upload_folder")
file_service = FileService(
    signing_secret="dev-only-secret",
    base_url=PUBLIC_BASE_URL,
)
DEFAULT_USER = "default_user"
session_manager = SessionManager(db_url=os.getenv("DATABASE_URL"))
active_session=session_manager.active_sessions


@router.post("/upload")
async def upload_files(files: List[UploadFile] = File(...), session_id: str = Form("main")):
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

        active_session.setdefault(session_id, {"context": {}})
        active_session[session_id]["last_upload"] = upload_details

 
        # Ensure session exists but DO NOT store uploads in DB state
        session = await session_manager.get_session(
            app_name=APP_NAME,
            user_id=DEFAULT_USER,
            session_id=session_id,
        )

        if not session:
            session = await session_manager.create_session(
                app_name=APP_NAME,
                user_id=DEFAULT_USER,
                session_id=session_id,
            )

        # ✅ Store uploads only in active_session (one-turn context)
        active_session.setdefault(session_id, {})
        active_session[session_id]["last_upload"] = upload_details        

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