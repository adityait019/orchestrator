from google.adk.sessions.database_session_service import DatabaseSessionService
from typing import Optional, Dict

class SessionManager:

    def __init__(self, db_url):
        self.session_service = DatabaseSessionService(db_url=db_url)
        self.active_sessions: Dict[str, Dict] = {}  # session_id -> session_info

    async def get_session(self, app_name, user_id, session_id):
        session = await self.session_service.get_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
        )
        return session
    
    async def create_session(self, app_name, user_id, session_id):
        session = await self.session_service.create_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
        )
        return session