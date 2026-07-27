import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from auth.deps import get_current_user_from_token
from services.agent_execution_service import AgentExecutionService
from websocket.event_normalizer import normalize_event


class AuthTests(unittest.IsolatedAsyncioTestCase):
    async def test_mock_mode_uses_server_configured_identity(self):
        with patch.dict(
            os.environ,
            {
                "AUTH_MODE": "mock",
                "MOCK_ACCESS_TOKEN": "test-token",
                "MOCK_USER_ID": "mock-user",
                "MOCK_TENANT_ID": "mock-tenant",
            },
            clear=False,
        ), patch("auth.deps.verify_token_via_auth_me", new=AsyncMock()) as verify:
            identity = await get_current_user_from_token("test-token")

        self.assertEqual(identity["user_id"], "mock-user")
        self.assertEqual(identity["tenant_id"], "mock-tenant")
        verify.assert_not_awaited()

    async def test_token_identity_requires_user_and_tenant(self):
        with patch.dict(os.environ, {"AUTH_MODE": "external"}, clear=False), patch(
            "auth.deps.verify_token_via_auth_me", new=AsyncMock(return_value={"user_id": "u"})
        ):
            with self.assertRaises(HTTPException) as ctx:
                await get_current_user_from_token("token")
        self.assertEqual(ctx.exception.status_code, 401)

    async def test_token_identity_comes_from_verifier(self):
        verified = {"user_id": "canonical-user", "tenant_id": "canonical-tenant", "roles": ["member"]}
        with patch.dict(os.environ, {"AUTH_MODE": "external"}, clear=False), patch(
            "auth.deps.verify_token_via_auth_me", new=AsyncMock(return_value=verified)
        ):
            self.assertEqual(await get_current_user_from_token("token"), verified)


class _Result:
    def scalars(self):
        return self

    def first(self):
        return None


class _Query:
    def where(self, *_args):
        return self

    def order_by(self, *_args):
        return self


class _Db:
    def __init__(self):
        self.created = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def execute(self, _statement):
        return _Result()

    def add(self, item):
        self.created.append(item)

    async def commit(self):
        return None

    async def refresh(self, item):
        item.id = 99


class _Invocation:
    class _Field:
        def __eq__(self, _value):
            return True

        def desc(self):
            return self

    orchestration_session_id = _Field()
    step_order = _Field()

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.id = None


class InvocationTests(unittest.IsolatedAsyncioTestCase):
    async def test_child_invocation_persists_its_parent(self):
        db = _Db()
        service = AgentExecutionService(lambda: db, session_service=None)

        with patch("services.agent_execution_service.AgentInvocation", _Invocation), patch(
            "services.agent_execution_service.select", lambda *_args: _Query()
        ):
            invocation, _ = await service.start_invocation(
                workflow_id="conversation-1",
                user_id="user-1",
                session_id="session-1",
                agent_name="specialist",
                prompt="analyse this",
                args={},
                parent_invocation_id=42,
            )

        self.assertEqual(invocation.parent_invocation_id, 42)
        self.assertEqual(invocation.id, 99)


class EventNormalizationTests(unittest.TestCase):
    def test_adk_usage_metadata_is_normalized(self):
        event = SimpleNamespace(
            custom_metadata=None,
            usage_metadata=SimpleNamespace(
                prompt_token_count=244,
                candidates_token_count=17,
                total_token_count=261,
            ),
            content=None,
        )

        normalized = normalize_event(event)

        self.assertEqual(
            normalized.token_usage,
            {"input_tokens": 244, "output_tokens": 17, "total_tokens": 261},
        )
