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

    
    async def start_workflow(self, user_id):
        workflow_id= str(uuid.uuid4())

        async with self.db() as db:
            ws=OrchestrationSession(
                session_id=workflow_id,
                user_id=user_id,
                status="active"
            )
            
            db.add(ws)
            await db.commit()
            await db.refresh(ws)
        return ws
    

    async def complete_workflow(self,workflow_id):
        async with self.db() as db:

            result=await db.execute(
                select(OrchestrationSession)
                .where(OrchestrationSession.id== workflow_id)
            )

            ws=result.scalar_one_or_none()

            if ws:
                ws.status = "completed"
                ws.completed_at=datetime.now(timezone.utc)
                await db.commit()

    async def fail_workflow(self,workflow_id,error_msg):
        async with self.db() as db:

            result=await db.execute(
                select(OrchestrationSession)
                .where(OrchestrationSession.id== workflow_id)
            )

            ws=result.scalar_one_or_none()

            if ws:
                ws.status = "failed"
                ws.completed_at=datetime.now(timezone.utc)
                ws.error_message=error_msg[:5000]
                await db.commit()