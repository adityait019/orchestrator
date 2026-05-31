# websocket/event_processor.py

from tools.helper_downloads import fetch_remote_file
from websocket.event_normaliser import normalize_event
import uuid
import logging

logger = logging.getLogger(__name__)

class EventProcessor:
    """
    Interprets model events and updates runtime state.
    """

    def __init__(self, emitter, agent_service, artifact_service, file_service):
        self.emitter = emitter
        self.agent_service = agent_service
        self.artifact_service = artifact_service
        self.file_service = file_service

    def _merge_output_payload(self, ic, payload: dict | None):
        if not payload:
            return
        if ic.output_payload is None:
            ic.output_payload = payload
            return

        if not isinstance(ic.output_payload, dict):
            ic.output_payload = payload
            return

        merged = dict(ic.output_payload)
        for key, value in payload.items():
            if key == "text" and isinstance(value, str):
                existing = merged.get("text")
                if isinstance(existing, str):
                    merged["text"] = existing + value
                    continue
            merged[key] = value
        ic.output_payload = merged

    async def _finalize_invocation(self, ctx, *, failed=False, error_msg=None):
        ic = ctx["invocation_ctx"]
        if not ic.invocation_id:
            return

        if failed:
            await self.agent_service.fail_invocation(
                ic.invocation_id,
                error_msg or "Invocation failed",
                ic.input_tokens,
                ic.output_tokens,
                ic.total_tokens,
            )
        else:
            output = ic.output_payload if ic.output_payload is not None else (ic.buffer or None)
            await self.agent_service.complete_invocation(
                ic.invocation_id,
                output,
                ic.input_tokens,
                ic.output_tokens,
                ic.total_tokens,
            )

        # Reset state
        ic.invocation_id = None
        ic.buffer = ""
        ic.output_payload = None
        ic.input_tokens = ic.output_tokens = ic.total_tokens = 0

    async def process(self, event, ctx):
        ic = ctx["invocation_ctx"]



        normalized = normalize_event(event)

        logger.debug(
            "[POST-NORMALIZE] text=%s metadata=%s raw_event=%s",
            normalized.text,
            normalized.metadata,
            type(event)
        )

        # Handle explicit model errors first
        if getattr(event, "error_message", None):
            err_msg = event.error_message
            ic.buffer += f"\nERROR: {err_msg}"
            await self._finalize_invocation(ctx, failed=True, error_msg=err_msg)
            await self.emitter.bot_message(f"❌ {err_msg}")
            return

        # Merge raw metadata + normalized metadata
        meta = {}
        raw_meta = getattr(event, "custom_metadata", {}) or {}
        if isinstance(raw_meta, dict):
            meta.update(raw_meta)
        if isinstance(normalized.metadata, dict):
            meta.update(normalized.metadata)


        # ==== A2A TOKEN USAGE (REMOTE AGENTS) ====


        token_usage = meta.get("token_usage") or meta.get("tool_usage")

        if isinstance(token_usage, dict):

            input_tokens = int(token_usage.get("input_tokens", 0))
            output_tokens = int(token_usage.get("output_tokens", 0))
            total_tokens = int(token_usage.get("total_tokens", 0))

            logger.info(
                "[TOKEN RECEIVED] agent=%s invocation_id=%s input=%s output=%s total=%s",
                ic.agent_name,
                ic.invocation_id,
                input_tokens,
                output_tokens,
                total_tokens,
            )

            # ✅ ✅ SAVE DIRECTLY to correct DB row
            if ic.invocation_id:
                await self.agent_service.add_token_usage(
                    invocation_id=ic.invocation_id,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                )

            # ✅ aggregation (for UI)
            ic.input_tokens += input_tokens
            ic.output_tokens += output_tokens
            ic.total_tokens += total_tokens

            await self.emitter.status(
                "token_usage",
                input=ic.input_tokens,
                output=ic.output_tokens,
                total=ic.total_tokens,
            )

        # ==== A2A Progress Events Handling ====
        # 1) Process any recovered progress events list
        recovered_list = meta.get("recovered_progress_events")
        if isinstance(recovered_list, list):
            for progress in recovered_list:
                event_type = progress.get("event")
                tool_name = progress.get("tool_name", "remote_tool")
                if event_type == "tool_call":
                    logger.info("[REMOTE TOOL CALL]: %s", tool_name)
                    ic.remote_tool_name = tool_name
                    await self.emitter.status("tool_started", name=tool_name)
                    await self.emitter.tool_call(name=tool_name, args={})
                elif event_type == "tool_response":
                    response = progress.get("tool_response", "")
                    logger.info("[REMOTE TOOL RESPONSE] %s", tool_name)
                    await self.emitter.status("tool_completed")
                    await self.emitter.tool_result(
                        name=getattr(ic, "remote_tool_name", tool_name),
                        response={"message": response}
                    )
                else:
                    # Generic progress updates (state/message/etc.)
                    payload = {}
                    for fld in ("state", "message", "phase", "step", "progress", "waiting_on"):
                        if fld in progress:
                            payload[fld] = progress[fld]
                    if progress.get("heartbeat"):
                        payload["heartbeat"] = True
                    if payload:
                        logger.info("[PROGRESS UPDATE]: %s", payload)
                        await self.emitter.task_update(**payload)
                    if progress.get("state") == "failed":
                        await self._finalize_invocation(ctx, failed=True, error_msg=progress.get("message") or "Remote agent failed")
                        await self.emitter.bot_message("❌ The remote agent reported a failure.")
            # Once handled, we skip further progress handling from normalized meta

        # 2) Handle any single progress in meta["a2a:progress"] (backwards compatibility)
        progress = meta.get("a2a:progress")
        if isinstance(progress, dict):
            # (Same logic as above for completeness, but typically recovered_list covers it)
            event_type = progress.get("event")
            if event_type == "tool_call":
                tool_name = progress.get("tool_name", "remote_tool")
                logger.info("[REMOTE TOOL CALL]: %s", tool_name)
                ic.remote_tool_name = tool_name
                await self.emitter.status("tool_started", name=tool_name)
                await self.emitter.tool_call(name=tool_name, args={})
                return
            elif event_type == "tool_response":
                response = progress.get("tool_response", "")
                logger.info("[REMOTE TOOL RESPONSE]")
                await self.emitter.status("tool_completed")
                await self.emitter.tool_result(
                    name=getattr(ic, "remote_tool_name", "remote_tool"),
                    response={"message": response}
                )
                return
            # Generic state updates
            payload = {}
            for fld in ("state", "message", "phase", "step", "progress", "waiting_on"):
                if fld in progress:
                    payload[fld] = progress[fld]
            if progress.get("heartbeat"):
                payload["heartbeat"] = True
            if payload:
                logger.info("[PROGRESS UPDATE]: %s", payload)
                await self.emitter.task_update(**payload)
            if progress.get("state") == "failed":
                await self._finalize_invocation(ctx, failed=True, error_msg=progress.get("message") or "Remote agent failed")
                await self.emitter.bot_message("❌ The remote agent reported a failure.")
                return

        # Token usage updates (unchanged)
        usage = getattr(event, "usage_metadata", None)
        if usage:
            ic.input_tokens += (usage.prompt_token_count or 0)
            ic.output_tokens += (usage.candidates_token_count or 0)
            ic.total_tokens += (usage.total_token_count or 0)
            await self.emitter.status(
                "token_usage",
                input=ic.input_tokens,
                output=ic.output_tokens,
                total=ic.total_tokens,
            )

        # Text streaming: emit assistant text *only if* it is not a progress marker
        skip = False
        sem_progress = meta.get("a2a:progress")
        if isinstance(sem_progress, dict):
            evt = sem_progress.get("event")
            if evt in {"tool_call", "tool_response"}:
                skip = True
        if normalized.text and not skip:
            clean_text = normalized.text.strip()
            if clean_text:
                logger.info("[NORMALIZED TEXT]: %s", clean_text)
                ic.buffer += clean_text
                self._merge_output_payload(ic, {"text": clean_text})
                await self.emitter.bot_message(clean_text)

        # A2A task status updates (unchanged)
        a2a_resp = meta.get("a2a:response")
        if isinstance(a2a_resp, dict):
            status = a2a_resp.get("status", {})
            state = (status.get("state") or "").lower()
            message = status.get("message") or status.get("detail") or ""
            error_text = meta.get("a2a:error_text")
            error_struct = meta.get("a2a:error")

            if error_text:
                message = error_text
            
            await self.emitter.status(
                "task_update",
                state=state,
                message=message or f"🔄 Task {state.replace('_', ' ')}",
            )
            if state == "failed":
                await self._finalize_invocation(ctx, failed=True, error_msg=error_struct or "Remote agent reported failure")
                await self.emitter.bot_message(f"{error_struct or '❌ The remote agent reported a failure.'}")
                await self.emitter.error_details(error_struct or status)
                return

        # File handling (unchanged)
        if normalized.files and ic.invocation_id:
            urls = []
            for file_url in normalized.files:
                try:
                    # tenant_id=str(uuid.uuid4())
                    file_id, filename, path = await fetch_remote_file(str(file_url))
                    signed_url = self.file_service.make_signed_url(
                        tenant_id=ctx.get("tenant_id", str(uuid.uuid4())),
                        user_id=ctx["user_id"],
                        session_id=ctx["session_id"],
                        file_id=file_id,
                        filename=filename,
                    )
                    await self.artifact_service.store_artifact(
                        tenant_id=ctx.get("tenant_id", str(uuid.uuid4())),
                        user_id=ctx["user_id"],
                        session_id=ctx["session_id"],
                        invocation_id=ic.invocation_id,
                        file_id=file_id,
                        filename=filename,
                        signed_url=signed_url,
                        path=path,
                    )
                    urls.append(signed_url)
                except Exception as ex:
                    logger.exception("Failed processing normalized file: %s", ex)
            if urls:
                self._merge_output_payload(ic, {"files": urls})
                await self.emitter.status("tool_completed", message="✅ Files processed successfully.")
                await self.emitter.file_processed(urls)

        # Structured ADK function_call/response (unchanged)
        content = getattr(event, "content", None)
        parts = getattr(content, "parts", None) if content else None
        if parts:
            for p in parts:
                if getattr(p, "function_call", None):
                    fc = p.function_call

                    fn_name = getattr(fc, "name", None)
                    fn_args = getattr(fc, "args", None) or {}

                    try:
                        fn_args = dict(fn_args)
                    except Exception:
                        fn_args = {}

                    # For ADK agent handoff, fc.name is "transfer_to_agent"
                    # but the actual target agent is inside fc.args["agent_name"]
                    if fn_name == "transfer_to_agent":
                        invocation_agent_name = fn_args.get("agent_name")
                    else:
                        invocation_agent_name = fn_name

                    if not invocation_agent_name:
                        logging.warning(
                            "[TOOL CALL] Could not resolve agent name. fn_name=%s args=%s",
                            fn_name,
                            fn_args,
                        )
                        continue

                    await self._finalize_invocation(ctx)
                    invocation, agent_session_id = await self.agent_service.start_invocation(
                        workflow_id=ctx["workflow_id"],
                        session_id=ctx["session_id"],
                        user_id=ctx.get("user_id"),
                        agent_name=invocation_agent_name,
                        prompt=ctx["prompt"],
                        args=fc.args,
                    )
                    ic.invocation_id = invocation.id
                    ic.agent_name = invocation_agent_name
                    ic.agent_session_id = agent_session_id
                    ic.buffer = ""
                    ic.input_tokens = ic.output_tokens = ic.total_tokens = 0
                    await self.emitter.status("tool_started", name=invocation_agent_name)
                    await self.emitter.tool_call(name=fc.name, args=fc.args)
                    continue
                if getattr(p, "function_response", None):
                    fr = p.function_response
                    if fr.response is not None:
                        self._merge_output_payload(ic, {"function_response": {"name": fr.name, "response": fr.response}})
                    await self.emitter.status("tool_completed", name=fr.name)
                    await self.emitter.tool_result(name=fr.name, response=fr.response or {})
                    continue

        logger.debug("[EVENT PROCESSING COMPLETE]")
