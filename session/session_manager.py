from google.adk.sessions.database_session_service import DatabaseSessionService
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions
from google.genai.types import Part, FileData
from google.adk.sessions.base_session_service import GetSessionConfig
from typing import Dict, Optional
import uuid
import mimetypes


class SessionManager:
    """
    Manages:
    - ADK persistent sessions (DatabaseSessionService)
    - In-memory active session mirror for WebSocket workflows
    """

    def __init__(self, db_url: str, app_name: str = "my_agent_app"):
        self.session_service = DatabaseSessionService(db_url=db_url)
        self.app_name = app_name

        # In-memory mirror:
        # session_id -> {
        #   "connected": bool,
        #   "last_upload": dict,
        # }
        self.active_sessions: Dict[str, Dict] = {}

    # ------------------------------------------------------------------
    # Core session helpers
    # ------------------------------------------------------------------

    async def get_session(self, user_id: str, session_id: str):
        config=GetSessionConfig(num_recent_events=0)
        return await self.session_service.get_session(
            app_name=self.app_name,
            user_id=user_id,
            session_id=session_id,
            config=config,
        )

    async def create_session(
        self,
        user_id: str,
        session_id: str,
        state: Optional[dict] = None,
    ):
        session = await self.session_service.create_session(
            app_name=self.app_name,
            user_id=user_id,
            session_id=session_id,
            state=state or {},
        )
        return session

    async def ensure_session(self, user_id: str, session_id: str):
        """
        Ensure session exists both in DB and memory.
        """
        session = await self.get_session(user_id, session_id)

        if not session:
            session = await self.create_session(
                user_id=user_id,
                session_id=session_id,
            )

        # Ensure in-memory mirror exists
        self.active_sessions.setdefault(
            session_id,
            {
                "connected": True,
                "last_upload": None,
            }
        )

        return session

    # ------------------------------------------------------------------
    # Upload tracking (CRITICAL)
    # ------------------------------------------------------------------

    async def set_last_upload(
        self,
        user_id: str,
        session_id: str,
        upload_details: dict,
    ):
        """
        Persist last upload to:
        - In-memory mirror
        - ADK session state
        """

        # ---- memory mirror ----
        self.active_sessions.setdefault(session_id, {})
        self.active_sessions[session_id]["last_upload"] = upload_details

        # ---- persistent state ----
        session = await self.ensure_session(user_id, session_id)

        evt = Event(
            invocation_id=str(uuid.uuid4()),
            author="system",
            actions=EventActions(
                state_delta={
                    "session": {
                        "last_upload": upload_details
                    }
                }
            ),
            partial=False,
        )

        await self.session_service.append_event(session, evt)

    # ------------------------------------------------------------------
    # Attachment logic (USED BY WEBSOCKET + HTTP)
    # ------------------------------------------------------------------

    async def get_last_upload(self, user_id: str, session_id: str) -> Optional[dict]:
        """
        Priority:
        1. In-memory session
        2. DB session state
        """

        # 1️⃣ Memory first (fast path – WebSocket)
        mirror = self.active_sessions.get(session_id)
        if mirror and mirror.get("last_upload"):
            return mirror["last_upload"]

        # 2️⃣ DB fallback
        session = await self.get_session(user_id, session_id)
        if session and session.state:
            return session.state.get("session", {}).get("last_upload")

        return None

    async def attach_last_upload(self, parts: list[Part], user_id: str, session_id: str):
        """
        Attach uploaded files to a user prompt.
        """

        last_upload = await self.consume_last_upload(user_id, session_id)
        if not last_upload:
            return parts

        for url in last_upload.get("file_urls", []):
            clean_url = url.split("?")[0]
            mime_type, _ = mimetypes.guess_type(clean_url)
            mime_type = mime_type or "application/octet-stream"

            parts.append(
                Part(
                    file_data=FileData(
                        file_uri=url,
                        mime_type=mime_type
                    )
                )
            )

        return parts


    async def consume_last_upload(self, user_id: str, session_id: str):
        mirror = self.active_sessions.get(session_id)
        if mirror and mirror.get("last_upload"):
            return mirror.pop("last_upload")

        session = await self.get_session(user_id, session_id)
        if session and session.state:
            return session.state.get("session", {}).pop("last_upload", None)

        return None

    # ------------------------------------------------------------------
    # WebSocket lifecycle helpers
    # ------------------------------------------------------------------

    def mark_connected(self, session_id: str):
        self.active_sessions.setdefault(session_id, {})
        self.active_sessions[session_id]["connected"] = True

    def mark_disconnected(self, session_id: str):
        if session_id in self.active_sessions:
            self.active_sessions[session_id]["connected"] = False