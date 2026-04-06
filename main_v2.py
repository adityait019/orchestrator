from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from core.runner_factory import create_runner
from core.config import APP_NAME, DEFAULT_USER
from routers.agent_registry import router as agent_router
from routers.upload_router import router as upload_router
from routers.file_router import router as file_router
from routers.run_agent_router import router as run_agent_router
from websocket.websocket_handler import WebSocketHandler
import logging
from services.workflow_service import WorkflowService
from services.agent_execution_service import AgentExecutionService
from services.artifact_service import ArtifactService
from services.file_service import FileService
from session.session_manager import SessionManager
from database.session import AsyncSessionLocal
from contextlib import asynccontextmanager
from agent_registry.health_monitor import health_check_loop
from services.agent_loader import load_active_agents
from services.agent_sync_service  import agent_sync_loop
from agents.agent import root_agent
import os
import asyncio
active_agents = []
health_task: asyncio.Task | None= None
sync_task: asyncio.Task | None= None

logger = logging.getLogger(__name__)
@asynccontextmanager
async def lifespan(app: FastAPI):
    global health_task, sync_task

    logger.info("Starting FastAPI lifespan")

    # Start health monitor
    if health_task is None or health_task.done():
        health_task = asyncio.create_task(health_check_loop())

    if sync_task is None or sync_task.done():
        sync_task = asyncio.create_task(agent_sync_loop())

    try:
        active_agents = await load_active_agents()

        if not active_agents:
            logger.warning("⚠️ No active agents were loaded")

        root_agent.sub_agents = active_agents
        logger.info("✅ %d agents registered with orchestrator", len(active_agents))

        yield

    except Exception as ex:
        logger.exception("❌ Failed during application startup: %s", ex)
        raise  # fail fast (recommended)

    finally:
        logger.info("Stopping FastAPI lifespan")

        if health_task:
            health_task.cancel()
        
            try:
                await health_task
            except asyncio.CancelledError:
                pass
        if sync_task:
            sync_task.cancel()
            try:
                await sync_task
            except asyncio.CancelledError:
                pass

app = FastAPI(title="Orchestrator Agent API",lifespan=lifespan)

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
session_manager = SessionManager(db_url=os.getenv("DATABASE_URL"))

BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000")
runner = create_runner(session_manager.session_service)

file_service = FileService(
    signing_secret=os.getenv("SECRET_KEY", "dev-only-secret"),
    base_url=BASE_URL,)

workflow_service = WorkflowService(AsyncSessionLocal)
agent_service = AgentExecutionService(AsyncSessionLocal, session_manager.session_service)
artifact_service = ArtifactService(AsyncSessionLocal)

# WebSocket handler
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