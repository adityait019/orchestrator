import json
import uuid
from google.genai.types import Content, Part
from fastapi import WebSocketDisconnect
import logging
from websocket.ws_emitter import WSEmitter
from websocket.event_processor import EventProcessor
from services.invocation_context import InvocationContext

logger = logging.getLogger(__name__)

class WebSocketHandler:

    def __init__(
        self,
        runner,
        session_manager,
        workflow_service,
        agent_service,
        artifact_service,
        file_service,
    ):
        self.runner = runner
        self.session_manager = session_manager
        self.workflow = workflow_service
        self.agent_service = agent_service
        self.artifact_service = artifact_service
        self.file_service = file_service

    async def handle(self, websocket, session_id: str, user_id: str):

        await websocket.accept()
        emitter = WSEmitter(websocket)
        await emitter.connection_established(session_id)

        # Base session (uploads, connection state ONLY)
        await self.session_manager.ensure_session(
            user_id=user_id,
            session_id=session_id,
        )
        self.session_manager.mark_connected(session_id)

        processor = EventProcessor(
            emitter,
            self.agent_service,
            self.artifact_service,
            self.file_service,
        )

        try:
            while True:
                raw = await websocket.receive_text()

                try:
                    obj = json.loads(raw)
                    prompt = (obj.get("prompt") or obj.get("content") or "").strip()
                except Exception:
                    prompt = raw.strip()

                if not prompt:
                    continue

                try:
                    workflow = await self.workflow.start_workflow(user_id)

                    invocation_ctx = InvocationContext()

                    root_invocation = await self.agent_service.start_root_invocation(
                        workflow.id,
                        session_id,
                        prompt,
                    )

                    invocation_ctx.invocation_id = root_invocation.id
                    invocation_ctx.agent_name = "Cortex"
                    invocation_ctx.agent_session_id = f"{session_id}::Cortex"

                    context = {
                        "workflow_id": workflow.id,
                        "session_id": session_id,
                        "prompt": prompt,
                        "invocation_ctx": invocation_ctx,
                    }

                    await emitter.status("turn_started")

                    parts = [Part(text=prompt)]
                    parts = await self.session_manager.attach_last_upload(
                        parts,
                        user_id=user_id,
                        session_id=session_id,
                    )

                    user_msg = Content(role="user", parts=parts)

                    # ✅ NEW per-turn session (CRITICAL FIX)
                    turn_session_id = f"{session_id}::turn::{uuid.uuid4()}"
                    await self.session_manager.create_session(
                        user_id=user_id,
                        session_id=turn_session_id,
                    )

                    async for event in self.runner.run_async(
                        user_id=user_id,
                        session_id=turn_session_id,
                        new_message=user_msg,
                    ):

                        meta = getattr(event, "custom_metadata", None)
                        if isinstance(meta, dict):
                            progress = meta.get("a2a:progress")
                            if isinstance(progress, dict):
                                await emitter.task_update(**progress)
                                continue

                        await processor.process(event, context)

                    ic = context["invocation_ctx"]
                    if ic.invocation_id:
                        await self.agent_service.complete_invocation(
                            ic.invocation_id,
                            ic.buffer,
                        )

                    await self.workflow.complete_workflow(workflow.id)
                    await emitter.done()

                except Exception as e:
                    logger.exception("🔥 WS processing error")
                    await emitter.bot_message(
                        f"❌ ERROR: {type(e).__name__}: {str(e)}"
                    )

        except WebSocketDisconnect:
            self.session_manager.mark_disconnected(session_id)
            logger.info("🔌 Client disconnected")