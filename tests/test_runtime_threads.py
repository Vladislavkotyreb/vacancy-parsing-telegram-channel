"""Потоки на процесс: хостинг считает их процессами (сбой рассылки 25.10.2026)."""

from __future__ import annotations

import asyncio
import threading
import unittest

from bot.runtime import MAX_THREADS, limit_threads


class ThreadLimitTest(unittest.TestCase):
    def _peak_threads(self, limited: bool) -> int:
        async def run() -> int:
            if limited:
                limit_threads()
            loop = asyncio.get_running_loop()
            before = threading.active_count()
            # Как aiohttp: DNS — через loop.getaddrinfo, то есть в пуле потоков.
            await asyncio.gather(*(loop.getaddrinfo("localhost", 80 + i) for i in range(50)))
            return threading.active_count() - before

        return asyncio.run(run())

    def test_limited_loop_uses_at_most_max_threads(self):
        self.assertLessEqual(self._peak_threads(limited=True), MAX_THREADS)

    def test_without_limit_python_would_spawn_more(self):
        # Подтверждает, что тест ловит проблему: без ограничения потоков больше.
        self.assertGreater(self._peak_threads(limited=False), MAX_THREADS)


if __name__ == "__main__":
    unittest.main()
