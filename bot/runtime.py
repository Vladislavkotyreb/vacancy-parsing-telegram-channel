"""Ограничение потоков: хостинг считает каждый поток процессом.

asyncio выполняет DNS-запросы (aiohttp, aiogram) в пуле потоков по умолчанию —
до min(32, ядра + 4) потоков на процесс, и простаивающие потоки не закрываются.
На reg.ru лимит процессов на аккаунт общий: 25.10.2026 чат-бот и утренний
парсинг канала вместе выбрали его, и рассылка подписчикам в 10:02 не смогла
стартовать («fork: Resource temporarily unavailable»). Четырёх потоков на DNS
хватает: один зависший запрос (сеть хостинга рвётся) не держит остальные.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

MAX_THREADS = 4


def limit_threads(loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
    loop = loop or asyncio.get_running_loop()
    loop.set_default_executor(ThreadPoolExecutor(max_workers=MAX_THREADS, thread_name_prefix="bot-io"))
