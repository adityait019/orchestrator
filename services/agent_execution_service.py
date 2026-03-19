#services/agent_execution_service.py

import json
from datetime import datetime,timezone
from sqlalchemy import select
from database.models import AgentInvocation


class AgentExecutionService:
    """Responsible for
    - AgentInvocation
    - agent_session_id
    - agent execution tracking 
    """

    def __init__(self,db_session_factory,session_service):
        self.db=db_session_factory
        self.session_service=session_service
    

    async def start_invocation(
      self,
      workflow_id,
      session_id,
      agent_name,
      prompt,
      args      
    ):
        agent_session_id=f"{session_id}::{agent_name}"

        async with self.db() as db:
            result=await db.execute(
                select(AgentInvocation)
                .where(
                    AgentInvocation.orchestration_session_id == workflow_id
                )
                .order_by(AgentInvocation.step_order.desc())
            )
            last= result.scalars().first()

            next_step=1 if not last else last.step_order+1

            invocation=AgentInvocation(
                orchestration_session_id=workflow_id,
                agent_name=agent_name,
                agent_session_id=agent_session_id,
                step_order=next_step,
                status="working",
                started_at=datetime.now(timezone.utc),
                input_payload=json.dumps({
                    "tool_args":args,
                    "user_prompt": prompt
                })[:5000]
            )
            db.add(invocation)
            await db.commit()
            await db.refresh(invocation)
        return invocation,agent_session_id