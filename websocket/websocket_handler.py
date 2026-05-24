# import json
# import uuid
# import logging
# from google.genai.types import Content, Part
# from fastapi import WebSocketDisconnect
# from jose import jwt, JWTError
# import time
# import asyncio
# import uuid
# from websocket.ws_emitter import WSEmitter
# from websocket.event_processor import EventProcessor
# from services.invocation_context import InvocationContext
# from rscp.services.login_services import login_user,LoginClientError,LoginError,LoginNetworkError,LoginRequest,LoginServerError,LoginSuccessResponse,LoginValidationErrorResponse
# import httpx
# from core.config import DEFAULT_USER
# import uuid
# logger = logging.getLogger(__name__)

# AUTH_TIMEOUT_SECONDS = 10    


# class WebSocketHandler:

#     def __init__(
#         self,
#         runner,
#         session_manager,
#         workflow_service,
#         agent_service,
#         artifact_service,
#         file_service,
#     ):
#         self.runner = runner
#         self.session_manager = session_manager
#         self.workflow = workflow_service
#         self.agent_service = agent_service
#         self.artifact_service = artifact_service
#         self.file_service = file_service

#     async def handle(self, websocket, session_id: str):

#         await websocket.accept()
#         emitter = WSEmitter(websocket)
#         await emitter.connection_established(session_id)


#         # # ─────────────────────────────────────────────
#         # # 🔐 AUTH HANDSHAKE (FIRST FRAME, TIME-BOUNDED)
#         # # ─────────────────────────────────────────────
#         # try:
#         #     frame = await asyncio.wait_for(
#         #         websocket.receive_json(),
#         #         timeout=AUTH_TIMEOUT_SECONDS,
#         #     )
#         #     logger.info(f"THIS is Frame {frame}")
#         # except asyncio.TimeoutError:
#         #     await websocket.send_json({"type": "auth_failed", "detail": "auth timeout"})
#         #     await websocket.close(code=4401)
#         #     return
#         # except Exception:
#         #     await websocket.send_json(
#         #         {"type": "auth_failed", "detail": "invalid JSON in auth frame"}
#         #     )
#         #     await websocket.close(code=4401)
#         #     return

#         # if frame.get("type") != "auth":
#         #     await websocket.send_json(
#         #         {"type": "auth_failed", "detail": "first frame must be type=auth"}
#         #     )
#         #     await websocket.close(code=4401)
#         #     return

#         # token = frame.get("access_token")
#         # user_id = frame.get("user_id")      # middleware already verified identity
#         # tenant_id = frame.get("tenant_id")
#         # roles = frame.get("roles", [])

#         # if not token or not isinstance(token, str):
#         #     await websocket.send_json(
#         #         {"type": "auth_failed", "detail": "missing or invalid access_token"}
#         #     )
#         #     await websocket.close(code=4401)
#         #     return

#         # await websocket.send_json({"type": "auth_ok", "scopes": roles})
#         # logger.info(
#         #     "WS authenticated: user=%s tenant=%s roles=%s session=%s",
#         #     user_id, tenant_id, roles, session_id,
#         # )


#         user_id=DEFAULT_USER,
#         tenant_id=str(uuid.uuid4())
        



#         # ✅ Ensure base session exists (user + session scoped)
#         await self.session_manager.ensure_session(
#             user_id=user_id,
#             session_id=session_id,
#         )
#         self.session_manager.mark_connected(user_id, session_id)

#         processor = EventProcessor(
#             emitter,
#             self.agent_service,
#             self.artifact_service,
#             self.file_service,
#         )

#         try:
#             while True:
#                 raw = await websocket.receive_text()

#                 try:
#                     obj = json.loads(raw)
#                     prompt = (obj.get("prompt") or obj.get("content") or "").strip()
#                 except Exception:
#                     prompt = raw.strip()

#                 if not prompt:
#                     continue

#                 try:
#                     # ✅ Start workflow scoped to user
#                     workflow = await self.workflow.start_workflow(user_id)

#                     invocation_ctx = InvocationContext()


#                     root_invocation = await self.agent_service.start_root_invocation(
#                         workflow_id=workflow.id,
#                         user_id=user_id,
#                         session_id=session_id,
#                         prompt=prompt,
#                     )

#                     invocation_ctx.invocation_id = root_invocation.id
#                     invocation_ctx.agent_name = "Cortex"
#                     invocation_ctx.agent_session_id = f"{session_id}::Cortex"
#                     # tenant_id=str(uuid.uuid4)  # In future , I will real tenant id.

#                     context = {
#                         "workflow_id": workflow.id,
#                         "user_id": user_id,          # ✅ IMPORTANT
#                         "session_id": session_id,
#                         "prompt": prompt,
#                         "invocation_ctx": invocation_ctx,
#                         "tenant_id": tenant_id
#                     }

#                     await emitter.status("turn_started")

#                     # ✅ Build user message + attach upload (one‑turn)
#                     parts = [Part(text=prompt)]
#                     parts = await self.session_manager.attach_last_upload(
#                         parts,
#                         user_id=user_id,
#                         session_id=session_id,
#                     )


#                     # ✅ Attach tool tokens (TEMP)
#                     token_result=await self.access_token_handler()

#                     if token_result:


#                         parts = await self.session_manager.attach_tool_tokens(
#                             parts,
#                             payload={
#                                 "access_token": token_result["access_token"],
#                                 "refresh_token": token_result["refresh_token"],
#                             },
#                             session_id=session_id
#                         )
#                     else:
#                         logger.warning("⚠️ Tool tokens not attached: login failed")


#                     user_msg = Content(role="user", parts=parts)

#                     # ✅ Per‑turn ADK session
#                     # turn_session_id = f"{session_id}::turn::{uuid.uuid4()}"
#                     await self.session_manager.ensure_session(
#                         user_id=user_id,
#                         session_id=session_id,
#                     )

#                     async for event in self.runner.run_async(
#                         user_id=user_id,
#                         session_id=session_id,
#                         new_message=user_msg,
#                     ):

#                         await processor.process(event, context)

#                     # ✅ Finalize invocation
#                     ic = context["invocation_ctx"]
#                     if ic.invocation_id:
#                         await self.agent_service.complete_invocation(
#                             ic.invocation_id,
#                             ic.buffer,
#                         )

#                     await self.workflow.complete_workflow(workflow.id)
#                     await emitter.done()

#                 except Exception as e:
#                     logger.exception("🔥 WS processing error")
#                     await emitter.bot_message(
#                         f"❌ ERROR: {type(e).__name__}: {str(e)}"
#                     )

#         except WebSocketDisconnect:
#             self.session_manager.mark_disconnected(user_id, session_id)
#             logger.info("🔌 Client disconnected")




#     async def access_token_handler(self)->dict | None:

#                return {
#                     "access_token": "fkjlghlkd;jfsldkjfolsdkgjooijdsfjl;ksdj",
#                     "refresh_token": "kfhklhoerihoerihfnklcdnfhlsdkfhkjlksdfhiosikdfh",
#                     "user_id": "kdejflkfnjlkjfdofjojopfjpworfjwepofjm",
#                     "tenant_id": "dfkldfhjldkfolkigfjfoifj",
#                     "roles": "user",
#                 }

    




import json
import uuid
import logging
from google.genai.types import Content, Part
from fastapi import WebSocketDisconnect
# from jose import jwt, JWTError
import time
import asyncio
from websocket.ws_emitter import WSEmitter
from websocket.event_processor import EventProcessor
from services.invocation_context import InvocationContext


logger = logging.getLogger(__name__)

# JWT_SECRET = "..."          # shared with tenant service
# JWT_ALG = "HS256"
# AUTH_TIMEOUT_SECONDS = 10

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

    async def handle(self, websocket, session_id: str, user_id: str):

        await websocket.accept()
        emitter = WSEmitter(websocket)
        await emitter.connection_established(session_id)

        # ✅ Ensure base session exists (user + session scoped)
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
                raw = await websocket.receive_text()

                try:
                    obj = json.loads(raw)
                    prompt = (obj.get("prompt") or obj.get("content") or "").strip()
                except Exception:
                    prompt = raw.strip()

                if not prompt:
                    continue

                try:
                    # ✅ Start workflow scoped to user
                    workflow = await self.workflow.start_workflow(user_id)

                    invocation_ctx = InvocationContext()


                    root_invocation = await self.agent_service.start_root_invocation(
                        workflow_id=workflow.id,
                        user_id=user_id,
                        session_id=session_id,
                        prompt=prompt,
                    )

                    invocation_ctx.invocation_id = root_invocation.id
                    invocation_ctx.agent_name = "Cortex"
                    invocation_ctx.agent_session_id = f"{session_id}::Cortex"

                    context = {
                        "workflow_id": workflow.id,
                        "user_id": user_id,          # ✅ IMPORTANT
                        "session_id": session_id,
                        "prompt": prompt,
                        "invocation_ctx": invocation_ctx,
                    }

                    await emitter.status("turn_started")

                    # ✅ Build user message + attach upload (one‑turn)
                    parts = [Part(text=prompt)]
                    parts = await self.session_manager.attach_last_upload(
                        parts,
                        user_id=user_id,
                        session_id=session_id,
                    )

                    user_msg = Content(role="user", parts=parts)

                    # ✅ Per‑turn ADK session
                    turn_session_id = f"{session_id}::turn::{uuid.uuid4()}"
                    await self.session_manager.create_session(
                        user_id=user_id,
                        session_id=turn_session_id,
                    )

                    async for event in self.runner.run_async(
                        user_id=user_id,
                        session_id=turn_session_id,
                        new_message=user_msg,
                    ):
                        meta = getattr(event, "custom_metadata", None)
                        if isinstance(meta, dict):
                            progress = meta.get("a2a:progress")
                            if isinstance(progress, dict):
                                await emitter.task_update(**progress)
                                continue

                        await processor.process(event, context)

                    # ✅ Finalize invocation
                    ic = context["invocation_ctx"]
                    if ic.invocation_id:
                        await self.agent_service.complete_invocation(
                            ic.invocation_id,
                            ic.buffer,
                        )

                    await self.workflow.complete_workflow(workflow.id)
                    await emitter.done()

                except Exception as e:
                    logger.exception("🔥 WS processing error")
                    await emitter.bot_message(
                        f"❌ ERROR: {type(e).__name__}: {str(e)}"
                    )

        except WebSocketDisconnect:
            self.session_manager.mark_disconnected(user_id, session_id)
            logger.info("🔌 Client disconnected")

