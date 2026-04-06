from datetime import datetime, timezone
from google.genai.types import Part
from tools.helper_downloads import fetch_remote_file


class EventProcessor:

    def __init__(self, emitter, agent_service, artifact_service, file_service):
        self.emitter = emitter
        self.agent_service = agent_service
        self.artifact_service = artifact_service
        self.file_service = file_service


    async def process(self, event, ctx):

        # 1. Error
        if getattr(event, "error_message", None):

            if ctx.get("current_invocation"):
                await self.agent_service.fail_invocation(
                    ctx["current_invocation"],
                    event.error_message
                )

            await self.emitter.bot_message(f"❌ {event.error_message}")
            return
        
        # 2. Streaming text
        if getattr(event, "text", None):
            await self.emitter.bot_message(event.text)
            return

        # 3. Metadata (A2A status)
        meta = getattr(event, "custom_metadata", {}) or {}
        a2a = meta.get("a2a:response")

        if isinstance(a2a, dict):
            status = a2a.get("status") or {}
            state = (status.get("state") or "").lower()

            if state:
                await self.emitter.status(
                    "task_update",
                    state=state,
                    message=status.get("message"),
                )

        # 4. Content parts
        content = getattr(event, "content", None)
        parts = getattr(content, "parts", None) if content else None

        if not parts:
            return

        for p in parts:

            # ---- TOOL CALL ----
            if getattr(p, "function_call", None):
                fc = p.function_call

                await self.emitter.status(
                    "tool_started",
                    name=fc.name,
                    message=f"🔧 Running {fc.name}",
                )

                invocation, agent_session = await self.agent_service.start_invocation(
                    ctx["workflow_id"],
                    ctx["session_id"],
                    fc.name,
                    ctx["prompt"],
                    fc.args
                )

                ctx["current_invocation"] = invocation.id

                continue

            # ---- TOOL RESPONSE ----
            if getattr(p, "function_response", None):
                fr = p.function_response

                await self.emitter.status(
                    "tool_completed",
                    name=fr.name,
                    message=f"✅ {fr.name} finished",
                )
                continue

            # ---- FILE ----
            if getattr(p, "file_data", None):
                fd = p.file_data


                file_id, filename, path = await fetch_remote_file(fd.file_uri)

                signed_url = self.file_service.make_signed_url(file_id, filename)

                await self.artifact_service.store_artifact(
                    ctx["current_invocation"],
                    file_id,
                    filename,
                    signed_url,
                    path
                )

                await self.emitter.file_processed([signed_url])

                continue
            if getattr(event, "usage_metadata", None):
                usage = event.usage_metadata

                # store or emit
                await self.emitter.status(
                    "token_usage",
                    input=usage.prompt_token_count,
                    output=usage.candidates_token_count,
                    total=usage.total_token_count
                )
                
            # ---- TEXT ----
            if getattr(p, "text", None):
                await self.emitter.bot_message(p.text)