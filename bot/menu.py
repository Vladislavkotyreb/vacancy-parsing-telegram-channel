"""Нижнее меню бота — общее для чат-бота и утренней рассылки.

Меню у человека обновляется, только когда бот присылает его заново. Многие
подписчики ничего не нажимают и только читают подборку — поэтому подборка
тоже приносит актуальное меню, иначе новые кнопки они бы не увидели.
"""

from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_NOW = "🔎 Вакансии сейчас"
BTN_MY_SUBSCRIPTION = "Мои вакансии"
BTN_UNSUBSCRIBE = "Прекратить рассылку"
BTN_CHOOSE_ROLES = "Выбрать роли"
BTN_CHOOSE_ROLES_AGAIN = "Выбрать роли заново"


def choose_roles_button(subscribed: bool) -> str:
    return BTN_CHOOSE_ROLES_AGAIN if subscribed else BTN_CHOOSE_ROLES


def main_menu_keyboard(subscribed: bool = False) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_NOW)],
            [KeyboardButton(text=BTN_MY_SUBSCRIPTION)],
            [KeyboardButton(text=BTN_UNSUBSCRIBE)],
            [KeyboardButton(text=choose_roles_button(subscribed))],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )
