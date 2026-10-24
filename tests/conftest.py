"""Тесты не ходят в сеть: забытая подмена площадки не должна ни тормозить
прогон, ни зависеть от того, что сегодня отдаёт HH или Хабр."""

import aiohttp
import pytest


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    async def blocked(self, method, url, *args, **kwargs):
        raise RuntimeError(f"сеть в тестах запрещена: {method} {url}")

    monkeypatch.setattr(aiohttp.ClientSession, "_request", blocked)
