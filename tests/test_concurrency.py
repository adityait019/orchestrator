import asyncio
import unittest

from services.concurrency import SessionExecutionCoordinator


class SessionExecutionCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_session_turns_are_serialized(self):
        coordinator = SessionExecutionCoordinator(max_concurrent_turns=2)
        entered: list[str] = []
        release_first = asyncio.Event()
        second_entered = asyncio.Event()

        async def first():
            async with coordinator.turn("user", "session"):
                entered.append("first")
                await release_first.wait()

        async def second():
            async with coordinator.turn("user", "session"):
                entered.append("second")
                second_entered.set()

        first_task = asyncio.create_task(first())
        await asyncio.sleep(0)
        second_task = asyncio.create_task(second())
        await asyncio.sleep(0.02)
        self.assertEqual(entered, ["first"])
        self.assertFalse(second_entered.is_set())

        release_first.set()
        await asyncio.gather(first_task, second_task)
        self.assertEqual(entered, ["first", "second"])

    async def test_different_sessions_can_run_in_parallel(self):
        coordinator = SessionExecutionCoordinator(max_concurrent_turns=2)
        entered = asyncio.Event()
        both_entered = asyncio.Event()
        count = 0
        count_lock = asyncio.Lock()

        async def work(session_id: str):
            nonlocal count
            async with coordinator.turn("user", session_id):
                async with count_lock:
                    count += 1
                    if count == 2:
                        both_entered.set()
                await entered.wait()

        tasks = [asyncio.create_task(work("one")), asyncio.create_task(work("two"))]
        await asyncio.wait_for(both_entered.wait(), timeout=1)
        entered.set()
        await asyncio.gather(*tasks)
