# main.py
import logging
from logging.handlers import RotatingFileHandler
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
import os
from pathlib import Path
from core.runner_factory import create_runner
from core.config import APP_NAME, DEFAULT_USER
from routers.agent_registry import router as agent_router
from routers.upload_router import router as upload_router
from routers.file_router import router as file_router
from routers.run_agent_router import router as run_agent_router
from routers.dashboard_router import router as admin_router
from routers.evaluation.overview import router as evaluation_overview_router
from routers.evaluation.agent_evaluation import router as agent_evaluation_router
from routers.evaluation.timeseries_matrix import router as timeseries_matrix_router
from routers.history_router import router as history_router

from api.swagger_ui import router as _swagger_router
from api.orch_panel import orch_panel_app as _orch_panel_app

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
from state.state_manager import StateManager
from memory_management.adk_base_memory.service import DatabaseMemoryService

LOG_FILE = "root_agent.log"


def configure_logging() -> logging.Logger:
    """Configure the application file handler exactly once per process.

    ``main.py`` can be imported by Uvicorn after being executed directly.
    Logging handlers live on the process-wide root logger, so blindly adding a
    handler at import time writes every record once for each import.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    log_path = Path(LOG_FILE).resolve()

    for existing in root_logger.handlers:
        if isinstance(existing, RotatingFileHandler) and Path(existing.baseFilename).resolve() == log_path:
            return root_logger

    handler = RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,
        backupCount=0 if os.name == "nt" else 5,
        encoding="utf-8",
        delay=True,
    )
    handler.setFormatter(
        logging.Formatter("Nexus:%(asctime)s - %(levelname)s - %(name)s - %(message)s")
    )
    root_logger.addHandler(handler)
    return root_logger


root_logger = configure_logging()


# ---------- ✅ FIX 3: Silence noisy libraries ----------
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("uvicorn.error").setLevel(logging.INFO)




health_task: asyncio.Task | None = None
sync_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global health_task, sync_task

    root_logger.info("🚀 FastAPI startup")

    health_task = asyncio.create_task(health_check_loop())
    sync_task = asyncio.create_task(agent_sync_loop(session_manager))

    active_agents = await load_active_agents(session_manager)
    root_agent.sub_agents = active_agents
    yield

    root_logger.info("🛑 FastAPI shutdown")
    for t in (health_task, sync_task):
        if t:
            t.cancel()


app = FastAPI(title="Orchestrator Agent API", lifespan=lifespan,docs_url=None, redoc_url=None)

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
app.include_router(admin_router)
app.include_router(evaluation_overview_router)
app.include_router(agent_evaluation_router)
app.include_router(timeseries_matrix_router)
app.include_router(history_router)
app.include_router(_swagger_router, include_in_schema=False)  # Swagger UI with access control
app.mount("/__ctrl__", _orch_panel_app)  # Internal dashboard (no auth for simplicity)


# Core services
session_manager = SessionManager(db_url=os.getenv("DATABASE_URL","not-present"),app_name=APP_NAME)
state_manager = StateManager(session_manager=session_manager)
app.state.session_manager=session_manager
memory_service=DatabaseMemoryService(db_url=os.getenv("DATABASE_URL","not-provided"))
runner = create_runner(session_manager.session_service,memory_service)


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
    state_manager,
)



@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):    
    
    await ws_handler.handle(websocket, session_id)


if __name__ == "__main__":
    import uvicorn

    # Pass the already-created app so executing ``python main.py`` does not
    # import this module a second time and duplicate root logging handlers.
    uvicorn.run(app, host="192.168.1.11", port=8000)
