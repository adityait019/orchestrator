#services/agent_execution_service.py
import json
from datetime import datetime, timezone
from sqlalchemy import select
from database.models import AgentInvocation


def _normalize_payload(value):
    """
    Ensure payload is always JSON-serializable dict
    (since DB column is JSONB now).
    """
    if value is None:
        return {}

    if isinstance(value, dict):
        return value

    if isinstance(value, str):
        return {"text": value}

    # fallback for objects, exceptions, etc.
    return {"value": str(value)}


class AgentExecutionService:

    def __init__(self, db_session_factory, session_service):
        self.db = db_session_factory
        self.session_service = session_service

    # -------------------------------------------------
    # Root Invocation
    # -------------------------------------------------

    async def start_root_invocation(
        self,
        workflow_id,
        user_id,
        session_id,
        prompt,
    ):
        invocation, _ = await self.start_invocation(
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

                # ✅ JSON (NOT string anymore)
                input_payload=_normalize_payload({
                    "user_id": user_id,
                    "session_id": session_id,
                    "tool_args": args,
                    "user_prompt": prompt,
                }),
            )

            db.add(invocation)
            await db.commit()
            await db.refresh(invocation)

        return invocation, agent_session_id

    # -------------------------------------------------
    # Completion
    # -------------------------------------------------

    async def complete_invocation(
        self,
        invocation_id,
        output,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None
    ):
        async with self.db() as db:
            result = await db.execute(
                select(AgentInvocation).where(AgentInvocation.id == invocation_id)
            )
            inv = result.scalar_one_or_none()

            if inv:
                inv.status = "completed"
                inv.completed_at = datetime.now(timezone.utc)

                # ✅ JSON payload
                payload = _normalize_payload(output)

                # Avoid persisting empty text/dict as JSONB — store NULL instead
                if isinstance(payload, dict):
                    # empty dict -> no useful output
                    if not payload:
                        inv.output_payload = None
                    # single empty text field -> treat as empty
                    elif list(payload.keys()) == ["text"]:
                        text = payload.get("text")
                        if isinstance(text, str) and not text.strip():
                            inv.output_payload = None
                        else:
                            inv.output_payload = payload
                    else:
                        inv.output_payload = payload
                else:
                    inv.output_payload = payload

                if input_tokens is not None:
                    inv.input_tokens = input_tokens

                if output_tokens is not None:
                    inv.output_tokens = output_tokens

                if total_tokens is not None:
                    inv.total_tokens = total_tokens

                await db.commit()

    # -------------------------------------------------
    # Failure
    # -------------------------------------------------

    async def fail_invocation(
        self,
        invocation_id,
        error_msg,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None
    ):
        async with self.db() as db:
            result = await db.execute(
                select(AgentInvocation).where(AgentInvocation.id == invocation_id)
            )
            inv = result.scalar_one_or_none()

            if inv:
                inv.status = "failed"
                inv.completed_at = datetime.now(timezone.utc)

                # ✅ Structured error
                inv.output_payload = _normalize_payload({
                    "status": "failed",
                    "error": error_msg
                })

                if input_tokens is not None:
                    inv.input_tokens = input_tokens

                if output_tokens is not None:
                    inv.output_tokens = output_tokens

                if total_tokens is not None:
                    inv.total_tokens = total_tokens

                await db.commit()

    # -------------------------------------------------
    # Token Tracking
    # -------------------------------------------------

    async def add_token_usage(
        self,
        invocation_id: int,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
    ):
        async with self.db() as db:
            result = await db.execute(
                select(AgentInvocation).where(AgentInvocation.id == invocation_id)
            )
            inv = result.scalar_one_or_none()

            if inv:
                input_tokens = input_tokens or 0
                output_tokens = output_tokens or 0
                total_tokens = total_tokens or 0

                inv.input_tokens = (inv.input_tokens or 0) + input_tokens
                inv.output_tokens = (inv.output_tokens or 0) + output_tokens
                inv.total_tokens = (inv.total_tokens or 0) + total_tokens

                await db.commit()