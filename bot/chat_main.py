"""Чат-бот для подписок на персональные дайджесты вакансий."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any, Awaitable, Callable

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    TelegramObject,
)

from bot.config import Settings
from bot.database import VacancyDatabase
from bot.roles import MVP_ROLE_IDS, ROLES

logger = logging.getLogger(__name__)
router = Router()
PID_FILE = Path(__file__).resolve().parent.parent / "logs" / "chat-bot.pid"

BTN_CHOOSE_ROLE = "🎯 Выбрать роль"
BTN_MY_SUBSCRIPTION = "📋 Моя подписка"
BTN_UNSUBSCRIBE = "🚫 Отписаться"


def _acquire_single_instance() -> None:
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    if PID_FILE.exists():
        try:
            old_pid = int(PID_FILE.read_text().strip())
            os.kill(old_pid, 0)
            logger.error("Чат-бот уже запущен (pid=%s). Выход.", old_pid)
            sys.exit(1)
        except (OSError, ValueError):
            PID_FILE.unlink(missing_ok=True)
    PID_FILE.write_text(str(os.getpid()))


def _release_single_instance() -> None:
    PID_FILE.unlink(missing_ok=True)


class InjectMiddleware:
    def __init__(self, **dependencies: Any) -> None:
        self.dependencies = dependencies

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data.update(self.dependencies)
        return await handler(event, data)


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_CHOOSE_ROLE)],
            [KeyboardButton(text=BTN_MY_SUBSCRIPTION), KeyboardButton(text=BTN_UNSUBSCRIBE)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def role_inline_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=ROLES[role_id].button_label, callback_data=f"role:{role_id}")]
        for role_id in MVP_ROLE_IDS
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def send_role_picker(message: Message) -> None:
    await message.answer(
        "Привет! Выбери роль — каждый день в <b>10:00 (МСК)</b> "
        "я буду присылать новые вакансии в личку.\n\n"
        "Источники: HeadHunter, Habr Career, GeekJob, GetMatch (для дизайнеров).",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )
    await message.answer(
        "Нажми на роль:",
        reply_markup=role_inline_keyboard(),
    )


async def send_subscription_info(message: Message, db: VacancyDatabase) -> None:
    if not message.from_user:
        return

    subscriber = db.get_subscriber(message.from_user.id)
    if not subscriber:
        await message.answer(
            "Ты пока не подписан.\nНажми «🎯 Выбрать роль» и выбери направление.",
            reply_markup=main_menu_keyboard(),
        )
        return

    role = ROLES.get(subscriber["role"])
    label = role.label if role else subscriber["role"]
    await message.answer(
        f"Текущая подписка: <b>{label}</b>\n"
        "Сменить роль — «🎯 Выбрать роль»\n"
        "Отписаться — «🚫 Отписаться»",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


async def unsubscribe_user(message: Message, db: VacancyDatabase) -> None:
    if not message.from_user:
        return

    subscriber = db.get_subscriber(message.from_user.id)
    if not subscriber:
        await message.answer(
            "Ты не подписан на рассылку.",
            reply_markup=main_menu_keyboard(),
        )
        return

    db.deactivate_subscriber(message.from_user.id)
    await message.answer(
        "Подписка отменена.\nЧтобы вернуться — «🎯 Выбрать роль».",
        reply_markup=main_menu_keyboard(),
    )


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await send_role_picker(message)


@router.message(F.text == BTN_CHOOSE_ROLE)
async def btn_choose_role(message: Message) -> None:
    await send_role_picker(message)


@router.message(F.text == BTN_MY_SUBSCRIPTION)
async def btn_my_subscription(message: Message, db: VacancyDatabase) -> None:
    await send_subscription_info(message, db)


@router.message(F.text == BTN_UNSUBSCRIBE)
async def btn_unsubscribe(message: Message, db: VacancyDatabase) -> None:
    await unsubscribe_user(message, db)


@router.message(Command("stop"))
async def cmd_stop(message: Message, db: VacancyDatabase) -> None:
    await unsubscribe_user(message, db)


@router.message(Command("myrole"))
async def cmd_myrole(message: Message, db: VacancyDatabase) -> None:
    await send_subscription_info(message, db)


@router.callback_query(F.data.startswith("role:"))
async def on_role_selected(callback: CallbackQuery, db: VacancyDatabase) -> None:
    if not callback.from_user or not callback.data:
        return

    role_id = callback.data.split(":", 1)[1]
    role = ROLES.get(role_id)
    if not role:
        await callback.answer("Неизвестная роль", show_alert=True)
        return

    db.set_subscriber(callback.from_user.id, role_id)
    await callback.answer("Подписка оформлена")

    if callback.message:
        await callback.message.edit_text(
            f"✅ Готово! Каждый день в <b>10:00 (МСК)</b> буду присылать "
            f"новые вакансии <b>{role.label}</b>.",
            parse_mode="HTML",
        )
        await callback.message.answer(
            "Меню управления подпиской — кнопки ниже 👇",
            reply_markup=main_menu_keyboard(),
        )


@router.message()
async def fallback(message: Message) -> None:
    await message.answer(
        "Используй кнопки меню 👇",
        reply_markup=main_menu_keyboard(),
    )


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    settings = Settings.from_env()
    db = VacancyDatabase(settings.db_path)
    bot = Bot(token=settings.telegram_bot_token)

    _acquire_single_instance()

    dp = Dispatcher()
    dp.update.middleware(InjectMiddleware(db=db))
    dp.include_router(router)

    logger.info("Чат-бот подписок запущен (polling)")
    try:
        await dp.start_polling(bot)
    finally:
        _release_single_instance()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
