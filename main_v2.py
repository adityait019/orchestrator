from __future__ import annotations

import asyncio
import logging
import mimetypes
import os
import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from dotenv import load_dotenv
from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    WebSocket
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

# ADK
from google.adk.runners import Runner
from google.adk.sessions.database_session_service import DatabaseSessionService
from google.genai.types import Content, Part, FileData

# Root agent
from agents.agent import root_agent

# Router
from routers.agent_registry import router as agent_router

# Agent discovery
from services.agent_loader import load_active_agents

# Health monitor
from agent_registry.health_monitor import health_check_loop

# Database
from database.session import AsyncSessionLocal
from database.models import Artifact
from sqlalchemy import select

# Helpers
from tools.helper_downloads import fetch_remote_file

# Services
from services.workflow_service import WorkflowService
from services.agent_execution_service import AgentExecutionService
from services.artifact_service import ArtifactService
from services.file_service import FileService

# Websocket handler
from websocket.websocket_handler import WebSocketHandler


# -------------------------------------------------------------------
# Setup
# -------------------------------------------------------------------

load_dotenv(override=True)

logging.basicConfig(level=logging.INFO, filename="app.log", filemode="a")

logger = logging.getLogger(__name__)

APP_NAME = "my_agent_app"
DEFAULT_USER = "default_user"

DATABASE_URL = os.getenv("DATABASE_URL")

FILE_SIGNING_SECRET = os.getenv("FILE_SIGNING_SECRET", "dev-secret")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")

UPLOAD_DIR = Path("upload_folder")

active_session: Dict[str, Dict] = {}

# -------------------------------------------------------------------
# Lifespan
# -------------------------------------------------------------------

active_agents = []


@asynccontextmanager
async def lifespan(app: FastAPI):

    global active_agents

    task = asyncio.create_task(health_check_loop())

    active_agents = await load_active_agents()

    root_agent.sub_agents = active_agents

    logger.info("+++ HEALTH MONITOR START +++")

    yield

    task.cancel()

    logger.info("--- HEALTH MONITOR STOPPED ---")


# -------------------------------------------------------------------
# App
# -------------------------------------------------------------------

app = FastAPI(title="Orchestrator Agent API", lifespan=lifespan)

app.include_router(agent_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL=os.getenv('DATABASE_URL',"not-provided")
# -------------------------------------------------------------------
# Session + Runner
# -------------------------------------------------------------------

session_service = DatabaseSessionService(db_url=DATABASE_URL)

runner = Runner(
    agent=root_agent,
    app_name=APP_NAME,
    session_service=session_service,
)

# -------------------------------------------------------------------
# Services
# -------------------------------------------------------------------

workflow_service = WorkflowService(AsyncSessionLocal)

agent_service = AgentExecutionService(
    AsyncSessionLocal,
    session_service,
)

artifact_service = ArtifactService(AsyncSessionLocal)

file_service = FileService(
    signing_secret=FILE_SIGNING_SECRET,
    base_url=PUBLIC_BASE_URL,
)

# -------------------------------------------------------------------
# WebSocket Handler
# -------------------------------------------------------------------

ws_handler = WebSocketHandler(
    runner=runner,
    session_service=session_service,
    workflow_service=workflow_service,
    agent_service=agent_service,
    artifact_service=artifact_service,
)

# -------------------------------------------------------------------
# Signed file endpoint
# -------------------------------------------------------------------


@app.get("/files/{file_id}/{filename}")
async def get_file(
    file_id: str,
    filename: str,
    exp: int = Query(...),
    sig: str = Query(...),
):

    if not file_service.verify_sig(file_id, filename, exp, sig):
        raise HTTPException(status_code=403, detail="Invalid signature")

    async with AsyncSessionLocal() as db:

        result = await db.execute(
            select(Artifact).where(
                Artifact.file_id == file_id,
                Artifact.filename == filename,
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

    path = UPLOAD_DIR / file_id / filename

    if not path.exists():

        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(str(path))


# -------------------------------------------------------------------
# Upload endpoint
# -------------------------------------------------------------------


@app.post("/upload")
async def upload_files(
    files: List[UploadFile] = File(...),
    session_id: str = Form("main"),
):

    file_id = uuid.uuid4().hex

    target_dir = UPLOAD_DIR / file_id

    UPLOAD_DIR.mkdir(exist_ok=True)

    target_dir.mkdir(exist_ok=True)

    uploaded_files = []

    for uploaded_file in files:

        path = target_dir / str(uploaded_file.filename)

        with open(path, "wb") as buffer:

            shutil.copyfileobj(uploaded_file.file, buffer)

        signed_url = file_service.make_signed_url(
            file_id,
            str(uploaded_file.filename),
        )

        uploaded_files.append(
            {
                "file_name": uploaded_file.filename,
                "file_path": str(path),
                "file_url": signed_url,
            }
        )

    upload_details = {
        "file_id": file_id,
        "files": uploaded_files,
        "file_urls": [f["file_url"] for f in uploaded_files],
        "timestamp": datetime.now().isoformat(),
    }

    active_session.setdefault(session_id, {"context": {}})

    active_session[session_id]["last_upload"] = upload_details

    return JSONResponse(
        {
            "status": "success",
            "file_id": file_id,
            "files_uploaded": uploaded_files,
        }
    )


# -------------------------------------------------------------------
# WebSocket
# -------------------------------------------------------------------


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):

    await ws_handler.handle(
        websocket,
        session_id,
        DEFAULT_USER,
    )


# -------------------------------------------------------------------
# Run server
# -------------------------------------------------------------------

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
    )