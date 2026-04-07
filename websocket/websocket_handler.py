import json
import asyncio
from google.genai.types import Content, Part
from fastapi import WebSocketDisconnect

from websocket.ws_emitter import WSEmitter
from websocket.event_processor import EventProcessor


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

        # 🔥 GLOBAL IDLE HEARTBEAT (keeps connection alive)
        heartbeat_running = True

        async def idle_heartbeat():
            while heartbeat_running:
                await asyncio.sleep(15)
                try:
                    await emitter.status("heartbeat")  # silent ping
                except:
                    break

        hb_task = asyncio.create_task(idle_heartbeat())

        try:
            while True:
                try:
                    raw = await websocket.receive_text()
                except WebSocketDisconnect:
                    print("🔌 Client disconnected")
                    break

                try:
                    obj = json.loads(raw)
                    prompt = (obj.get("prompt") or "").strip()
                except:
                    prompt = raw.strip()

                if not prompt:
                    continue

                workflow = await self.workflow.start_workflow(user_id)

                await emitter.status("turn_started",message="🛞 Processing request...")

                user_msg = Content(role="user", parts=[Part(text=prompt)])

                context = {
                    "workflow_id": workflow.id,
                    "session_id": session_id,
                    "prompt": prompt,
                    "current_invocation": None
                }

                try:
                    # 🔥 PROCESSING HEARTBEAT (during execution)
                    last_ping = 0

                    async def run_with_timeout():
                        nonlocal last_ping

                        async for event in self.runner.run_async(
                            user_id=user_id,
                            session_id=session.id,
                            new_message=user_msg,
                        ):
                            now = asyncio.get_event_loop().time()

                            # send heartbeat every 10 sec
                            if now - last_ping > 10:
                                await emitter.status("processing",message="🧠 Thinking...")
                                last_ping = now

                            await processor.process(event, context)

                    await asyncio.wait_for(run_with_timeout(), timeout=60)

                except asyncio.TimeoutError:
                    await emitter.bot_message("⏱️ Request timed out. Try again.")
                    print("⚠️ Runner timeout")

                except Exception as e:
                    print("🔥 ERROR:", e)
                    await emitter.bot_message("❌ Something went wrong while processing your request.")

                # complete invocation
                if context["current_invocation"]:
                    await self.agent_service.complete_invocation(
                        context["current_invocation"],
                        "completed"
                    )

                # ✅ signal end of response
                await emitter.done()

        finally:
            # 🔥 CLEANUP HEARTBEAT
            heartbeat_running = False
            hb_task.cancel()
            try:
                await hb_task
            except:
                pass