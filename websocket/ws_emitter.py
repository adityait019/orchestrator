import logging
class WSEmitter:

    def __init__(self, websocket):
        self.ws = websocket

    async def connection_established(self, session_id):
        await self.ws.send_json({
            "type": "connection_established",
            "message": "🎉 Welcome to Agentic AI Gateway!",
            "session_id": session_id,
        })

    async def bot_message(self, text):
        await self.ws.send_json({
            "type": "message",
            "content": text
        })

    async def status(self, stage, **extra):
        """
        Generic status emitter.
        Used for task progress, tool lifecycle, and finalization.
        """
        payload = {
            "type": "status",
            "stage": stage
        }
        payload.update(extra)
        await self.ws.send_json(payload)

    # ✅ OPTIONAL (recommended)
    async def task_update(self, **extra):
        """
        Emits A2A progress/task updates.
        """
        await self.status("progress_update", **extra)

    async def tool_call(self, name, args):

        await self.ws.send_json({
            "type": "tool_call",
            "name": name,
            "args": args
        })

    async def tool_result(self, name, response):
        await self.ws.send_json({
            "type": "tool_result",
            "name": name,
            "response": response
        })

    async def file_processed(self, urls):
        await self.ws.send_json({
            "type": "file_processed",
            "download_link": urls,
            "files": urls,
            "message": "Generated files ready for download"
        })

    async def error_details(self, data):
        await self.ws.send_json({
            "type": "error_details",
            "data": data
        })

    async def done(self):
        from datetime import datetime
        await self.ws.send_json({
            "type": "status",
            "stage": "done",
            "ts": datetime.now().isoformat()
        })