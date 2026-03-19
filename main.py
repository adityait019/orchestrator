# main.py

from __future__ import annotations
import hashlib
import hmac
import json
import logging
import os
import re
import shutil
import time
import uuid
import mimetypes
from datetime import datetime,timezone
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import quote, urlparse, unquote

from dotenv import load_dotenv
from fastapi import (
    FastAPI, File, Form, HTTPException, Query,
    UploadFile, WebSocket, WebSocketDisconnect
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

# ADK Framework
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
# from google.adk.sessions.database_session_service import DatabaseSessionService
from google.adk.sessions.base_session_service import GetSessionConfig
from google.genai.types import Content, Part, FileData
import html
# Root Agent
from agents.agent import root_agent


#Router Setup for Agent Registry

from routers.agent_registry import router as agent_router
from contextlib import asynccontextmanager
from agent_registry.health_monitor import health_check_loop
import asyncio

#Dynamic Agent Discovery
from services.agent_loader import load_active_agents

#Invocation Tracking.

from database.session import AsyncSessionLocal
from database.models import OrchestrationSession
from database.models import AgentInvocation
from dataclasses import dataclass
from sqlalchemy import select

#Artifact Tracking


from database.models import Artifact
from tools.helper_downloads import fetch_remote_file


#Agent Event Tracking

from database.models import AgentEvent
# --------------------------------------------------------------------
# Setup
# --------------------------------------------------------------------



@dataclass
class InvocationContext:
    id:int | None =None
    agent_name:str | None =None
    agent_session_id:str | None= None 
    buffer:str =""

    
load_dotenv(override=True)

DATABASE_URL=os.getenv("DATABASE_URL","NOT PROVIDDED")

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)

logging.basicConfig(level=logging.INFO,filename='app.log',filemode='a')

APP_NAME = "my_agent_app"
DEFAULT_USER = "default_user"
SHOW_RAW_TOOL_EVENTS = True  # flip to True when you want to see raw 

active_agents=[]
@asynccontextmanager
async def lifespan(app:FastAPI):
    global active_agents
    task=asyncio.create_task(health_check_loop())
    
    active_agents=await load_active_agents()
    root_agent.sub_agents=active_agents
    # active_agents=await load_active_agents()

    logger.info("+++ HEALTH MONITOR START +++")
    yield
    task.cancel()
    logger.info("--- HEALTH MONITOR STOPPED ---")


app = FastAPI(title="Orchestrator Agent API", lifespan=lifespan)

app.include_router(agent_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"]
)

# session_service = DatabaseSessionService(
#     db_url=DATABASE_URL
# )

session_service=InMemorySessionService()
active_session: Dict[str, Dict] = {}

file_saver = Path("upload_folder")


runner = Runner(
    agent=root_agent,
    app_name=APP_NAME,
    session_service=session_service,
)


def debug_event(event):
    info = {
        "author": getattr(event, "author", None),
        "text": getattr(event, "text", None),
        "error": getattr(event, "error_message", None),
    }

    content = getattr(event, "content", None)
    if content and getattr(content, "parts", None):
        parts = []
        for p in content.parts:
            if getattr(p, "text", None):
                parts.append({"type": "text", "value": p.text})

            if getattr(p, "function_call", None):
                parts.append({
                    "type": "function_call",
                    "name": p.function_call.name,
                    "args": p.function_call.args
                })

            if getattr(p, "function_response", None):
                parts.append({
                    "type": "function_response",
                    "name": p.function_response.name
                })

            if getattr(p, "file_data", None):
                parts.append({
                    "type": "file",
                    "uri": getattr(p.file_data, "file_uri", None)
                })

        info["parts"] = parts

    metadata = getattr(event, "custom_metadata", None)
    if metadata:
        info["metadata"] = metadata

    return info
# --------------------------------------------------------------------
# Signed URL helpers
# --------------------------------------------------------------------

FILE_ROOT = file_saver
FILE_URL_TTL = 10 * 60
SIGNING_SECRET = os.environ.get("FILE_SIGNING_SECRET", "dev-only-secret")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://10.73.83.83:8000")

AGENT_RESOURCE_DIRECTORY=Path("download")

def _sign_token(file_id: str, filename: str, exp: int) -> str:
    msg = f"{file_id}:{filename}:{exp}".encode("utf-8")
    return hmac.new(SIGNING_SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def make_signed_url(file_id: str, filename: str) -> str:
    encoded_filename = quote(filename, safe="")
    exp = int(time.time()) + FILE_URL_TTL
    sig = _sign_token(file_id, filename, exp)
    url = f"{PUBLIC_BASE_URL}/files/{file_id}/{encoded_filename}?exp={exp}&sig={sig}"
    logger.info(f"[signed_url] {url}")
    return url


def verify_sig(file_id: str, filename: str, exp: int, sig: str) -> bool:
    if exp < int(time.time()):
        return False
    return hmac.compare_digest(sig, _sign_token(file_id, filename, exp))


@app.get("/files/{file_id}/{filename}")
async def get_file(file_id: str, filename: str, exp: int = Query(...), sig: str = Query(...)):
    if not verify_sig(file_id, filename, exp, sig):
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


# --------------------------------------------------------------------
# File context attachment to user message
# --------------------------------------------------------------------

async def _attach_last_upload_parts(parts: List[Part], session_id: str) -> List[Part]:
    try:
        sess = await session_service.get_session(
            app_name=APP_NAME, user_id=DEFAULT_USER, session_id=session_id
        )
    except Exception:
        sess = None

    last_upload = None
    if sess and getattr(sess, "state", None):
        last_upload = sess.state.get("session", {}).get("last_upload")

    if not last_upload:
        mirror = active_session.get(session_id, {})
        last_upload = mirror.get("last_upload")

    if not last_upload:
        return parts

    file_urls = last_upload.get("file_urls", [])
    for url in file_urls:
        clean_url = url.split("?")[0]
        mime_type, _ = mimetypes.guess_type(clean_url)
        mime_type = mime_type or "application/octet-stream"

        parts.append(
            Part(file_data=FileData(file_uri=str(url), mime_type=str(mime_type)))
        )

    return parts


# --------------------------------------------------------------------
# REST endpoint
# --------------------------------------------------------------------

class AgentRequest(BaseModel):
    prompt: str
    session_id: str = "default-session"


class AgentResponse(BaseModel):
    response: str


@app.post("/agent/run", response_model=AgentResponse)
async def run_agent(request: AgentRequest):
    try:
        session = await session_service.get_session(app_name=APP_NAME, user_id=DEFAULT_USER, session_id=request.session_id)
        if not session:
            session = await session_service.create_session(app_name=APP_NAME, user_id=DEFAULT_USER, session_id=request.session_id)

        parts = [Part(text=request.prompt)]
        parts = await _attach_last_upload_parts(parts, request.session_id)
        user_msg = Content(role="user", parts=parts)

        full_text = ""


        async for event in runner.run_async(
            user_id=DEFAULT_USER, session_id=session.id, new_message=user_msg
        ):
            if getattr(event, "text", None):
                full_text += event.text # type: ignore
                
                continue

            if event.content and event.content.parts:
                for p in event.content.parts:
                    if getattr(p, "text", None):
                        full_text += p.text # type: ignore

        return AgentResponse(response=full_text)

    except Exception as e:
        logger.exception("Server Error in /agent/run")
        raise HTTPException(status_code=500, detail=str(e))


# --------------------------------------------------------------------
# Upload Endpoint
# --------------------------------------------------------------------

@app.post("/upload")
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
            f["file_url"] = make_signed_url(file_id, f["file_name"])

        upload_details = {
            "file_id": file_id,
            "files": uploaded_files,
            "file_urls": [f["file_url"] for f in uploaded_files],
            "timestamp": datetime.now().isoformat(),
            "file_count": len(uploaded_files),
        }

        active_session.setdefault(session_id, {"context": {}})
        active_session[session_id]["last_upload"] = upload_details

        session = await session_service.get_session(app_name=APP_NAME, user_id=DEFAULT_USER, session_id=session_id)
        if not session:
            session = await session_service.create_session(
                app_name=APP_NAME, user_id=DEFAULT_USER, session_id=session_id,
                state={"session": {"last_upload": upload_details}}
            )
        else:
            evt = Event(
                invocation_id=str(uuid.uuid4()),
                author=str(root_agent.name),
                actions=EventActions(state_delta={"session": {"last_upload": upload_details}}),
                partial=False,
            )
            await session_service.append_event(session, evt)

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


# --------------------------------------------------------------------
# WebSocket Handler
# --------------------------------------------------------------------

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    logger.info(f"WebSocket connected: {session_id}")



    await websocket.send_json({
        "type": "connection_established",
        "message": "🎉 Welcome to Agentic AI Gateway!",
        "session_id": session_id,
    })

    active_session.setdefault(session_id, {"context": {}, "connected": True})

    # config=GetSessionConfig(num_recent_events=1)

    session = await session_service.get_session(app_name=APP_NAME,user_id= DEFAULT_USER, session_id=session_id)


    if not session:
        session = await session_service.create_session(app_name=APP_NAME, user_id=DEFAULT_USER, session_id=session_id)

    try:
        while True:
            raw = await websocket.receive_text()

            # Parse user message
            try:
                obj = json.loads(raw)
                prompt = (obj.get("prompt") or obj.get("content") or "").strip()
            except Exception:
                prompt = raw.strip()

            if not prompt:
                continue
            
            #----------NEW WORKFLOW(Per Prompt)--------
            workflow_id=str(uuid.uuid4())
            async with AsyncSessionLocal() as db:
                orchestration_session=OrchestrationSession(
                    session_id=workflow_id,
                    user_id=DEFAULT_USER,
                    status="active",
                )
                db.add(orchestration_session)
                await db.commit()
                await db.refresh(orchestration_session)

            parts = [Part(text=prompt)]
            parts = await _attach_last_upload_parts(parts, session_id)
            user_msg = Content(role="user", parts=parts)


            await websocket.send_json({"type": "status_type", "stage": "turn_started"})


            current_invocation=InvocationContext()

            run_session_id=(
                current_invocation.agent_session_id
                if current_invocation.agent_session_id
                else session.id
            )
            async for event in runner.run_async(
                user_id=DEFAULT_USER,
                session_id=run_session_id,
                new_message=user_msg,
            ):

                # logger.info(f"EVENT TIMELINE: %s",debug_event(event))

                input_token= 0
                output_token=0
                total_token=0 
                if getattr(event,'usage_metadata',None):
                    input_token=event.usage_metadata.prompt_token_count # type: ignore
                    output_token=event.usage_metadata.candidates_token_count # type: ignore
                    total_token=event.usage_metadata.total_token_count # type: ignore
                    await websocket.send_json(
                        {
                            "type": "token_usase",
                            "input_token":input_token,
                            "output_token":output_token,
                            "total_token":total_token
                        }
                    )
                else:
                    input_token=0
                    output_token=0
                    output_token=0
                # 0) Explicit error
                if getattr(event, "error_message", None):
                    if current_invocation.id:
                        async with AsyncSessionLocal() as db:
                            result=await db.execute(
                                select(AgentInvocation).where(
                                    AgentInvocation.id == current_invocation.id
                                )
                            )
                            invocation=result.scalar_one_or_none()
                            if invocation:
                                invocation.status="failed"
                                invocation.completed_at=datetime.now(timezone.utc)
                                invocation.output_payload=current_invocation.buffer[:5000]
                                await db.commit()
                            
                        
                    await websocket.send_json({
                        "type": "bot_message",
                        "content": f"❌ Server error: {event.error_message}",
                    })
                
                # 0b) Remote A2A failure
                a2a_resp = (getattr(event, "custom_metadata", {}) or {}).get("a2a:response")
                if isinstance(a2a_resp, dict):
                    status = (a2a_resp.get("status") or {})
                    if (status.get("state") or "").lower() == "failed":
                        if current_invocation.id:
                            async with AsyncSessionLocal() as db:
                                result=await db.execute(
                                    select(AgentInvocation).where(
                                        AgentInvocation.id==current_invocation.id
                                    )
                                )
                                invocation=result.scalar_one_or_none()
                                if invocation:
                                    invocation.status="failed"
                                    invocation.completed_at=datetime.now(timezone.utc)
                                    await db.commit()
                            
                        await websocket.send_json({
                            "type": "bot_message",
                            "content": "❌ The remote agent reported a failure.",
                        })
                        await websocket.send_json({
                            "type": "error_details",
                            "data": status,
                        })

                        
                a2a_resp = (getattr(event, "custom_metadata", {}) or {}).get("a2a:response")
                if isinstance(a2a_resp, dict):
                    status = (a2a_resp.get("status") or {})
                    state = (status.get("state") or "").lower()
                    if state and state != "failed":
                        message = status.get("message") or status.get("detail") or ""
                        payload = {
                            "type": "status_type",
                            "stage": "task_update",
                            "state": state,  # queued/submitted/working/completed
                            "message": message or f"🔄 Task {state.replace('_', ' ')}",
                        }
                        # Optional: progress/steps if your server fills them
                        if status.get("progress") is not None:
                            payload["progress"] = status["progress"]
                        if status.get("step") is not None:
                            payload["step"] = status["step"]
                        if status.get("total_steps") is not None:
                            payload["total_steps"] = status["total_steps"]
                        await websocket.send_json(payload)
                # ---------- 1) Friendly streaming text ----------
                if getattr(event, "text", None):
                    if current_invocation.id:
                        current_invocation.buffer += event.text # type: ignore
                    await websocket.send_json({"type": "bot_message", "content": event.text}) # type: ignore

                # ---------- 2) UI files via metadata (your current code) ----------
                ui_files = (getattr(event, "custom_metadata", {}) or {}).get("ui_files")


                if ui_files:
                    local_urls = []
                    # remote_urls = []
                    for item in ui_files:
                        url = (item or {}).get("url")
                        if not url:
                            continue

                        # Friendly “tool completed” message
                        local_file_id,local_filename,local_file_path=await fetch_remote_file(str(url))
                        # remote_urls.append(str(url))
                        signed_url=make_signed_url(local_file_id,local_filename)
                        local_urls.append(signed_url)
                        #---Artifact in DB----
                        if current_invocation.id:
                            async with AsyncSessionLocal() as db:
                                artifact=Artifact(
                                    invocation_id=current_invocation.id,
                                    file_id=local_file_id,
                                    filename=local_filename,
                                    url=signed_url,
                                    path=str(local_file_path),
                                    created_at=datetime.now(timezone.utc),
                                    )
                                db.add(artifact)
                                await db.commit() 


                    if local_urls:

                        await websocket.send_json({
                            "type": "status_type",
                            "stage": "tool_completed",
                            "message": f"{getattr(event, 'author', 'Agent')} completed the task."
                        })
                        await websocket.send_json({
                            "type": "file_processed",
                            "download_link": local_urls,
                            "files": local_urls,
                            "message": "Generated files ready for download"
                        })
                #token usage:

                token_usage=(getattr(event, "custom_metadata", {}) or {}).get("token_usage")

                logger.info(f"format of token uage : {token_usage}")
                if token_usage:
                    input_token=token_usage.get("input")
                    output_token=token_usage.get("output")
                    total_token=token_usage.get("total")
                    await websocket.send_json(
                        {
                            "type": "token_usage",
                            "input_token":input_token,
                            "output_token":output_token,
                            "total_token":total_token
                        }
                    )
                # ---------- 3) Structured content.parts ----------
                content = getattr(event, "content", None)
                evt_parts = getattr(content, "parts", None) if content else None

                if evt_parts:
                    for p in evt_parts:
                        # A) Tool call -> Show spinner/status instead of raw JSON
                        fc = getattr(p, "function_call", None)

                        if fc:

                            if current_invocation.id:
                                async with AsyncSessionLocal() as db:
                                    result=await db.execute(
                                        select(AgentInvocation).where(
                                            AgentInvocation.id==current_invocation.id
                                        )
                                    )
                                    invocation=result.scalar_one_or_none()
                                    if invocation:
                                        invocation.status="completed"
                                        invocation.completed_at=datetime.now(timezone.utc)
                                        invocation.output_payload=current_invocation.buffer[:5000]
                                        await db.commit()
                            
                                current_invocation=InvocationContext()
                            # Friendly status for chatty success
                            await websocket.send_json({
                                "type": "status_type",
                                "stage": "tool_started",
                                "name": fc.name or "tool",
                                "message": f"🔧 Running {fc.args.get("agent_name") if fc.args else 'tool'}…"
                            })
                            if SHOW_RAW_TOOL_EVENTS:
                                await websocket.send_json({
                                    "type": "tool_call_type",
                                    "name": fc.name,
                                    "args": fc.args or {},
                                })
                            real_agent_name=fc.name
                            if fc.name == "transfer_to_agent" and fc.args:
                                real_agent_name=fc.args.get("agent_name") or fc.args.get("name") or "unknown_agent"

                            agent_name=real_agent_name
                            async with AsyncSessionLocal() as db:
                                result=await db.execute(
                                    select(AgentInvocation)
                                    .where(AgentInvocation.orchestration_session_id == orchestration_session.id)
                                    .order_by(AgentInvocation.step_order.desc())
                                )
                                last_invocation=result.scalars().first()
                                next_step=1 if not last_invocation else last_invocation.step_order+1

                                invocation=AgentInvocation(
                                    orchestration_session_id=orchestration_session.id,
                                    agent_name=agent_name,
                                    agent_session_id=f"{session_id}::{agent_name}",
                                    step_order=next_step,
                                    status="working",
                                    started_at=datetime.now(timezone.utc),
                                    input_payload=json.dumps({"tool_args":fc.args,
                                                              "user_prompt":prompt})[:5000] if fc.args else None,
                                )
                                db.add(invocation)
                                await db.commit()
                                await db.refresh(invocation)

                                agent_session_id =f"{session_id}::{agent_name}"

                                agent_session= await session_service.get_session(
                                    app_name=APP_NAME,
                                    user_id=DEFAULT_USER,
                                    session_id=agent_session_id
                                )
                                if not agent_session:
                                    agent_session=await session_service.create_session(
                                        app_name=APP_NAME,
                                        user_id=DEFAULT_USER,
                                        session_id=agent_session_id
                                    )
                                current_invocation.id=invocation.id
                                current_invocation.agent_name=agent_name
                                current_invocation.agent_session_id=agent_session_id
                                current_invocation.buffer=""

                            continue

                        # B) Tool response -> mark completed; artifacts will come as file_data parts
                        fr = getattr(p, "function_response", None)
                        if fr:
                            await websocket.send_json({
                                "type": "status_type",
                                "stage": "tool_completed",
                                "name": fr.name or "tool",
                                "message": f"✅ {fr.name or 'Tool'} finished."
                            })
                            if SHOW_RAW_TOOL_EVENTS:
                                await websocket.send_json({
                                    "type": "tool_result_type",
                                    "name": fr.name,
                                    "response": fr.response or {},
                                })
                            
        
                            continue

                        # C) File data (emit artifacts immediately)
                        fd = getattr(p, "file_data", None)
                        if fd and getattr(fd, "file_uri", None):

                            local_file_id,local_filename,local_file_path=await fetch_remote_file(str(fd.file_uri))

                            signed_url=make_signed_url(local_file_id,local_filename)
                            #---Artifact in DB----
                            if current_invocation.id:
                                async with AsyncSessionLocal() as db:
                                    artifact=Artifact(
                                        invocation_id=current_invocation.id,
                                        file_id=local_file_id,
                                        filename=local_filename,
                                        url=signed_url,
                                        path=str(local_file_path),
                                        created_at=datetime.now(timezone.utc),
                                        )
                                    db.add(artifact)
                                    await db.commit() 

                            await websocket.send_json({
                                "type": "file_processed",
                                "download_link": [signed_url],
                                "files": [signed_url],
                                "message": "File generated successfully"
                            })
                            # (No continue needed; but safe to continue)
                            continue

                        # D) Text (non-tool)
                        if getattr(p, "text", None):
                            if current_invocation.id:
                                current_invocation.buffer += p.text
                            # Treat as progress/working
                            await websocket.send_json({
                                "type": "bot_message",
                                "content": p.text,
                            })
            if current_invocation.id:
                async with AsyncSessionLocal() as db:
                    result=await db.execute(
                        select(AgentInvocation).where(
                            AgentInvocation.id==current_invocation.id
                            )
                    )
                    invocation=result.scalar_one_or_none()
                    if invocation:
                            invocation.status="completed"
                            invocation.completed_at=datetime.now(timezone.utc)
                            invocation.output_payload=current_invocation.buffer[:5000]
                            await db.commit()
                            
                    current_invocation=InvocationContext()                
            # After loop
            await websocket.send_json({
                "type": "status_type",
                "stage": "done",
                "ts": datetime.now().isoformat()
            })

            async with AsyncSessionLocal() as db:
                result=await db.execute(
                    select(OrchestrationSession).where(
                        OrchestrationSession.id == orchestration_session.id
                    )
                )
                ws=result.scalar_one_or_none()
                if ws:
                    ws.status ="completed"
                    ws.completed_at=datetime.now(timezone.utc)
                    await db.commit()

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {session_id}")
        active_session.pop(session_id, None)

    except Exception as e:
        logger.error(f"WebSocket Error: {e}")
        await websocket.send_json({
            "type": "bot_message",
            "content": f"⚠️ WS Error: {str(e)}"
        })
        active_session.pop(session_id, None)
        await websocket.close()




if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)