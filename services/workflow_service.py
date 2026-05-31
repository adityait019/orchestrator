#services/workflow_service.py
import uuid
from datetime import datetime,timezone
from database.models import OrchestrationSession
from sqlalchemy import select


class WorkflowService:
    """Responsible for
     - create orchestration_session
     - complete orchestration_session
     - workflow lifecycle
    """

    def __init__(self, db_session_factory):
        self.db=db_session_factory

    


    async def start_workflow(
        self,
        session_id: str,
        user_id: str,
        tenant_id: str | None = None,
        title: str | None = None,
    ):
        now = datetime.now(timezone.utc)

        async with self.db() as db:

            # 🔹 Check if session already exists
            result = await db.execute(
                select(OrchestrationSession).where(
                    OrchestrationSession.session_id == session_id
                )
            )

            ws = result.scalar_one_or_none()

            # ✅ If exists → just return it
            if ws:
                return ws

            # ✅ Else → create new
            ws = OrchestrationSession(
                session_id=session_id,
                user_id=user_id,
                status="active",
                tenant_id=tenant_id,
                title=title or f"New Conversation {session_id[:8]}",
                message_count=0,
                last_message_at=now,
            )

            db.add(ws)
            await db.commit()
            await db.refresh(ws)

            return ws



    async def complete_workflow(self, workflow_id):
        async with self.db() as db:

            result = await db.execute(
                select(OrchestrationSession)
                .where(OrchestrationSession.session_id == str(workflow_id))
            )

            ws = result.scalar_one_or_none()

            if ws:
                ws.status = "completed"
                ws.completed_at = datetime.now(timezone.utc)

                await db.commit()

