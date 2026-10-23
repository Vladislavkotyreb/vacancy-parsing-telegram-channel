"""Разовая рассылка всем пользователям бота — например, ченжлог.

Текст лежит в файле в репозитории (`broadcasts/<id>.html`), id рассылки — имя
файла. Доставка отмечается для каждого получателя только после ответа Телеграма,
поэтому прерванную рассылку можно перезапустить: дошедшим повторно не придёт.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter

from bot.database import VacancyDatabase

logger = logging.getLogger(__name__)

# Телеграм разрешает около 30 сообщений в секунду; держимся с запасом.
SEND_PAUSE_SEC = 0.05
NETWORK_RETRIES = 3


@dataclass
class BroadcastStats:
    recipients: int = 0
    sent: int = 0
    already_sent: int = 0
    blocked: int = 0
    failed: int = 0


def load_broadcast(path: Path) -> tuple[str, str]:
    """(id рассылки, текст). id — имя файла без расширения."""
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Файл рассылки пуст: {path}")
    return path.stem, text


async def _send(bot: Bot, chat_id: int, text: str) -> None:
    network_retries = 0
    while True:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            return
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 1)
        except TelegramNetworkError:
            network_retries += 1
            if network_retries > NETWORK_RETRIES:
                raise
            await asyncio.sleep(10 * network_retries)


async def send_preview(bot: Bot, admin_id: int, text: str) -> None:
    """Превью только админу: отметки не ставятся, рассылка не начинается."""
    await _send(bot, admin_id, text)


async def run_broadcast(
    bot: Bot,
    db: VacancyDatabase,
    broadcast_id: str,
    text: str,
    user_ids: Iterable[int],
) -> BroadcastStats:
    recipients = list(dict.fromkeys(user_ids))
    stats = BroadcastStats(recipients=len(recipients))

    for user_id in recipients:
        if db.was_broadcast_sent(broadcast_id, user_id):
            stats.already_sent += 1
            continue
        try:
            await _send(bot, user_id, text)
        except TelegramForbiddenError:
            # Заблокировал бота — отписываем, как это делает и утренняя рассылка.
            db.deactivate_subscriber(user_id, reason="blocked")
            stats.blocked += 1
            continue
        except Exception:
            # Не отмечаем: при перезапуске попробуем ещё раз.
            logger.exception("Рассылка %s: не доставлено пользователю %s", broadcast_id, user_id)
            stats.failed += 1
            continue

        db.mark_broadcast_sent(broadcast_id, user_id)
        stats.sent += 1
        await asyncio.sleep(SEND_PAUSE_SEC)

    logger.info("Рассылка %s: %s", broadcast_id, stats)
    return stats
