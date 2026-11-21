from __future__ import annotations

from typing import Optional

from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeChat, MenuButtonCommands, KeyboardButton, ReplyKeyboardMarkup

BTN_ADD_RESUME = "Добавить резюме"
BTN_MY_RESUMES = "Мои резюме"
BTN_NOW = "🔎 Вакансии сейчас"
BTN_MY_SUBSCRIPTION = "Мои вакансии"
BTN_UNSUBSCRIBE = "Прекратить рассылку"
BTN_CHOOSE_ROLES = "Выбрать роли"
BTN_CHOOSE_ROLES_AGAIN = "Выбрать роли заново"


def reply_keyboard(has_resume: Optional[bool] = None) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=BTN_NOW)],
        [KeyboardButton(text=BTN_MY_SUBSCRIPTION), KeyboardButton(text=BTN_CHOOSE_ROLES)],
    ]
    if has_resume is not None:
        rows.append([KeyboardButton(text=BTN_MY_RESUMES if has_resume else BTN_ADD_RESUME)])
    rows.append([KeyboardButton(text=BTN_UNSUBSCRIBE)])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=False,
        one_time_keyboard=False,
    )


def menu_commands() -> list[BotCommand]:
    return [
        BotCommand(command="vacancies", description=BTN_NOW),
        BotCommand(command="myrole", description=BTN_MY_SUBSCRIPTION),
        BotCommand(command="roles", description=BTN_CHOOSE_ROLES),
        BotCommand(command="resume", description="Добавить или открыть резюме"),
        BotCommand(command="stop", description=BTN_UNSUBSCRIBE),
    ]


async def configure_native_menu(bot: Bot, admin_id: Optional[int] = None) -> None:
    await bot.set_my_commands(
        menu_commands(), scope=BotCommandScopeAllPrivateChats(),
    )
    if admin_id is not None:
        await bot.set_my_commands(
            menu_commands() + [
                BotCommand(command="stats", description="Статистика бота"),
                BotCommand(command="users", description="Пользователи бота"),
            ],
            scope=BotCommandScopeChat(chat_id=admin_id),
        )
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
