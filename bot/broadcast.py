"""Разовая рассылка всем пользователям бота — например, ченжлог.

Текст лежит в файле в репозитории (`broadcasts/<id>.html`), id рассылки — имя
файла. Если рядом лежит `broadcasts/<id>.mp4`, текст уходит подписью к нему:
видео отправляется анимацией (без звука, Телеграм крутит его по кругу), файл
загружается один раз, дальше уходит по file_id. Старую нижнюю клавиатуру убираем:
действия доступны в штатном меню Telegram. Доставка отмечается для каждого получателя только после ответа Телеграма,
поэтому прерванную рассылку можно перезапустить: дошедшим повторно не придёт.
"""

from __future__ import annotations

import asyncio
import fcntl
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import html
import re
from typing import Iterable, Optional

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter
from aiogram.types import FSInputFile

from bot.database import VacancyDatabase

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

# Единственный согласованный утренний анонс для @productdesignervacparser228bot.
RESUME_BOT_ID = 8859745184
RESUME_ANNOUNCEMENT_AT = datetime(2026, 11, 21, 10, tzinfo=timezone(timedelta(hours=3)))
RESUME_ANNOUNCEMENT_END = RESUME_ANNOUNCEMENT_AT.replace(hour=SAFE_TO[0], minute=SAFE_TO[1])
RESUME_ANNOUNCEMENT = Path(__file__).resolve().parent.parent / "broadcasts" / "2026-11-21-resume-match.html"


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
        # Размер — из самого файла: неверный размер Телеграм показывает с обрезкой.
        self.width, self.height = mp4_size(path)


def mp4_size(path: Path) -> tuple[Optional[int], Optional[int]]:
    """Ширина и высота видео из заголовка mp4 (atom tkhd); не нашли — (None, None)."""
    try:
        data = path.read_bytes()
    except OSError:
        return None, None
    at = data.find(b"tkhd")
    while at != -1:
        size = int.from_bytes(data[at - 4:at], "big")
        box = data[at - 4:at - 4 + size]
        if len(box) >= 92:
            width = int.from_bytes(box[-8:-4], "big") >> 16
            height = int.from_bytes(box[-4:], "big") >> 16
            if width and height:
                return width, height
        at = data.find(b"tkhd", at + 4)
    return None, None


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
                width=video.width,
                height=video.height,
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
    await _send(bot, admin_id, text, video)


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
            await _send(bot, user_id, text, video)
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


async def deliver_resume_announcement(bot: Bot, db: VacancyDatabase) -> Optional[BroadcastStats]:
    """Ручной запуск и таймер используют одну базу доставок и один межпроцессный замок."""
    now = datetime.now(RESUME_ANNOUNCEMENT_AT.tzinfo)
    if bot.id != RESUME_BOT_ID or not RESUME_ANNOUNCEMENT_AT <= now < RESUME_ANNOUNCEMENT_END:
        raise ValueError("Этот анонс предназначен для рабочего бота 21 ноября с 10:00 до 20:00 МСК.")
    broadcast_id, caption = load_broadcast(RESUME_ANNOUNCEMENT)
    video = find_video(RESUME_ANNOUNCEMENT, caption)
    if video is None:
        raise FileNotFoundError(RESUME_ANNOUNCEMENT.with_suffix(".mp4"))
    with db.db_path.with_name(broadcast_id + ".lock").open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            logger.info("Рассылка %s уже идёт в другом процессе", broadcast_id)
            return None
        handle.seek(0)
        report = handle.read().strip()
        if report:
            logger.info("Рассылка %s уже завершена. %s", broadcast_id, report)
            return None
        recipients = db.broadcast_audience(include_starters=True)
        if not recipients:
            raise ValueError("В базе нет получателей анонса.")
        logger.info("Начинаю рассылку %s. Получателей: %d", broadcast_id, len(recipients))
        stats = await run_broadcast(bot, db, broadcast_id, caption, recipients, video)
        report = (f"Доставлено сейчас: {stats.sent}. Уже получили: {stats.already_sent}. "
                  f"Заблокировали бота: {stats.blocked}. Ошибок: {stats.failed}.")
        logger.info("%s", report)
        if not stats.failed:
            handle.write(report + "\n")
        return stats


async def scheduled_resume_announcement(bot: Bot, db: VacancyDatabase) -> None:
    if bot.id != RESUME_BOT_ID:
        return
    due = RESUME_ANNOUNCEMENT_AT
    try:
        now = datetime.now(due.tzinfo)
        if now >= RESUME_ANNOUNCEMENT_END:
            return
        if now < due:
            logger.info("Рассылка %s запланирована на %s МСК, включая пользователей без подписки",
                        RESUME_ANNOUNCEMENT.stem, due.strftime("%d.%m.%Y %H:%M"))
        while now < due:
            await asyncio.sleep((due - now).total_seconds())
            now = datetime.now(due.tzinfo)
        if now < RESUME_ANNOUNCEMENT_END:
            await deliver_resume_announcement(bot, db)
    except Exception:
        logger.exception("Сбой запланированной рассылки %s", RESUME_ANNOUNCEMENT.stem)
