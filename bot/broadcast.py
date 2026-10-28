"""Разовая рассылка всем пользователям бота — например, ченжлог.

Текст лежит в файле в репозитории (`broadcasts/<id>.html`), id рассылки — имя
файла. Если рядом лежит `broadcasts/<id>.mp4`, текст уходит подписью к нему:
видео отправляется анимацией (без звука, Телеграм крутит его по кругу), файл
загружается один раз, дальше уходит по file_id. К каждому сообщению прикладываем
нижнее меню — так новые кнопки появляются сразу, а не со следующей подборкой. Доставка отмечается для каждого получателя только после ответа Телеграма,
поэтому прерванную рассылку можно перезапустить: дошедшим повторно не придёт.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
import html
import re
from typing import Iterable, Optional

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter
from aiogram.types import FSInputFile

from bot.database import VacancyDatabase
from bot.menu import main_menu_keyboard

logger = logging.getLogger(__name__)

# Телеграм разрешает около 30 сообщений в секунду; держимся с запасом.
SEND_PAUSE_SEC = 0.05
NETWORK_RETRIES = 3
# Подпись к видео в Телеграме — не длиннее 1024 символов (без учёта разметки).
CAPTION_LIMIT = 1024
# Рассылка всем — только днём по Москве: ночью и рано утром уведомление будит
# людей (отписки), а в 10:00–10:30 идут утренний сбор и подборка.
SAFE_FROM = (12, 0)
SAFE_TO = (20, 0)


def is_safe_time(hour: int, minute: int) -> bool:
    return SAFE_FROM <= (hour, minute) < SAFE_TO


@dataclass
class BroadcastStats:
    recipients: int = 0
    sent: int = 0
    already_sent: int = 0
    blocked: int = 0
    failed: int = 0


class BroadcastVideo:
    """Видео рассылки: первый раз грузим файл, дальше шлём по file_id."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.file_id: Optional[str] = None


def load_broadcast(path: Path) -> tuple[str, str]:
    """(id рассылки, текст). id — имя файла без расширения."""
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Файл рассылки пуст: {path}")
    return path.stem, text


def find_video(path: Path, text: str) -> Optional[BroadcastVideo]:
    """Видео рядом с текстом (`<id>.mp4`) или None. Слишком длинную подпись не пропускаем."""
    video = path.with_suffix(".mp4")
    if not video.exists():
        return None
    plain = html.unescape(re.sub(r"<[^>]+>", "", text))
    if len(plain) > CAPTION_LIMIT:
        raise ValueError(f"Подпись к видео длиннее {CAPTION_LIMIT} символов: {len(plain)}")
    return BroadcastVideo(video)


async def _send(
    bot: Bot,
    chat_id: int,
    text: str,
    video: Optional[BroadcastVideo] = None,
    reply_markup=None,
) -> None:
    network_retries = 0
    while True:
        try:
            if video is None:
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                    reply_markup=reply_markup,
                )
                return
            message = await bot.send_animation(
                chat_id=chat_id,
                animation=video.file_id or FSInputFile(video.path),
                caption=text,
                parse_mode=ParseMode.HTML,
                width=1080,
                height=1920,
                reply_markup=reply_markup,
            )
            if video.file_id is None:
                media = getattr(message, "animation", None) or getattr(message, "document", None) \
                    or getattr(message, "video", None)
                if media is not None and isinstance(getattr(media, "file_id", None), str):
                    video.file_id = media.file_id
            return
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 1)
        except TelegramNetworkError:
            network_retries += 1
            if network_retries > NETWORK_RETRIES:
                raise
            await asyncio.sleep(10 * network_retries)


async def send_preview(
    bot: Bot, admin_id: int, text: str, video: Optional[BroadcastVideo] = None
) -> None:
    """Превью только админу: отметки не ставятся, рассылка не начинается."""
    await _send(bot, admin_id, text, video, main_menu_keyboard(True))


async def run_broadcast(
    bot: Bot,
    db: VacancyDatabase,
    broadcast_id: str,
    text: str,
    user_ids: Iterable[int],
    video: Optional[BroadcastVideo] = None,
) -> BroadcastStats:
    recipients = list(dict.fromkeys(user_ids))
    stats = BroadcastStats(recipients=len(recipients))

    for user_id in recipients:
        if db.was_broadcast_sent(broadcast_id, user_id):
            stats.already_sent += 1
            continue
        try:
            subscribed = bool(db.get_subscriber_roles(user_id))
            await _send(bot, user_id, text, video, main_menu_keyboard(subscribed))
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
