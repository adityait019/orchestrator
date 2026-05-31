import logging
from fastapi import WebSocketDisconnect


logger=logging.getLogger(__name__)
class WSEmitter:

    def __init__(self, websocket):
        self.ws = websocket
        self.closed=False


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


    async def connection_established(self, session_id):
        await self._safe_send({
            "type": "connection_established",
            "message": "🎉 Welcome to Agentic AI Gateway!",
            "session_id": session_id,
        })


    async def bot_message(self, text):
        await self._safe_send({
            "type": "message",
            "content": text
        })

    async def status(self, stage, **extra):
        """
        Generic status emitter.
        Used for task progress, tool lifecycle, and finalization.
        """
        payload = {
            "type": "status_type",
            "stage": stage
        }
        payload.update(extra)
        logger.info(f"[EMITTER: STATUS]: STAGE {stage} EXTRA: {extra}")
        await self._safe_send(payload)

    # ✅ OPTIONAL (recommended)
    async def task_update(self, **extra):
        """
        Emits A2A progress/task updates.
        """
        logger.info(f"[EMITTER: TASK_UPDATE]: {extra}")
        await self.status("progress_update", **extra)

    async def tool_call(self, name, args):
        logger.info(f"[EMITTER: TOOL_CALL]: NAME: {name}, ARGS: {args}")

        await self._safe_send({
            "type": "tool_call_type",
            "name": name,
            "args": args
        })

    async def tool_result(self, name, response):
        logger.info(f"[EMITTER: TOOL_RESULT]: NAME: {name}, RESPONSE: {response}")
        await self._safe_send({
            "type": "tool_result_type",
            "name": name,
            "response": response
        })

    async def file_processed(self, urls):
        logger.info(f"[EMITTER: FILE_PROCESSED]: URLS: {urls}")
        await self._safe_send({
            "type": "file_processed",
            "download_link": urls,
            "files": urls,
            "message": "Generated files ready for download"
        })

    async def error_details(self, data):
        logger.info(f"[EMITTER: ERROR_DETAILS]: DATA: {data}")
        await self._safe_send({
            "type": "error_details",
            "data": data
        })

    async def done(self):
        from datetime import datetime
        await self._safe_send({
            "type": "status_type",
            "stage": "done",
            "ts": datetime.now().isoformat()
        })	