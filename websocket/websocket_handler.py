import json
import logging
from google.genai.types import Content, Part
from fastapi import WebSocketDisconnect
import asyncio
from websocket.ws_emitter import WSEmitter
from websocket.event_processor import EventProcessor
from services.invocation_context import InvocationContext
from core.config import DEFAULT_USER
import uuid
from services.chat_history_service import chat_history_service
logger = logging.getLogger(__name__)

AUTH_TIMEOUT_SECONDS = 10    


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

    async def handle(self, websocket, session_id: str):

        await websocket.accept()
        emitter = WSEmitter(websocket)
        await emitter.connection_established(session_id)

        # ─────────────────────────────────────────────
        # 🔐 AUTH HANDSHAKE
        # ─────────────────────────────────────────────
        try:
            frame = await asyncio.wait_for(
                websocket.receive_json(),
                timeout=AUTH_TIMEOUT_SECONDS,
            )
            logger.info(f"THIS is Frame {frame}")

        except asyncio.TimeoutError:
            await emitter._safe_send({"type": "auth_failed", "detail": "auth timeout"})
            await websocket.close(code=4401)
            return

        except Exception:
            await emitter._safe_send({"type": "auth_failed", "detail": "invalid JSON"})
            await websocket.close(code=4401)
            return

        if frame.get("type") != "auth":
            await emitter._safe_send({
                "type": "auth_failed",
                "detail": "first frame must be type=auth"
            })
            await websocket.close(code=4401)
            return

        token = frame.get("access_token")
        user_id = frame.get("user_id")
        tenant_id = frame.get("tenant_id")
        roles = frame.get("roles", [])

        if not token or not isinstance(token, str):
            await emitter._safe_send({
                "type": "auth_failed",
                "detail": "missing or invalid access_token"
            })
            await websocket.close(code=4401)
            return

        await emitter._safe_send({"type": "auth_ok", "scopes": roles})

        logger.info(
            "WS authenticated: user=%s tenant=%s roles=%s session=%s",
            user_id, tenant_id, roles, session_id,
        )

        # user_id = str(uuid.uuid4())  # TEMP: generate random user_id for now, until we have real auth in place
        # tenant_id = str(uuid.uuid4())  # TEMP: generate random tenant_id for now, until we have real auth in place
        # roles = ["user"]  # TEMP: default role

        # ✅ Session setup
        await self.session_manager.ensure_session(
            user_id=user_id,
            session_id=session_id,
        )
        self.session_manager.mark_connected(user_id, session_id)

        processor = EventProcessor(
            emitter,
            self.agent_service,
            self.artifact_service,
            self.file_service,
        )

        try:
            while True:
                try:
                    raw = await websocket.receive_text()
                except WebSocketDisconnect:
                    logger.info("🔌 Client disconnected while waiting for input")
                    break

                try:
                    obj = json.loads(raw)
                    prompt = (obj.get("prompt") or obj.get("content") or "").strip()
                except Exception:
                    prompt = raw.strip()

                if not prompt:
                    continue

                # ✅ Save user message immediately (before processing)
                try:
                    await chat_history_service.append_message(
                        session_manager=self.session_manager,
                        user_id=user_id,
                        tenant_id=tenant_id,
                        session_id=session_id,
                        message={
                            "type": "user",
                            "content": prompt,
                        },
                    )
                except Exception:
                    logger.exception("Failed saving user message early")


                try:
                    # ✅ Start workflow
                    workflow = await self.workflow.start_workflow(session_id=session_id, user_id=user_id,tenant_id=tenant_id,)

                    invocation_ctx = InvocationContext()

                    root_invocation = await self.agent_service.start_root_invocation(
                        workflow_id=workflow.session_id,
                        user_id=user_id,
                        session_id=session_id,
                        prompt=prompt,
                    )

                    invocation_ctx.invocation_id = root_invocation.id
                    invocation_ctx.agent_name = "Cortex"
                    invocation_ctx.agent_session_id = f"{session_id}::Cortex"

                    context = {
                        "workflow_id": workflow.session_id,
                        "user_id": user_id,
                        "session_id": session_id,
                        "prompt": prompt,
                        "invocation_ctx": invocation_ctx,
                        "tenant_id": tenant_id
                    }

                    if emitter.closed:
                        break

                    await emitter.status("turn_started")

                    # ✅ Build message
                    parts = [Part(text=prompt)]
                    parts = await self.session_manager.attach_last_upload(
                        parts,
                        user_id=user_id,
                        session_id=session_id,
                    )

                    # ✅ Attach token
                    parts = await self.session_manager.attach_tool_tokens(
                        parts,
                        payload={"access_token": token},
                        session_id=session_id
                    )

                    user_msg = Content(role="user", parts=parts)



                    try:
                        # ✅ STREAM processing (SAFE)
                        async for event in self.runner.run_async(
                            user_id=user_id,
                            session_id=session_id,
                            new_message=user_msg,
                        ):
                            if emitter.closed:
                                logger.info("🔌 Stopping stream: WS closed")
                                break

                            try:
                                await processor.process(event, context)
                            except WebSocketDisconnect:
                                logger.info("🔌 Disconnected during processing")
                                break

                        # ✅ finalize only if still connected
                        if not emitter.closed:
                            ic = context["invocation_ctx"]

                            if ic.invocation_id:
                                try:
                                    output = ic.output_payload if ic.output_payload is not None else (ic.buffer or None)
                                    await self.agent_service.complete_invocation(
                                        ic.invocation_id,
                                        output,
                                        ic.input_tokens,
                                        ic.output_tokens,
                                        ic.total_tokens,
                                    )
                                except Exception:
                                    logger.exception("Failed finalizing invocation")

                            # await self.workflow.complete_workflow(workflow.session_id)
                    finally:
                        try:
                            await self.workflow.complete_workflow(workflow.session_id)
                        except Exception:
                            logger.exception("🔥 Error completing workflow")

                        await emitter.done()



                    # ✅ Save USER message (append-only)
                    try:
                        ic= context["invocation_ctx"]

                        # ✅ Extract AI output safely
                        ai_output = ""

                        if ic:
                            payload = ic.output_payload

                            if isinstance(payload, dict):
                                ai_output = payload.get("text") or str(payload)
                            elif isinstance(payload, str):
                                ai_output = payload
                            elif payload is None:
                                ai_output = ic.buffer or ""
                            else:
                                ai_output = str(payload)
                        if  ai_output :
                        # ✅ Save AI message (append-only)
                            await chat_history_service.append_message(
                                session_manager=self.session_manager,
                                user_id=user_id,
                                tenant_id=tenant_id,
                                session_id=session_id,
                                message={
                                    "type": "ai",
                                    "content": ai_output,
                                    "input_tokens": ic.input_tokens if ic else None,
                                    "output_tokens": ic.output_tokens if ic else None,
                                    "artifact_ids": None,
                                    "agent_name": ic.agent_name if ic else None,
                                },
                            )

                    except Exception:
                        logger.exception("Failed saving AI message (session=%s user=%s)",session_id,user_id)



                except WebSocketDisconnect:
                    logger.info("🔌 Client disconnected mid-turn")
                    break

                except Exception as e:
                    logger.exception("🔥 WS processing error")

                    if not emitter.closed:
                        # await emitter.bot_message(
                        #     f"❌ ERROR: {type(e).__name__}: {str(e)}"
                        # )
                    
                        await emitter.bot_message({
                            "type": "error",
                            "error": str(e),
                            "error_type": type(e).__name__
                        })


        except WebSocketDisconnect:
            logger.info("🔌 Client disconnected (outer loop)")

        finally:
            self.session_manager.mark_disconnected(user_id, session_id)
            logger.info("✅ Cleanup complete")

    
