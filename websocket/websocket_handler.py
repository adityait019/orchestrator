#websocket/websocket_handler.py
import json
import logging
import asyncio

from google.genai.types import Content, Part
from fastapi import WebSocketDisconnect, HTTPException

from websocket.ws_emitter import WSEmitter
from websocket.event_processor import EventProcessor
from services.invocation_context import InvocationContext, AgentRuntime
from services.chat_history_service import chat_history_service
from services.planning_service import PlanningService
from services.plan_execution_service import PlanExecutionService
from agents.agent import root_agent
from services.concurrency import session_execution_coordinator

logger = logging.getLogger(__name__)

AUTH_TIMEOUT_SECONDS = 10

BREAK_WORDS = {
    "thanks",
    "thank you",
    "ok",
    "okay",
    "cool",
    "great",
    "fine",
    "bye"
}
INPUT_REQUIRED_STATES = {
    "input-required",
    "input_required",
    "inputrequired",
}
class WebSocketHandler:

    def __init__(self, runner, session_manager, workflow_service, agent_service, artifact_service, file_service, state_manager):
        self.runner = runner
        self.session_manager = session_manager
        self.workflow = workflow_service
        self.agent_service = agent_service
        self.artifact_service = artifact_service
        self.file_service = file_service
        self.state_manager = state_manager
        self.planner = PlanningService()
        self.plan_executor: PlanExecutionService | None = (
            PlanExecutionService(agent_service.db, agent_service)
            if agent_service is not None
            else None
        )

    async def _run_runner_turn(self, *, user_id, session_id, user_msg, processor, context):
        """Serialize ADK mutations for a conversation while allowing other sessions."""
        async with session_execution_coordinator.turn(user_id, session_id):
            async for event in self.runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=user_msg,
            ):
                try:
                    await processor.process(event, context)
                    logger.info("Processed event: %s", event)
                except Exception as exc:
                    logger.exception("[STREAM ERROR]: %s", exc)
                finally:
                    await asyncio.sleep(0)

    async def _execute_plan_turn(self, *, user_id, session_id, **kwargs):
        """Plan execution mutates the same conversation state as ADK turns."""
        if self.plan_executor is None:
            raise RuntimeError("Plan execution is unavailable because agent services are not configured")
        async with session_execution_coordinator.turn(user_id, session_id):
            return await self.plan_executor.execute(
                user_id=user_id,
                session_id=session_id,
                **kwargs,
            )

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
        
        await emitter._safe_send({"type": "auth_ok","user_id": user_id, "tenant_id": tenant_id})
        logger.info(
            "WS authenticated: user=%s tenant=%s roles=%s session=%s",
            user_id, tenant_id, roles, session_id,
        )
        await self.session_manager.ensure_session(user_id, session_id)
        self.session_manager.mark_connected(user_id, session_id)
        logger.info("WS connected successfully")
        processor = EventProcessor(
            emitter,
            self.agent_service,
            self.artifact_service,
            self.file_service,
            self.session_manager,
            self.state_manager,
        )
        logger.info("Event processor initialized")
        try:
            while True:

                try:
                    raw = await websocket.receive_text()
                    logger.info("Received raw message: %s", raw)
                except WebSocketDisconnect:
                    logger.info("Client disconnected")
                    break
                except Exception as e:
                    logger.exception("Receive failed: %s", e)
                    continue

                try:
                    obj = json.loads(raw)
                    prompt =(obj.get("prompt") or obj.get("content") or "").strip()
                    
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

                logger.info("Workflow started: %s", workflow.session_id)
                invocation_ctx = InvocationContext()
                invocation_ctx.state_manager = self.state_manager

                orch_state = await self.state_manager.load_orchestration_state(
                    user_id=user_id,
                    session_id=session_id
                )
                active_task = orch_state.task or {}
                
                logger.info(
                    "[TASK LOADED] %s",
                    orch_state.task
                )
                is_break_message = (
                    prompt.lower().strip() in BREAK_WORDS
                )

                task_state = str(active_task.get("state") or "").lower().strip()
                task_interaction = str(active_task.get("interaction") or "").lower().strip()

                is_input_required = (
                    task_interaction == "request_input"
                    or task_state in INPUT_REQUIRED_STATES
                )

                is_continuation = (
                    bool(active_task.get("owner"))
                    and is_input_required
                    and not is_break_message
                )

                logger.info("Loaded orchestration state: %s", orch_state)
                # ✅ CRITICAL SAFETY INIT

                invocation_ctx.orch_state = orch_state



                context = {
                    "workflow_id": workflow.session_id,
                    "user_id": user_id,
                    "session_id": session_id,
                    "prompt": prompt,
                    "invocation_ctx": invocation_ctx,
                    "tenant_id": tenant_id,
                }

                context.update({
                    "continuation": is_continuation,
                    "continued_task": active_task if is_continuation else None,
                })

                pending_plan = orch_state.plan or {}
                if pending_plan.get("status") == "awaiting_input":
                    try:
                        invocation_ctx.root_invocation_id = int(pending_plan["root_invocation_id"])
                        await self._execute_plan_turn(
                            user_id=user_id,
                            session_id=session_id,
                            plan=pending_plan,
                            root_invocation_id=invocation_ctx.root_invocation_id,
                            workflow_id=workflow.session_id,
                            agents=list(root_agent.sub_agents),
                            processor=processor,
                            invocation_ctx=invocation_ctx,
                            tenant_id=tenant_id,
                            resume_input=prompt,
                        )
                        if pending_plan.get("status") == "awaiting_input":
                            await emitter.bot_message(
                                "The plan needs more input to continue.", agent="Nexus"
                            )
                        else:
                            await emitter.bot_message("Plan completed.", agent="Nexus")
                    except Exception as exc:
                        logger.exception("[PLAN RESUME ERROR]")
                        pending_plan["status"] = "failed"
                        pending_plan["error"] = str(exc)
                        await emitter.bot_message("Plan execution failed. Please try again.", agent="Nexus")
                    finally:
                        orch_state.plan = pending_plan
                        await self.state_manager.save_orchestration_state(user_id, session_id, orch_state)
                        await emitter.done()
                    continue

                if pending_plan.get("status") == "awaiting_approval":
                    answer = prompt.lower().strip()
                    if answer in {"yes", "y", "approve", "proceed"}:
                        try:
                            pending_plan["status"] = "running"
                            invocation_ctx.root_invocation_id = int(pending_plan["root_invocation_id"])
                            await self._execute_plan_turn(
                                user_id=user_id,
                                session_id=session_id,
                                plan=pending_plan,
                                root_invocation_id=invocation_ctx.root_invocation_id,
                                workflow_id=workflow.session_id,
                                agents=list(root_agent.sub_agents),
                                processor=processor,
                                invocation_ctx=invocation_ctx,
                                tenant_id=tenant_id,
                            )
                            if pending_plan.get("status") == "awaiting_input":
                                await emitter.bot_message(
                                    "The plan needs more input to continue.", agent="Nexus"
                                )
                            else:
                                await emitter.bot_message("Plan completed.", agent="Nexus")
                        except Exception as exc:
                            logger.exception("[PLAN EXECUTION ERROR]")
                            pending_plan["status"] = "failed"
                            pending_plan["error"] = str(exc)
                            await emitter.bot_message("Plan execution failed. Please try again.", agent="Nexus")
                        finally:
                            orch_state.plan = pending_plan
                            await self.state_manager.save_orchestration_state(user_id, session_id, orch_state)
                            await emitter.done()
                        continue

                    if answer in {"no", "n", "cancel"}:
                        pending_plan["status"] = "cancelled"
                        orch_state.plan = pending_plan
                        await self.state_manager.save_orchestration_state(user_id, session_id, orch_state)
                        await emitter.bot_message("Okay, I cancelled the proposed plan.", agent="Nexus")
                        await emitter.done()
                        continue

                    await emitter.bot_message(
                        "A plan is waiting for approval. Reply 'yes' to execute it or 'no' to cancel.",
                        agent="Nexus",
                    )
                    await emitter.done()
                    continue
                
                logger.info(
                    "[CONTINUATION] %s task=%s",
                    is_continuation,
                    active_task,
                )
                
                logger.info(
                    "[ROUTING] state=%s interaction=%s owner=%s input_required=%s",
                    active_task.get("state"),
                    active_task.get("interaction"),
                    active_task.get("owner"),
                    is_input_required,
                )
                # =========================
                # INITIAL AGENT
                # =========================

                agent_name = "Nexus"  # default agent
                if is_continuation:
                    agent_name = active_task.get("owner")
                    logger.info("Continuing with agent: %s", agent_name)
                root_invocation, _ = await self.agent_service.start_invocation(
                    workflow_id=workflow.session_id,
                    user_id=user_id,
                    session_id=session_id,
                    agent_name=agent_name,
                    prompt=prompt,
                    args={},
                )

                logger.info("Started root invocation: %s", root_invocation.id)
                runtime = AgentRuntime(
                    invocation_id=root_invocation.id,
                    agent_name=root_invocation.agent_name,
                )

                invocation_ctx.runtimes[root_invocation.id] = runtime
                invocation_ctx.active_invocation_id = root_invocation.id

                logger.info("Initialized invocation context: %s", invocation_ctx)
                # =========================
                # BUILD MESSAGE
                # =========================
                parts = [Part(text=prompt)]

                parts = await self.session_manager.attach_last_upload(
                    parts, user_id, session_id
                )

                uploaded_file_urls = [
                    part.file_data.file_uri
                    for part in parts
                    if getattr(part, "file_data", None) is not None
                    and getattr(part.file_data, "file_uri", None)
                ]

                plan = await self.planner.create_plan(
                    prompt=prompt,
                    agents=list(root_agent.sub_agents),
                    uploaded_file_urls=uploaded_file_urls,
                )
                if plan:
                    plan["root_invocation_id"] = root_invocation.id
                    orch_state.plan = plan
                    await self.agent_service.complete_invocation(
                        root_invocation.id,
                        {"plan": plan},
                    )
                    runtime.completed = True
                    await self.state_manager.save_orchestration_state(user_id, session_id, orch_state)
                    steps = "\n".join(
                        f"{index}. {node['agent_name']}: {node['query']}"
                        for index, node in enumerate(plan["nodes"], start=1)
                    )
                    await emitter.bot_message(
                        f"Proposed plan: {plan['summary']}\n\n{steps}\n\nProceed? (yes/no)",
                        agent="Nexus",
                    )
                    await emitter.done()
                    continue

                await self.session_manager.set_tool_context(
                    user_id, session_id,
                    {"access_token": token, "user_id": user_id, "role": roles},
                )

                user_msg = Content(role="user", parts=parts)

                await emitter.status("turn_started")

                logger.info("Starting agent loop for prompt: %s", prompt)
                # =========================
                # RUN AGENT LOOP
                # =========================
                try:
                    await self._run_runner_turn(
                        user_id=user_id,
                        session_id=session_id,
                        user_msg=user_msg,
                        processor=processor,
                        context=context,
                    )

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
                orch_task = getattr(orch_state, "task", None) if orch_state else None
                # ✅ BLOCK completion for multi-turn
                if orch_task and orch_task.get("interaction") == "request_input":
                    logger.info("⏸ Waiting for user input")

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
                if invocation_ctx.orch_state:
                    await self.state_manager.save_orchestration_state(
                        user_id=user_id,
                        session_id=session_id,
                        state=invocation_ctx.orch_state
                    )

                await emitter.done()


        except WebSocketDisconnect:
            logger.info("Client disconnected")

        finally:
            self.session_manager.mark_disconnected(user_id, session_id)
            logger.info("Connection cleanup done; conversation remains active")
