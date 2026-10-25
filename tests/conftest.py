"""Тесты не ходят в сеть: забытая подмена площадки не должна ни тормозить
прогон, ни зависеть от того, что сегодня отдаёт HH или Хабр."""

import aiohttp
import pytest


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    async def blocked(self, method, url, *args, **kwargs):
        raise RuntimeError(f"сеть в тестах запрещена: {method} {url}")

    monkeypatch.setattr(aiohttp.ClientSession, "_request", blocked)


@pytest.fixture(autouse=True)
def _quiet_world_feeds(monkeypatch):
    """Мировая удалёнка по умолчанию пуста, а не «не ответила».

    Недоступная площадка теперь делает сбор роли неполным (аудит 25.10.2026),
    поэтому тесты, которые её не подменяют, иначе получали бы SourceLimited.
    Тест, которому площадка нужна, подменяет её сам — его patch сильнее.
    """
    from unittest.mock import AsyncMock

    import bot.subscriber_collect as sc

    for name in ("_fetch_himalayas", "_fetch_wwr", "_fetch_jobicy"):
        monkeypatch.setattr(sc, name, AsyncMock(return_value=[]))
    monkeypatch.setattr(sc, "SIDE_SOURCE_RETRY_DELAY_SEC", 0)
