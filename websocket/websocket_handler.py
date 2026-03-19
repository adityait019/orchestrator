import json
import uuid
from google.genai.types import Content, Part
from websocket.ws_emitter import WSEmitter


class WebSocketHandler:

    def __init__(
        self,
        runner,
        session_service,
        workflow_service,
        agent_service,
        artifact_service,
    ):

        self.runner = runner
        self.sessions = session_service
        self.workflow = workflow_service
        self.agent_service = agent_service
        self.artifact_service = artifact_service

    async def handle(self, websocket, session_id, user_id):

        await websocket.accept()

        emitter = WSEmitter(websocket)

        await emitter.connection_established(session_id)

        session = await self.sessions.get_session(
            app_name="my_agent_app",
            user_id=user_id,
            session_id=session_id,
        )

        if not session:

            session = await self.sessions.create_session(
                app_name="my_agent_app",
                user_id=user_id,
                session_id=session_id,
            )

        while True:

            raw = await websocket.receive_text()

            try:

                obj = json.loads(raw)

                prompt = (obj.get("prompt") or obj.get("content") or "").strip()

            except Exception:

                prompt = raw.strip()

            if not prompt:
                continue

            workflow = await self.workflow.start_workflow(user_id)

            await emitter.status("turn_started")

            parts = [Part(text=prompt)]

            user_msg = Content(role="user", parts=parts)

            async for event in self.runner.run_async(

                user_id=user_id,
                session_id=session.id,
                new_message=user_msg,

            ):

                # error
                if getattr(event, "error_message", None):

                    await emitter.bot_message(
                        f"❌ Server error: {event.error_message}"
                    )

                # streaming text
                if getattr(event, "text", None):

                    await emitter.bot_message(event.text)

                # metadata events
                a2a_resp = (getattr(event, "custom_metadata", {}) or {}).get(
                    "a2a:response"
                )

                if isinstance(a2a_resp, dict):

                    status = a2a_resp.get("status") or {}

                    state = (status.get("state") or "").lower()

                    if state:

                        await emitter.status(
                            "task_update",
                            state=state,
                            message=status.get("message"),
                        )

                content = getattr(event, "content", None)

                parts = getattr(content, "parts", None) if content else None

                if parts:

                    for p in parts:

                        fc = getattr(p, "function_call", None)

                        if fc:

                            await emitter.status(
                                "tool_started",
                                name=fc.name,
                                message=f"🔧 Running {fc.name}",
                            )

                            await emitter.tool_call(fc.name, fc.args or {})

                        fr = getattr(p, "function_response", None)

                        if fr:

                            await emitter.status(
                                "tool_completed",
                                name=fr.name,
                                message=f"✅ {fr.name} finished",
                            )

                            await emitter.tool_result(
                                fr.name,
                                fr.response or {},
                            )

                        if getattr(p, "text", None):

                            await emitter.bot_message(p.text)

            await emitter.done()