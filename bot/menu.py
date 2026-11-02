"""Штатная кнопка «Меню» Telegram; открытие и закрытие выполняет клиент.

setMyCommands + setChatMenuButton(MenuButtonCommands), без ReplyKeyboardMarkup.
Тексты старой клавиатуры сохранены для кнопок, уже находящихся у пользователей.
"""

from __future__ import annotations

from typing import Optional

from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeChat, MenuButtonCommands

BTN_NOW = "🔎 Вакансии сейчас"
BTN_MY_SUBSCRIPTION = "Мои вакансии"
BTN_UNSUBSCRIBE = "Прекратить рассылку"
BTN_CHOOSE_ROLES = "Выбрать роли"
BTN_CHOOSE_ROLES_AGAIN = "Выбрать роли заново"


def menu_commands() -> list[BotCommand]:
    return [
        BotCommand(command="vacancies", description=BTN_NOW),
        BotCommand(command="myrole", description=BTN_MY_SUBSCRIPTION),
        BotCommand(command="roles", description=BTN_CHOOSE_ROLES),
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
