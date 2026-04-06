import json
from google.genai.types import Content, Part

from websocket.ws_emitter import WSEmitter
from websocket.event_processor import EventProcessor
import os

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

    async def handle(self, websocket, session_id, user_id):

        await websocket.accept()
        emitter = WSEmitter(websocket)

        await emitter.connection_established(session_id)

        session = await self.session_manager.get_session(
            app_name="my_agent_app",
            user_id=user_id,
            session_id=session_id,
        )

        if not session:
            session = await self.session_manager.create_session(
                app_name="my_agent_app",
                user_id=user_id,
                session_id=session_id,
            )
        processor = EventProcessor(
            emitter,
            self.agent_service,
            self.artifact_service,
            self.file_service,
        )

        while True:

            raw = await websocket.receive_text()

            try:
                obj = json.loads(raw)
                prompt = (obj.get("prompt") or "").strip()
            except:
                prompt = raw.strip()

            if not prompt:
                continue

            workflow = await self.workflow.start_workflow(user_id)

            await emitter.status("turn_started")

            user_msg = Content(role="user", parts=[Part(text=prompt)])

            context = {
                "workflow_id": workflow.id,
                "session_id": session_id,
                "prompt": prompt,
                "current_invocation": None
            }

            async for event in self.runner.run_async(
                user_id=user_id,
                session_id=session.id,
                new_message=user_msg,
            ):
                await processor.process(event, context)
            
            if context["current_invocation"]:
                await self.agent_service.complete_invocation(
                    context["current_invocation"],
                    "completed"
                )

            await emitter.done()