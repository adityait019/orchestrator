import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from websocket.websocket_handler import WebSocketHandler


class _WebSocket:
    def __init__(self):
        self.sent = []
        self.closed_code = None

    async def accept(self):
        return None

    async def send_json(self, value):
        self.sent.append(value)

    async def receive_json(self):
        return {
            "type": "auth",
            "access_token": "invalid",
            "user_id": "forged-user",
            "tenant_id": "forged-tenant",
        }

    async def close(self, code):
        self.closed_code = code


class WebSocketAuthenticationTests(unittest.IsolatedAsyncioTestCase):
    async def test_forged_frame_identity_is_rejected(self):
        websocket = _WebSocket()
        handler = WebSocketHandler(None, None, None, None, None, None, None)

        with patch(
            "websocket.websocket_handler.get_current_user_from_token",
            new=AsyncMock(side_effect=HTTPException(status_code=401, detail="invalid")),
        ):
            await handler.handle(websocket, "session-1")

        self.assertEqual(websocket.closed_code, 4401)
        self.assertIn({"type": "auth_failed"}, websocket.sent)
