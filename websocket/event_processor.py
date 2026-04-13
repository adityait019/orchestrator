# websocket/event_processor.py

from tools.helper_downloads import fetch_remote_file
import logging

class EventProcessor:
    """
    Interprets model events and mutates ONLY runtime invocation state.
    All persistence is delegated to services.
    """

    def __init__(self, emitter, agent_service, artifact_service, file_service):
        self.emitter = emitter
        self.agent_service = agent_service
        self.artifact_service = artifact_service
        self.file_service = file_service

    # -----------------------------------------------------------
    # Invocation finalization helper
    # -----------------------------------------------------------
    async def _finalize_invocation(
        self,
        ctx,
        *,
        failed: bool = False,
        error_msg: str | None = None,
    ):
        ic = ctx["invocation_ctx"]

        if not ic.invocation_id:
            return

        if failed:
            await self.agent_service.fail_invocation(
                ic.invocation_id,
                error_msg or "Invocation failed",
            )
        else:
            await self.agent_service.complete_invocation(
                ic.invocation_id,
                ic.buffer,
            )

        # reset runtime state
        ic.invocation_id = None
        ic.buffer = ""
        ic.input_tokens = 0
        ic.output_tokens = 0
        ic.total_tokens = 0

    # -----------------------------------------------------------
    # Main event processor
    # -----------------------------------------------------------
    async def process(self, event, ctx):
        ic = ctx["invocation_ctx"]

        # =======================================================
        # 0️⃣ Explicit model-level error (fatal)
        # =======================================================
        if getattr(event, "error_message", None):
            ic.buffer += f"\nERROR: {event.error_message}"

            await self._finalize_invocation(
                ctx,
                failed=True,
                error_msg=event.error_message,
            )

            await self.emitter.bot_message(f"❌ {event.error_message}")
            return

        meta = getattr(event, "custom_metadata", {}) or {}

        # =======================================================
        # 1️⃣ ✅ A2A PROGRESS HANDLING (MUST COME FIRST)
        # =======================================================
        
        progress = meta.get("a2a:progress")
        if isinstance(progress, dict):
            payload = {}

            state = progress.get("state")
            if state:
                payload["state"] = state

            message = progress.get("message")
            if message:
                payload["message"] = message

            phase = progress.get("phase")
            if phase:
                payload["phase"] = phase

            step = progress.get("step")
            if step:
                payload["step"] = step

            pct = progress.get("progress")
            if pct is not None:
                payload["progress"] = pct

            waiting_on = progress.get("waiting_on")
            if waiting_on:
                payload["waiting_on"] = waiting_on

            if progress.get("heartbeat"):
                payload["heartbeat"] = True

            # ✅ emits: type=status_type, stage=
            
            logging.info(f"[PROGRESS UPDATE]: {payload}")
            await self.emitter.task_update(**payload)

            # terminal progress state
            if state == "failed":
                await self._finalize_invocation(
                    ctx,
                    failed=True,
                    error_msg=message or "Remote agent failed",
                )
                await self.emitter.bot_message(
                    "❌ The remote agent reported a failure."
                )
                return
            # NOTE: state == "completed" does NOT finalize;
            # final text/file response will follow.

        # =======================================================
        # 2️⃣ Token usage (telemetry-only)
        # =======================================================
        usage = getattr(event, "usage_metadata", None)
        if usage:
            ic.input_tokens += usage.prompt_token_count or 0
            ic.output_tokens += usage.candidates_token_count or 0
            ic.total_tokens += usage.total_token_count or 0

            await self.emitter.status(
                "token_usage",
                input=ic.input_tokens,
                output=ic.output_tokens,
                total=ic.total_tokens,
            )

        # =======================================================
        # 3️⃣ Streaming text (authoritative chat output)
        # =======================================================
        if getattr(event, "text", None):
            ic.buffer += event.text
            await self.emitter.bot_message(event.text)
            return  # prevent duplicate emission from parts

        # =======================================================
        # 4️⃣ A2A RESPONSE STATUS (legacy/compat)
        # =======================================================
        a2a = meta.get("a2a:response")

        if isinstance(a2a, dict):
            status = a2a.get("status", {})
            state = (status.get("state") or "").lower()
            message = status.get("message") or status.get("detail") or ""

            await self.emitter.status(
                "task_update",
                state=state,
                message=message or f"🔄 Task {state.replace('_', ' ')}",
            )

            if state == "failed":
                await self._finalize_invocation(
                    ctx,
                    failed=True,
                    error_msg=message or "Remote agent reported failure",
                )
                await self.emitter.bot_message(
                    "❌ The remote agent reported a failure."
                )
                await self.emitter.error_details(status)
                return

        # =======================================================
        # 5️⃣ UI FILES via custom_metadata (A2A ui_files)
        # =======================================================
        ui_files = meta.get("ui_files")
        if isinstance(ui_files, list) and ic.invocation_id:
            urls = []

            for item in ui_files:
                url = (item or {}).get("url")
                if not url:
                    continue

                file_id, filename, path = await fetch_remote_file(str(url))
                signed_url = self.file_service.make_signed_url(file_id, filename)

                await self.artifact_service.store_artifact(
                    ic.invocation_id,
                    file_id,
                    filename,
                    signed_url,
                    path,
                )
                urls.append(signed_url)

            if urls:
                await self.emitter.status(
                    "tool_completed",
                    message="✅ Task completed successfully.",
                )
                await self.emitter.file_processed(urls)

        # =======================================================
        # 6️⃣ Structured content parts
        # =======================================================
        content = getattr(event, "content", None)
        parts = getattr(content, "parts", None) if content else None
        if not parts:
            return

        for p in parts:

            # ---------------- TOOL CALL ----------------
            if getattr(p, "function_call", None):
                fc = p.function_call

                await self._finalize_invocation(ctx)

                invocation, agent_session_id = await self.agent_service.start_invocation(
                    ctx["workflow_id"],
                    ctx["session_id"],
                    fc.name,
                    ctx["prompt"],
                    fc.args,
                )

                ic.invocation_id = invocation.id
                ic.agent_name = fc.name
                ic.agent_session_id = agent_session_id
                ic.buffer = ""
                ic.input_tokens = 0
                ic.output_tokens = 0
                ic.total_tokens = 0

                await self.emitter.status("tool_started", name=fc.name)
                await self.emitter.tool_call(
                    name=fc.name,
                    args=fc.args,
                )
                continue

            # ---------------- TOOL RESPONSE ----------------
            if getattr(p, "function_response", None):
                await self.emitter.status(
                    "tool_completed",
                    name=p.function_response.name,
                )
                await self.emitter.tool_result(
                    name=p.function_response.name,
                    response=p.function_response.response or {},
                )
                continue

            # ---------------- FILE DATA ----------------
            if getattr(p, "file_data", None) and ic.invocation_id:
                fd = p.file_data
                file_id, filename, path = await fetch_remote_file(fd.file_uri)
                url = self.file_service.make_signed_url(file_id, filename)

                await self.artifact_service.store_artifact(
                    ic.invocation_id,
                    file_id,
                    filename,
                    url,
                    path,
                )

                await self.emitter.file_processed([url])
                continue

            # ---------------- PART TEXT (fallback) ----------------
            if getattr(p, "text", None):
                ic.buffer += p.text
                await self.emitter.bot_message(p.text)
