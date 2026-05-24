# #services/agent_execution_service.py

import json
from datetime import datetime, timezone
from sqlalchemy import select
from database.models import AgentInvocation


class AgentExecutionService:
    """
    Responsible for:
    - AgentInvocation tracking
    - agent_session_id generation
    - agent execution lifecycle
    """

    def __init__(self, db_session_factory, session_service):
        self.db = db_session_factory
        self.session_service = session_service

    # -------------------------------------------------
    # Root Invocation (Cortex)
    # -------------------------------------------------

    async def start_root_invocation(
        self,
        workflow_id,
        user_id,
        session_id,
        prompt,
    ):
        invocation, agent_session_id = await self.start_invocation(
            workflow_id=workflow_id,
            user_id=user_id,
            session_id=session_id,
            agent_name="Cortex",
            prompt=prompt,
            args={},
        )
        return invocation

    # -------------------------------------------------
    # Generic Invocation
    # -------------------------------------------------

    async def start_invocation(
        self,
        workflow_id,
        user_id,
        session_id,
        agent_name,
        prompt,
        args,
    ):
        # ✅ user‑scoped agent session
        agent_session_id = f"{user_id}::{session_id}::{agent_name}"

        async with self.db() as db:
            result = await db.execute(
                select(AgentInvocation)
                .where(AgentInvocation.orchestration_session_id == workflow_id)
                .order_by(AgentInvocation.step_order.desc())
            )
            last = result.scalars().first()

            next_step = 1 if not last else last.step_order + 1

            invocation = AgentInvocation(
                orchestration_session_id=workflow_id,
                agent_name=agent_name,
                agent_session_id=agent_session_id,
                step_order=next_step,
                status="working",
                started_at=datetime.now(timezone.utc),
                input_payload=json.dumps(
                    {
                        "user_id": user_id,     # ✅ traceability
                        "session_id": session_id,
                        "tool_args": args,
                        "user_prompt": prompt,
                    }
                )[:5000],
            )

            db.add(invocation)
            await db.commit()
            await db.refresh(invocation)

        return invocation, agent_session_id

    # -------------------------------------------------
    # Completion / Failure
    # -------------------------------------------------

    async def complete_invocation(self, invocation_id, output,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    total_tokens:  int | None = None
):
        async with self.db() as db:
            result = await db.execute(
                select(AgentInvocation).where(AgentInvocation.id == invocation_id)
            )
            inv = result.scalar_one_or_none()

            if inv:
                inv.status = "completed"
                inv.completed_at = datetime.now(timezone.utc)
                inv.output_payload = output[:5000]
                inv.input_tokens=input_tokens
                inv.output_tokens=output_tokens
                inv.total_tokens=total_tokens

                await db.commit()

    async def fail_invocation(self, invocation_id, error_msg,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    total_tokens:  int | None = None
):
        async with self.db() as db:
            result = await db.execute(
                select(AgentInvocation).where(AgentInvocation.id == invocation_id)
            )
            inv = result.scalar_one_or_none()

            if inv:
                inv.status = "failed"
                inv.completed_at = datetime.now(timezone.utc)
                inv.output_payload = error_msg[:5000]
                inv.input_tokens=input_tokens
                inv.output_tokens=output_tokens
                inv.total_tokens=total_tokens
                await db.commit()
