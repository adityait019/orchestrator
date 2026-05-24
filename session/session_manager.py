from google.adk.sessions.database_session_service import DatabaseSessionService
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions
from google.genai.types import Part, FileData
from google.adk.sessions.base_session_service import GetSessionConfig
from typing import Dict, Optional
import uuid
import mimetypes
from a2a.types import Message



# In SessionManager

import json
from google.genai.types import Part

META_TOOL_TOKEN_PREFIX = "[META:TOOL_TOKENS]"




class SessionManager:
    """
    Manages:
    - ADK persistent sessions (DatabaseSessionService)
    - In-memory active session mirror (PER USER + SESSION)
    """

    def __init__(self, db_url: str, app_name: str = "my_agent_app"):
        self.session_service = DatabaseSessionService(db_url=db_url)
        self.app_name = app_name

        # Keyed by: f"{user_id}::{session_id}"
        self.active_sessions: Dict[str, Dict] = {}

    # -----------------------------
    # Internal helpers
    # -----------------------------

    def _key(self, user_id: str, session_id: str) -> str:
        return f"{user_id}::{session_id}"

    # -----------------------------
    # Core session helpers
    # -----------------------------

    async def get_session(self, user_id: str, session_id: str):
        return await self.session_service.get_session(
            app_name=self.app_name,
            user_id=user_id,
            session_id=session_id,
            config=GetSessionConfig(num_recent_events=1),
        )

    async def create_session(
        self,
        user_id: str,
        session_id: str,
        state: Optional[dict] = None,
    ):
        return await self.session_service.create_session(
            app_name=self.app_name,
            user_id=user_id,
            session_id=session_id,
            state=state or {},
        )

    async def ensure_session(self, user_id: str, session_id: str):
        session = await self.get_session(user_id, session_id)
        if not session:
            session = await self.create_session(user_id, session_id)

        self.active_sessions.setdefault(
            self._key(user_id, session_id),
            {"connected": True, "last_upload": None},
        )
        return session

    # -----------------------------
    # Upload tracking
    # -----------------------------

    async def set_last_upload(
        self,
        user_id: str,
        session_id: str,
        upload_details: dict,
    ):
        key = self._key(user_id, session_id)

        self.active_sessions.setdefault(key, {})
        self.active_sessions[key]["last_upload"] = upload_details

        session = await self.ensure_session(user_id, session_id)

        evt = Event(
            invocation_id=str(uuid.uuid4()),
            author="system",
            actions=EventActions(
                state_delta={"session": {"last_upload": upload_details}}
            ),
            partial=False,
        )

        await self.session_service.append_event(session, evt)

    # -----------------------------
    # Attachment logic
    # -----------------------------

    async def consume_last_upload(self, user_id: str, session_id: str):
        key = self._key(user_id, session_id)

        mirror = self.active_sessions.get(key)
        if mirror and mirror.get("last_upload"):
            return mirror.pop("last_upload")

        session = await self.get_session(user_id, session_id)
        if session and session.state:
            return session.state.get("session", {}).get("last_upload")

        return None

    async def attach_last_upload(self, parts: list[Part], user_id: str, session_id: str):
        last_upload = await self.consume_last_upload(user_id, session_id)
        if not last_upload:
            return parts

        for url in last_upload.get("file_urls", []):
            clean_url = url.split("?")[0]
            mime, _ = mimetypes.guess_type(clean_url)
            parts.append(
                Part(
                    file_data=FileData(
                        file_uri=url,
                        mime_type=mime or "application/octet-stream",
                    )
                )
            )

        return parts



    async def attach_tool_tokens(
        self,
        parts: list[Part],
        payload: dict,  # {access_token, refresh_token}
        session_id:str,
    ):
        """
        TEMPORARY / TESTING ONLY.

        Attaches tool tokens as a META text Part so they reach the remote agent.
        The agent is responsible for:
        - extracting
        - forwarding to the tool
        - NOT emitting them back as normal text
        """

        if not payload:
            return parts

        meta_blob = {
            "type": "tool_credentials",
            "access_token": payload.get("access_token"),
            "refresh_token": payload.get("refresh_token"),
        }

        parts.append(
            Part(
                text=f"{META_TOOL_TOKEN_PREFIX} {json.dumps(meta_blob)}"
            )
        )

        return parts
    # -----------------------------
    # WebSocket lifecycle
    # -----------------------------

    def mark_connected(self, user_id: str, session_id: str):
        self.active_sessions.setdefault(
            self._key(user_id, session_id), {}
        )["connected"] = True

    def mark_disconnected(self, user_id: str, session_id: str):
        key = self._key(user_id, session_id)
        if key in self.active_sessions:
            self.active_sessions[key]["connected"] = False