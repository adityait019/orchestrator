import logging
from fastapi import WebSocketDisconnect

logger = logging.getLogger(__name__)


class WSEmitter:

    def __init__(self, websocket,legacy_mode=False):
        self.ws = websocket
        self.closed = False
        self.legacy_mode=legacy_mode

    # =========================================================
    # ✅ SAFE SEND
    # =========================================================
    async def _safe_send(self, payload: dict):
        if self.closed:
            return

        try:
            await self.ws.send_json(payload)
        except WebSocketDisconnect:
            self.closed = True
            logger.warning("⚠️ WebSocket closed")
        except Exception:
            logger.exception("❌ WS send failed")

    # =========================================================
    # ✅ CONNECTION
    # =========================================================
    async def connection_established(self, session_id):
        await self._safe_send({
            "type": "connection_established",
            "message": "🎉 Welcome to Agentic AI Gateway!",
            "session_id": session_id,
        })

    # =========================================================
    # ✅ CHAT MESSAGE
    # =========================================================
    async def bot_message(self, text, agent=None):
        await self._safe_send({
            "type": "bot_message",
            "content": text,
            "agent": agent
        })

    # =========================================================
    # ✅ GENERIC STATUS
    # =========================================================
    async def status(self, stage, agent=None, **extra):
        payload = {
            "type": "status",
            "stage": stage,
            "agent": agent,
        }
        payload.update(extra)

        logger.info(f"[EMITTER: STATUS]: STAGE {stage} EXTRA: {extra}")
        await self._safe_send(payload)

        if self.legacy_mode:
            legacy={
                "type":"status_type",
                "stage":stage,
            }
            legacy.update(extra)
            logger.info(f"[LEGACY EMITTER:STATUS]: sTAGE {stage} EXTRA: {extra}")
            await self._safe_send(legacy)
    # =========================================================
    # ✅ TASK / PROGRESS (A2A)
    # =========================================================
    async def agent_progress(self, agent, state, task_id=None):
        logger.info(f"[EMITTER: PROGRESS]: {agent} -> {state}")

        await self._safe_send({
            "type": "agent_progress",
            "agent": agent,
            "state": state,
            "task_id": task_id
        })

    # =========================================================
    # ✅ TOOL EVENTS
    # =========================================================
    async def tool_call(self, name, args, agent=None):
        logger.info(f"[EMITTER: TOOL_CALL]: NAME: {name}, ARGS: {args}")

        await self._safe_send({
            "type": "tool_call",
            "name": name,
            "args": args,
            "agent": agent,
        })

        if self.legacy_mode:
            legacy={
            "type": "tool_call_type",
            "name": name,
            "args": args,
        }
            logger.info(f"[LEGACY EMITTER: TOOL CALL]: NAME: {name}, ARGS: {args}")
            await self._safe_send(legacy)

    async def tool_result(self, name, response, agent=None):
        logger.info(f"[EMITTER: TOOL_RESULT]: NAME: {name}, RESPONSE: {response}")

        await self._safe_send({
            "type": "tool_result",
            "name": name,
            "response": response,
            "agent": agent,
        })

        if self.legacy_mode:
            legacy={
                "type":"tool_result_type",
                "name":name,
                "response":response,
            }
            logger.info(f"[LEGACY EMITTER: TOOL RESULT]: NAME: {name}, RESPONSE: {response}")
            await self._safe_send(legacy)
            

    # =========================================================
    # ✅ TOKEN USAGE
    # =========================================================
    async def token_usage(self, agent, input_tokens, output_tokens, total_tokens):
        logger.info(
            f"[EMITTER: TOKEN_USAGE]: agent={agent} total={total_tokens}"
        )

        await self._safe_send({
            "type": "token_usage",
            "agent": agent,
            "input": input_tokens,
            "output": output_tokens,
            "total": total_tokens,
        })

    # =========================================================
    # ✅ FILES
    # =========================================================
    async def file_processed(self, urls):
        logger.info(f"[EMITTER: FILE_PROCESSED]: URLS: {urls}")

        await self._safe_send({
            "type": "file_processed",
            "download_link": urls,
            "files": urls,
            "message": "Generated files ready for download"
        })

    # =========================================================
    # ✅ ERROR
    # =========================================================
    async def error_details(self, data):
        logger.info(f"[EMITTER: ERROR_DETAILS]: DATA: {data}")

        await self._safe_send({
            "type": "error_details",
            "data": data
        })

    # =========================================================
    # ✅ DEBUG META (TRACE MODE)
    # =========================================================
    async def debug_meta(self, meta):
        await self._safe_send({
            "type": "debug_meta",
            "meta": meta
        })

    # =========================================================
    # ✅ DONE
    # =========================================================
    async def done(self):
        from datetime import datetime
        ts=datetime.now().isoformat()

        await self._safe_send({
            "type": "done",
            "ts": datetime.now().isoformat()
        })
        if self.legacy_mode:
            logger.info("[LEGACY EMITTER: STATUS TYPE]: STAGE: DONE")
            await self._safe_send({
                "type":"status_type",
                "stage":"done",
                "ts":ts
            })

    async def waiting_for_input(self, question, *, node_id=None, agent=None, task_id=None):
        """Notify clients that an A2A plan is paused for user input."""
        await self._safe_send({
            "type": "waiting_for_input",
            "question": question or "Please provide the requested input.",
            "node_id": node_id,
            "agent_name": agent,
            "task_id": task_id,
        })

    async def plan_completed(self, outputs, nodes=None, total_tokens=0):
        await self._safe_send({
            "type": "plan_completed",
            "outputs": outputs,
            "nodes": nodes or [],
            "total_tokens": total_tokens,
        })


    # =========================================================
    #  Agent Thoughts
    # =========================================================
    async def agent_thoughts(self, agent_name, thoughts):
        await self._safe_send({
            "type": "agent_thoughts",
            "agent_name": agent_name,
            "thoughts": thoughts,
        })