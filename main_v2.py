# main.py
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
import logging
import os

from core.runner_factory import create_runner
from core.config import APP_NAME, DEFAULT_USER
from routers.agent_registry import router as agent_router
from routers.upload_router import router as upload_router
from routers.file_router import router as file_router
from routers.run_agent_router import router as run_agent_router

from websocket.websocket_handler import WebSocketHandler

from services.workflow_service import WorkflowService
from services.agent_execution_service import AgentExecutionService
from services.artifact_service import ArtifactService
from services.file_service import FileService
from services.agent_loader import load_active_agents
from services.agent_sync_service import agent_sync_loop

from session.session_manager import SessionManager
from database.session import AsyncSessionLocal
from agent_registry.health_monitor import health_check_loop
from agents.agent import root_agent

logger = logging.getLogger(__name__)

health_task: asyncio.Task | None = None
sync_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global health_task, sync_task

    logger.info("🚀 FastAPI startup")

    health_task = asyncio.create_task(health_check_loop())
    sync_task = asyncio.create_task(agent_sync_loop())

    active_agents = await load_active_agents()
    root_agent.sub_agents = active_agents

    yield

    logger.info("🛑 FastAPI shutdown")
    for t in (health_task, sync_task):
        if t:
            t.cancel()


app = FastAPI(title="Orchestrator Agent API", lifespan=lifespan)

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
app.include_router(run_agent_router)

# Core services
session_manager = SessionManager(db_url=os.getenv("DATABASE_URL","not-present"),app_name=APP_NAME)

app.state.session_manager=session_manager

runner = create_runner(session_manager.session_service)

file_service = FileService(
    signing_secret=os.getenv("FILE_SIGNING_SECRET", "dev-only-secret"),
    base_url=os.getenv("PUBLIC_BASE_URL", "http://localhost:8000"),
)

workflow_service = WorkflowService(AsyncSessionLocal)
agent_service = AgentExecutionService(AsyncSessionLocal, session_manager.session_service)
artifact_service = ArtifactService(AsyncSessionLocal)

ws_handler = WebSocketHandler(
    runner,
    session_manager,
    workflow_service,
    agent_service,
    artifact_service,
    file_service,
)


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await ws_handler.handle(websocket, session_id, DEFAULT_USER)



if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="192.168.1.5", port=8000)