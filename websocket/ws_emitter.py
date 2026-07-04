import logging
from fastapi import WebSocketDisconnect

logger = logging.getLogger(__name__)


class WSEmitter:

    def __init__(self, websocket):
        self.ws = websocket
        self.closed = False

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

    async def tool_result(self, name, response, agent=None):
        logger.info(f"[EMITTER: TOOL_RESULT]: NAME: {name}, RESPONSE: {response}")

        await self._safe_send({
            "type": "tool_result",
            "name": name,
            "response": response,
            "agent": agent,
        })

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

        await self._safe_send({
            "type": "done",
            "ts": datetime.now().isoformat()
        })