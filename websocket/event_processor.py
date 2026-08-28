#websocket/event_processor.py
from __future__ import annotations
from tools.helper_downloads import fetch_remote_file
from websocket.event_normalizer import normalize_event
from state.models import RemoteAgentState
from services.concurrency import external_io_semaphore
import asyncio
import logging
import hashlib
import json

logger = logging.getLogger(__name__)
INPUT_REQUIRED_STATES = {
    "input-required",
    "input_required",
    "inputrequired",
}

TERMINAL_STATES = {
    "completed",
    "complete",
    "done",
    "failed",
    "canceled",
    "cancelled",
    "unknown",
}

class EventProcessor:

    def __init__(self, emitter, agent_service, artifact_service, file_service, session_manager, state_manager):
        self.emitter = emitter
        self.agent_service = agent_service
        self.artifact_service = artifact_service
        self.file_service = file_service
        self.session_manager = session_manager
        self.state_manager = state_manager

    # =========================
    # MERGE OUTPUT
    # =========================
    def _merge_output_payload(self, runtime, payload: dict | None):
        if not payload:
            return

        if runtime.output_payload is None:
            runtime.output_payload = payload
            return

        if not isinstance(runtime.output_payload, dict):
            runtime.output_payload = payload
            return

        merged = dict(runtime.output_payload)

        for key, value in payload.items():
            if key == "text" and isinstance(value, str):
                existing = merged.get("text")
                if isinstance(existing, str):
                    merged["text"] = existing + value
                    continue
            merged[key] = value

        runtime.output_payload = merged

    def _hash(self, text: str):
        return hashlib.md5(text.encode()).hexdigest()

    # =========================
    # FINALIZE ✅ FIXED
    # =========================
    async def _finalize_invocation(self, ctx, runtime, *, failed=False, error_msg=None):
        if not runtime or runtime.completed:
            return

        inv_ctx = ctx["invocation_ctx"]
        orch_state = inv_ctx.orch_state
        task = orch_state.task if orch_state else None

        # ✅ CRITICAL FIX — BLOCK finalize if waiting for input
        if task and task.get("interaction") == "request_input" and not failed:
            logger.info("⛔ Preventing premature completion (waiting for input)")
            return

        if failed:
            await self.agent_service.fail_invocation(
                runtime.invocation_id,
                error_msg or "Invocation failed",
                runtime.input_tokens,
                runtime.output_tokens,
                runtime.total_tokens,
            )
        else:
            output = runtime.output_payload if runtime.output_payload is not None else (runtime.buffer or None)

            await self.agent_service.complete_invocation(
                runtime.invocation_id,
                output,
                runtime.input_tokens,
                runtime.output_tokens,
                runtime.total_tokens,
            )

        if orch_state:
            orch_state.active_agent = runtime.agent_name
            orch_state.last_output = runtime.output_payload or runtime.buffer
            inv_ctx.pending_state_update = True

        runtime.completed = True

        logger.info(
            "[FINALIZE] agent=%s invocation=%s status=%s tokens=%d",
            runtime.agent_name,
            runtime.invocation_id,
            "FAILED" if failed else "COMPLETED",
            runtime.total_tokens
        )

    # =========================
    # MAIN PROCESS
    # =========================
    async def process(self, event, ctx):

        inv_ctx = ctx["invocation_ctx"]
        runtime = inv_ctx.runtimes.get(inv_ctx.active_invocation_id)

        logger.info(
            "[EVENT START] event_type=%s active_invocation=%s agent=%s",
            type(event).__name__,
            inv_ctx.active_invocation_id,
            runtime.agent_name if runtime else None
        )

        if not runtime:
            logger.error(
                "[RUNTIME MISSING] active_invocation=%s available_runtimes=%s",
                inv_ctx.active_invocation_id,
                list(inv_ctx.runtimes.keys())
            )
            return

        normalized = normalize_event(event)

        if hasattr(self.agent_service, "record_event"):
            try:
                await self.agent_service.record_event(
                    runtime.invocation_id,
                    str(normalized.a2a_state or type(event).__name__),
                    {
                        "trace_id": inv_ctx.trace_id,
                        "turn_id": inv_ctx.turn_id,
                        "span_id": inv_ctx.active_span_id,
                        "state": normalized.a2a_state,
                        "text": normalized.text,
                        "metadata": normalized.metadata,
                    },
                )
            except Exception:
                logger.exception("[TRACE EVENT SAVE FAILED]")

        # =========================
        # ✅ SAFE METADATA MERGE (FIX)
        # =========================
        meta = {}
        raw_meta = getattr(event, "custom_metadata", {}) or {}

        if isinstance(raw_meta, dict):
            meta.update(raw_meta)

        if isinstance(normalized.metadata, dict):
            for k, v in normalized.metadata.items():

                # ✅ CRITICAL FIX — DO NOT overwrite interaction blindly
                if k == "interaction":
                    if normalized.text:  # ✅ ONLY agent messages
                        meta[k] = v
                    continue

                meta[k] = v

        # =========================
        # ✅ DEBUG META
        # =========================
        if normalized.raw_meta:
            await self.emitter.debug_meta(normalized.raw_meta)

        # =========================
        # ✅ REMOTE STATE
        # =========================
        if self.state_manager:
            context_id = normalized.a2a_context_id or meta.get("a2a:context_id")
            task_id = normalized.a2a_task_id or meta.get("a2a:task_id")

            if context_id or task_id:
                try:
                    await self.state_manager.save_remote_state(
                        user_id=ctx["user_id"],
                        session_id=ctx["session_id"],
                        state=RemoteAgentState(
                            agent_name=runtime.agent_name,
                            scope_key=ctx["session_id"],
                            remote_context_id=context_id,
                            remote_task_id=task_id,
                        )
                    )
                except Exception:
                    logger.exception("[REMOTE STATE SAVE FAILED]")

        # =========================
        # ✅ A2A PROGRESS (FIXED)
        # =========================
        if normalized.a2a_state:
  
            raw_state = str(normalized.a2a_state or "").lower().strip()
            existing_task = ctx["invocation_ctx"].orch_state.task or {}

            interaction = None

            if normalized.text:
                interaction = meta.get("interaction")

            # ✅ Infer interaction from A2A state
            if not interaction and raw_state in INPUT_REQUIRED_STATES:
                interaction = "request_input"

            # ✅ Terminal state should clear active task ownership
            if raw_state in TERMINAL_STATES:
                ctx["invocation_ctx"].orch_state.task = None
                ctx["invocation_ctx"].orch_state.active_agent = None
                inv_ctx.pending_state_update = True

                logger.info(
                    "[TASK CLEARED] state=%s agent=%s",
                    raw_state,
                    runtime.agent_name,
                )

            else:

                ctx["invocation_ctx"].orch_state.task = {
                    "owner": runtime.agent_name,
                    "state": normalized.a2a_state or existing_task.get("state"),
                    "task_id": normalized.a2a_task_id or existing_task.get("task_id"),
                    "context_id": normalized.a2a_context_id or existing_task.get("context_id"),
                    "interaction": (
                        interaction
                        if interaction is not None
                        else existing_task.get("interaction")
                    ),
                }
                if interaction == "request_input" and normalized.text:
                    ctx["invocation_ctx"].orch_state.task["question"] = normalized.text

                inv_ctx.pending_state_update = True

                logger.info(
                    "[TASK PROGRESS UPDATE] %s",
                    ctx["invocation_ctx"].orch_state.task,
                )
            inv_ctx.pending_state_update = True


            
            await self.emitter.agent_progress(
                agent=runtime.agent_name,
                state=normalized.a2a_state,
                task_id=normalized.a2a_task_id,
            )

        # =========================
        # ✅ ERROR
        # =========================
        if getattr(event, "error_message", None):
            err_msg = event.error_message
            runtime.buffer += f"\nERROR: {err_msg}"

            await self._finalize_invocation(ctx, runtime, failed=True, error_msg=err_msg)
            await self.emitter.bot_message(f"❌ {err_msg}", agent=runtime.agent_name)
            return

        # =========================
        # ✅ TOKEN USAGE
        # =========================
        token_usage = (
            normalized.token_usage
            or meta.get("token_usage")
            or meta.get("tool_usage")
        )


        if isinstance(token_usage, dict):
            task_id_for_dedup = normalized.a2a_task_id or meta.get("a2a:task_id")
            dedup_key = (
                task_id_for_dedup,
                token_usage.get("input_tokens"),
                token_usage.get("output_tokens"),
                token_usage.get("total_tokens"),
            )

            if dedup_key in runtime.applied_token_usage_keys:
                logger.info(
                    "[DUPLICATE TOKEN USAGE SKIPPED] task_id=%s agent=%s tokens=%s",
                    task_id_for_dedup, runtime.agent_name, dedup_key[1:],
                )
            else:
                runtime.applied_token_usage_keys.add(dedup_key)

                input_tokens = int(token_usage.get("input_tokens", 0))
                output_tokens = int(token_usage.get("output_tokens", 0))
                total_tokens = int(token_usage.get("total_tokens", 0))

                await self.agent_service.add_token_usage(
                    runtime.invocation_id,
                    input_tokens,
                    output_tokens,
                    total_tokens,
                )

                runtime.input_tokens += input_tokens
                runtime.output_tokens += output_tokens
                runtime.total_tokens += total_tokens

                await self.emitter.token_usage(
                    agent=runtime.agent_name,
                    input_tokens=runtime.input_tokens,
                    output_tokens=runtime.output_tokens,
                    total_tokens=runtime.total_tokens,
                )
        # =========================
        # ✅ TOOL EVENTS
        # =========================
        if meta.get("type") == "tool_event":
            phase = meta.get("phase")
            tool_name = meta.get("tool_name")
            data = meta.get("data")

            if phase == "call":
                await self.emitter.tool_call(name=tool_name, args={}, agent=runtime.agent_name)


            elif phase == "response":
                if getattr(runtime, "last_tool_response", None) == data:
                    logger.info(
                        "[DUPLICATE TOOL RESULT SKIPPED] tool=%s agent=%s",
                        tool_name,
                        runtime.agent_name,
                    )
                else:
                    runtime.last_tool_response = data

                    await self.emitter.tool_result(
                        name=tool_name,
                        response=data or {},
                        agent=runtime.agent_name,
                    )

        # =========================
        # ✅ TEXT STREAMING
        # =========================

        if normalized.text:
            clean = normalized.text.strip()

            try:
                payload = json.loads(clean)

                if (
                    isinstance(payload, dict)
                    and payload.get("interaction")
                ):
                    interaction = payload["interaction"]
                    existing_task = ctx["invocation_ctx"].orch_state.task or {}
                    ctx["invocation_ctx"].orch_state.task = {
                        "owner": runtime.agent_name,
                        "state": normalized.a2a_state,
                        "task_id": normalized.a2a_task_id,
                        "context_id": normalized.a2a_context_id,
                        "interaction": (interaction if interaction is not None else existing_task.get("interaction")),
                    }

                    inv_ctx.pending_state_update = True

                    logger.info(
                        "[TASK UPDATED FROM JSON] %s",
                        ctx["invocation_ctx"].orch_state.task
                    )

            except Exception:
                pass

            h = self._hash(clean)

            if clean and h != getattr(runtime, "last_hash", None):
                runtime.last_hash = h
                runtime.buffer += clean
                self._merge_output_payload(runtime, {"text": clean})

                await self.emitter.bot_message(clean, agent=runtime.agent_name)


        # =========================
        # ✅ FILES
        # =========================
        if normalized.files:
            urls = []

            for file_url in normalized.files:
                if file_url in runtime.processed_file_urls:
                    logger.info(
                        "[DUPLICATE FILE SKIPPED] url=%s agent=%s",
                        file_url, runtime.agent_name,
                    )
                    continue

                runtime.processed_file_urls.add(file_url)

                try:
                    async with external_io_semaphore:
                        file_id, filename, path = await fetch_remote_file(str(file_url))

                    tenant_id = ctx.get("tenant_id") or runtime.invocation_id

                    signed_url = self.file_service.make_signed_url(
                        tenant_id=tenant_id,
                        user_id=ctx["user_id"],
                        session_id=ctx["session_id"],
                        file_id=file_id,
                        filename=filename,
                    )

                    await self.artifact_service.store_artifact(
                        tenant_id=tenant_id,
                        user_id=ctx["user_id"],
                        session_id=ctx["session_id"],
                        invocation_id=runtime.invocation_id,
                        file_id=file_id,
                        filename=filename,
                        signed_url=signed_url,
                        path=path,
                    )

                    urls.append(signed_url)

                except Exception:
                    logger.exception("File processing failed")

            if urls:
                self._merge_output_payload(runtime, {"files": urls})
                await self.emitter.file_processed(urls)

        # =========================
        # ✅ FUNCTION CALL / AGENT SWITCH
        # =========================
        content = getattr(event, "content", None)
        parts = getattr(content, "parts", None) if content else None

        # ✅ FIX: resolve tool_call_id from A2A metadata for patching
        a2a_tool_call_id = (
            raw_meta.get("tool_call_id")
            or normalized.metadata.get("tool_call_id")
        )

        if parts:
            for p in parts:

                if getattr(p, "function_call", None):
                    fc = p.function_call

                    # ✅ FIX: patch missing function_call.id from A2A metadata
                    if not fc.id and a2a_tool_call_id:
                        fc.id = a2a_tool_call_id
                        logger.info(
                            "[PATCHED fc.id] tool=%s id=%s",
                            fc.name, fc.id
                        )
                    elif not fc.id:
                        import uuid
                        fc.id = f"adk_{fc.name}_{uuid.uuid4().hex[:8]}"
                        logger.warning(
                            "[PATCHED fc.id FALLBACK] tool=%s generated id=%s",
                            fc.name, fc.id
                        )

                    fn_name = fc.name
                    fn_args = dict(fc.args or {})

                    agent_name = fn_args.get("agent_name") if fn_name == "transfer_to_agent" else fn_name
                    if not agent_name:
                        continue

                    await self._finalize_invocation(ctx, runtime)

                    invocation, _ = await self.agent_service.start_invocation(
                        workflow_id=ctx["workflow_id"],
                        session_id=ctx["session_id"],
                        user_id=ctx["user_id"],
                        agent_name=agent_name,
                        prompt=ctx["prompt"],
                        args={
                            **fn_args,
                            "trace_id": inv_ctx.trace_id,
                            "turn_id": inv_ctx.turn_id,
                            "parent_span_id": inv_ctx.active_span_id,
                        },
                    )

                    new_runtime = type(runtime)(
                        invocation_id=invocation.id,
                        agent_name=agent_name,
                    )

                    inv_ctx.runtimes[invocation.id] = new_runtime
                    inv_ctx.active_invocation_id = invocation.id

                    await self.emitter.status("tool_started", agent=agent_name)
                    await self.emitter.tool_call(name=fn_name, args=fn_args, agent=agent_name)

                    continue

                if getattr(p, "function_response", None):
                    fr = p.function_response

                    # ✅ FIX: patch missing function_response.id from A2A metadata
                    if not fr.id and a2a_tool_call_id:
                        fr.id = a2a_tool_call_id
                        logger.info(
                            "[PATCHED fr.id] tool=%s id=%s",
                            fr.name, fr.id
                        )
                    elif not fr.id:
                        import uuid
                        fr.id = f"adk_{fr.name}_{uuid.uuid4().hex[:8]}"
                        logger.warning(
                            "[PATCHED fr.id FALLBACK] tool=%s generated id=%s",
                            fr.name, fr.id
                        )

                    self._merge_output_payload(
                        runtime,
                        {"function_response": {
                            "name": fr.name,
                            "response": fr.response,
                        }},
                    )

                    await self.emitter.tool_result(
                        name=fr.name,
                        response=fr.response or {},
                        agent=runtime.agent_name,
                    )
        # =========================
        # ✅ FINALIZE (FIXED)
        # =========================
        is_terminal = not getattr(event, "partial", False)

        task = ctx["invocation_ctx"].orch_state.task

        if task and task.get("interaction") == "request_input":
            logger.info("⏸ Skipping finalize — waiting for user input")
        else:
            if is_terminal and not runtime.completed:
                await self._finalize_invocation(ctx, runtime)

        await asyncio.sleep(0)
