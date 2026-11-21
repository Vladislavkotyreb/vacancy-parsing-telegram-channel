"""Однократная замена старой нижней клавиатуры в личных чатах Telegram."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

from bot.database import VacancyDatabase
from bot.digest_more import user_lock
from bot.menu import reply_keyboard

logger = logging.getLogger(__name__)


async def refresh_resume_menu(bot: Bot, db: VacancyDatabase, user_id: int, *, proactive: bool) -> None:
    async with user_lock(user_id):
        if not db.needs_resume_menu(user_id, proactive=proactive):
            return
        has_resume = db.get_resume(user_id) is not None
        text = ("Твоё резюме доступно по кнопке «Мои резюме»." if has_resume else
                "Нажми «Добавить резюме» и прикрепи PDF.")
        try:
            await bot.send_message(user_id, text, reply_markup=reply_keyboard(has_resume),
                                   disable_notification=True)
        except TelegramBadRequest as exc:
            if "chat not found" not in str(exc).lower():
                raise
            logger.info("Клавиатура недоступна: чат %s не найден", user_id)
        except TelegramForbiddenError:
            # Если пользователь вернётся, /start сразу покажет актуальную клавиатуру.
            logger.info("Клавиатура недоступна: Telegram запретил отправку в чат %s", user_id)
        db.finish_resume_menu(user_id)


async def refresh_existing_chats(bot: Bot, db: VacancyDatabase) -> None:
    while True:
        try:
            recipients = db.pending_resume_menus()
            for user_id in recipients:
                try:
                    await refresh_resume_menu(bot, db, user_id, proactive=True)
                except TelegramRetryAfter as exc:
                    await asyncio.sleep(exc.retry_after + 1)
                except Exception:
                    logger.exception("Не удалось обновить клавиатуру в чате %s", user_id)
                await asyncio.sleep(0.06)
            if not db.pending_resume_menus():
                logger.info("Обновление клавиатур завершено для доступных личных чатов")
                return
        except Exception:
            logger.exception("Не удалось прочитать очередь обновления клавиатур")
        await asyncio.sleep(60)
