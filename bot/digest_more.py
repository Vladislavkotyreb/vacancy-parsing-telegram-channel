"""Кнопка «Показать остальные» под урезанной подборкой.

Рассылка (cron, run_once) отправляет MAX_VACANCIES_PER_DIGEST самых свежих
вакансий, остаток кладёт в digest_overflow и ставит кнопку под последним
сообщением. Чат-бот — отдельный процесс — по нажатию отдаёт этот остаток.
Кто не нажал, получит остаток в следующие дни, как и раньше.
"""

from __future__ import annotations

import asyncio
import weakref

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import Settings
from bot.database import VacancyDatabase
from bot.dates import is_fresh
from bot.formatters import build_paginated_digest
from bot.models import Vacancy
from bot.russian import plural_ru

DIGEST_MORE = "dg:more:"  # dg:more:<YYYY-MM-DD> — дата подборки по TIMEZONE
NOTHING_LEFT = "Больше вакансий из этой подборки нет"

# Замок на человека: двойное нажатие не должно прислать остаток дважды.
# Слабые ссылки — замок живёт, только пока его держат или ждут.
_locks: weakref.WeakValueDictionary[int, asyncio.Lock] = weakref.WeakValueDictionary()


def more_keyboard(count: int, day: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Показать остальные {count}",
                    callback_data=f"{DIGEST_MORE}{day}",
                )
            ]
        ]
    )


def format_more_header(count: int) -> str:
    noun = plural_ru(count, "вакансия", "вакансии", "вакансий")
    return f"<b>Ещё {count} {noun} из подборки</b>"


def user_lock(user_id: int) -> asyncio.Lock:
    lock = _locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _locks[user_id] = lock
    return lock


def pending_overflow(
    db: VacancyDatabase, settings: Settings, user_id: int, day: str
) -> list[Vacancy]:
    """Что ещё можно показать: не уходило раньше и не устарело с утра."""
    stored = db.get_digest_overflow(user_id, day)
    fresh = [v for v in stored if is_fresh(v, settings.max_vacancy_age_hours)]
    return db.unsent_to_subscriber(user_id, fresh)


async def send_overflow(
    bot: Bot, db: VacancyDatabase, user_id: int, vacancies: list[Vacancy]
) -> int:
    """Отправляет остаток и отмечает его доставленным. Возвращает число сообщений.

    Отметка — после отправки: если сеть оборвётся на середине, остаток и кнопка
    сохранятся и нажатие можно повторить.
    """
    messages, _ = build_paginated_digest(format_more_header(len(vacancies)), vacancies)
    for index, text in enumerate(messages):
        if index:
            await asyncio.sleep(0.4)
        await bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=False,
        )
    for vacancy in vacancies:
        db.mark_sent_to_subscriber(user_id, vacancy)
    return len(messages)
