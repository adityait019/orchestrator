import json
import logging
import asyncio

from google.genai.types import Content, Part
from fastapi import WebSocketDisconnect

from websocket.ws_emitter import WSEmitter
from websocket.event_processor import EventProcessor
from services.invocation_context import InvocationContext, AgentRuntime
from services.chat_history_service import chat_history_service

logger = logging.getLogger(__name__)

AUTH_TIMEOUT_SECONDS = 10


class WebSocketHandler:

    def __init__(self, runner, session_manager, workflow_service, agent_service, artifact_service, file_service, state_manager):
        self.runner = runner
        self.session_manager = session_manager
        self.workflow = workflow_service
        self.agent_service = agent_service
        self.artifact_service = artifact_service
        self.file_service = file_service
        self.state_manager = state_manager

    async def handle(self, websocket, session_id: str):

        await websocket.accept()
        emitter = WSEmitter(websocket)
        await emitter.connection_established(session_id)

        # =========================
        # AUTH
        # =========================
        try:
            frame = await asyncio.wait_for(websocket.receive_json(), timeout=AUTH_TIMEOUT_SECONDS)
        except Exception:
            await emitter._safe_send({"type": "auth_failed"})
            await websocket.close(code=4401)
            return

        if frame.get("type") != "auth":
            await websocket.close(code=4401)
            return

        user_id = frame.get("user_id")
        tenant_id = frame.get("tenant_id")
        token = frame.get("access_token")
        roles = frame.get("roles", [])
        
        await emitter._safe_send({"type": "auth_ok"})
        logger.info(
            "WS authenticated: user=%s tenant=%s roles=%s session=%s",
            user_id, tenant_id, roles, session_id,
        )
        await self.session_manager.ensure_session(user_id, session_id)
        self.session_manager.mark_connected(user_id, session_id)

        processor = EventProcessor(
            emitter,
            self.agent_service,
            self.artifact_service,
            self.file_service,
            self.session_manager,
            self.state_manager,
        )

        try:
            while True:

                try:
                    raw = await websocket.receive_text()
                except WebSocketDisconnect:
                    logger.info("Client disconnected")
                    break
                except Exception as e:
                    logger.exception("Receive failed: %s", e)
                    continue

                try:
                    obj = json.loads(raw)
                    prompt = (obj.get("prompt") or "").strip()
                except Exception:
                    prompt = raw.strip()

                if not prompt:
                    continue

                # =========================
                # START WORKFLOW
                # =========================
                workflow = await self.workflow.start_workflow(
                    session_id=session_id,
                    user_id=user_id,
                    tenant_id=tenant_id,
                )

                invocation_ctx = InvocationContext()
                invocation_ctx.state_manager = self.state_manager

                orch_state = await self.state_manager.load_orchestration_state(
                    user_id=user_id,
                    session_id=session_id
                )

                # ✅ CRITICAL SAFETY INIT
                if orch_state.task is None:
                    orch_state.task = {}


                invocation_ctx.orch_state = orch_state

                # ✅ Plan

                context = {
                    "workflow_id": workflow.session_id,
                    "user_id": user_id,
                    "session_id": session_id,
                    "prompt": prompt,
                    "invocation_ctx": invocation_ctx,
                    "tenant_id": tenant_id,
                }

                # =========================
                # INITIAL AGENT
                # =========================
                root_invocation, _ = await self.agent_service.start_invocation(
                    workflow_id=workflow.session_id,
                    user_id=user_id,
                    session_id=session_id,
                    agent_name="Cortex",
                    prompt=prompt,
                    args={},
                )

                runtime = AgentRuntime(
                    invocation_id=root_invocation.id,
                    agent_name="Cortex",
                )

                invocation_ctx.runtimes[root_invocation.id] = runtime
                invocation_ctx.active_invocation_id = root_invocation.id

                # =========================
                # BUILD MESSAGE
                # =========================
                parts = [Part(text=prompt)]

                parts = await self.session_manager.attach_last_upload(
                    parts, user_id, session_id
                )


                user_msg = Content(role="user", parts=parts)

                await emitter.status("turn_started")

                # =========================
                # RUN AGENT LOOP
                # =========================
                try:
                    async for event in self.runner.run_async(
                        user_id=user_id,
                        session_id=session_id,
                        new_message=user_msg,
                    ):
                        try:
                            await processor.process(event, context)
                        except Exception as e:
                            logger.exception("[STREAM ERROR]: %s", e)
                        finally:
                            await asyncio.sleep(0)

                except Exception:
                    logger.exception("[RUN ERROR]")
                    await emitter.bot_message("❌ Internal error")
                    continue

                # =========================
                # FINAL OUTPUT
                # =========================
                active_invocation_id = invocation_ctx.active_invocation_id
                
                final_runtime=None
                if active_invocation_id:
                    final_runtime = invocation_ctx.runtimes.get(active_invocation_id)

                if not final_runtime:
                    logger.error("[NO FINAL RUNTIME]")
                    await emitter.done()
                    continue

                output = (
                    final_runtime.output_payload
                    if final_runtime.output_payload
                    else final_runtime.buffer
                )

                orch_state = invocation_ctx.orch_state
                orch_task = getattr(orch_state, "task", {}) if orch_state else {}
                # ✅ BLOCK completion for multi-turn
                if orch_task and orch_task.get("interaction") == "request_input":
                    logger.info("⏸ Waiting for user input — not completing")

                elif not getattr(final_runtime, "completed", False):
                    await self.agent_service.complete_invocation(
                        final_runtime.invocation_id,
                        output,
                        final_runtime.input_tokens,
                        final_runtime.output_tokens,
                        final_runtime.total_tokens,
                    )

                # ✅ SAVE CHAT
                if output:
                    await chat_history_service.append_message(
                        session_manager=self.session_manager,
                        user_id=user_id,
                        tenant_id=tenant_id,
                        session_id=session_id,
                        message={"type": "user", "content": prompt},
                    )

                    await chat_history_service.append_message(
                        session_manager=self.session_manager,
                        user_id=user_id,
                        tenant_id=tenant_id,
                        session_id=session_id,
                        message={
                            "type": "ai",
                            "content": str(output),
                            "agent_name": final_runtime.agent_name,
                        },
                    )

                # ✅ DONE SIGNAL (FIXED)
                if orch_task and orch_task.get("interaction") == "request_input":
                    logger.info("⏸ Not sending done() — awaiting input")
                else:
                    await emitter.done()

        except WebSocketDisconnect:
            logger.info("Client disconnected")

        finally:
            await self.workflow.complete_workflow(session_id)
            self.session_manager.mark_disconnected(user_id, session_id)
            logger.info("Cleanup done")