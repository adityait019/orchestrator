from fastapi import APIRouter, HTTPException
import logging 
from session.session_manager import SessionManager
from core.config import APP_NAME, DEFAULT_USER
import os
from pydantic import BaseModel
from core.runner_factory import create_runner
from google.genai.types import Content, Part
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/run", tags=["Run Agent"])

# --------------------------------------------------------------------
# REST endpoint
# --------------------------------------------------------------------

class AgentRequest(BaseModel):
    prompt: str
    session_id: str = "default-session"


class AgentResponse(BaseModel):
    response: str

session_manager = SessionManager(db_url=os.getenv("DATABASE_URL","not-present"),app_name=APP_NAME)
runner = create_runner(session_manager.session_service)

@router.post("/", response_model=AgentResponse)
async def run_agent(request: AgentRequest):
    try:
        session = await session_manager.get_session(user_id=DEFAULT_USER, session_id=request.session_id)
        if not session:
            session = await session_manager.create_session(user_id=DEFAULT_USER, session_id=request.session_id)

        parts = [Part(text=request.prompt)]
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
