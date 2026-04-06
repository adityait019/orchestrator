from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from core.runner_factory import create_runner
from routers.agent_registry import router as agent_router
from routers.upload_router import router as upload_router
from routers.file_router import router as file_router

from websocket.websocket_handler import WebSocketHandler

from services.workflow_service import WorkflowService
from services.agent_execution_service import AgentExecutionService
from services.artifact_service import ArtifactService
from session.session_manager import SessionManager
from database.session import AsyncSessionLocal

import os

APP_NAME = "my_agent_app"
DEFAULT_USER = "default_user"

app = FastAPI(title="Orchestrator Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(agent_router)
app.include_router(upload_router)
app.include_router(file_router)

# Core services
session_manager = SessionManager(db_url=os.getenv("DATABASE_URL"))
session_service = session_manager.session_service

runner = create_runner(session_service)

workflow_service = WorkflowService(AsyncSessionLocal)
agent_service = AgentExecutionService(AsyncSessionLocal, session_service)
artifact_service = ArtifactService(AsyncSessionLocal)

# WebSocket handler
ws_handler = WebSocketHandler(
    runner,
    session_service,
    workflow_service,
    agent_service,
    artifact_service,
)

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await ws_handler.handle(websocket, session_id, DEFAULT_USER)