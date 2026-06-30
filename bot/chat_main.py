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
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
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
from bot.role_categories import CATEGORIES, CATEGORY_IDS, get_category
from bot.roles import ROLES
from bot.russian import format_subscription_roles, format_success_roles

logger = logging.getLogger(__name__)
router = Router()
PID_FILE = Path(__file__).resolve().parent.parent / "logs" / "chat-bot.pid"

BTN_MY_SUBSCRIPTION = "Мои вакансии"
BTN_UNSUBSCRIBE = "Прекратить рассылку"
BTN_CHOOSE_ROLES = "Выбрать роли"
BTN_CHOOSE_ROLES_AGAIN = "Выбрать роли заново"

CALLBACK_CATEGORY_PREFIX = "cat:"
CALLBACK_TOGGLE_PREFIX = "toggle:"
CALLBACK_CONTINUE = "roles:continue"
CALLBACK_BACK = "roles:back"


class SubscribeFlow(StatesGroup):
    picking_category = State()
    picking_roles = State()


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


def _is_subscribed(user_id: int, db: VacancyDatabase) -> bool:
    subscriber = db.get_subscriber(user_id)
    return bool(subscriber and subscriber.get("roles"))


def _choose_roles_button(subscribed: bool) -> str:
    return BTN_CHOOSE_ROLES_AGAIN if subscribed else BTN_CHOOSE_ROLES


def main_menu_keyboard(subscribed: bool = False) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_MY_SUBSCRIPTION)],
            [KeyboardButton(text=BTN_UNSUBSCRIBE)],
            [KeyboardButton(text=_choose_roles_button(subscribed))],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def category_inline_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=category.title, callback_data=f"{CALLBACK_CATEGORY_PREFIX}{category_id}")]
        for category_id in CATEGORY_IDS
        if (category := CATEGORIES.get(category_id))
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def roles_inline_keyboard(category_id: str, selected: set[str]) -> InlineKeyboardMarkup:
    category = get_category(category_id)
    if not category:
        return InlineKeyboardMarkup(inline_keyboard=[])

    rows: list[list[InlineKeyboardButton]] = []
    for role_id in category.role_ids:
        role = ROLES.get(role_id)
        if not role:
            continue
        prefix = "✓ " if role_id in selected else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{prefix}{role.button_label}",
                    callback_data=f"{CALLBACK_TOGGLE_PREFIX}{role_id}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(text="← Назад", callback_data=CALLBACK_BACK),
            InlineKeyboardButton(text="Продолжить", callback_data=CALLBACK_CONTINUE),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _roles_step_text(
    category_id: str, selected: set[str], saved_roles: list[str] | None = None
) -> str:
    category = get_category(category_id)
    title = category.title if category else category_id

    if selected:
        current = format_subscription_roles(sorted(selected))
        current_line = f"Сейчас отмечено: <b>{current}</b>"
    else:
        current_line = "Сейчас отмечено: <i>ничего</i>"

    lines = [
        f"<b>{title}</b> — шаг 2 из 2",
        current_line,
    ]

    if saved_roles:
        lines.append(f"В подписке: <b>{format_subscription_roles(saved_roles)}</b>")

    lines.extend(
        [
            "",
            "Нажми на роль, чтобы отметить или снять.",
            "«Продолжить» — сохранить · «Назад» — к выбору направления.",
        ]
    )
    return "\n".join(lines)


async def _show_category_picker(message: Message, state: FSMContext) -> None:
    await state.set_state(SubscribeFlow.picking_category)
    await message.edit_text(
        "Шаг 1 из 2 — выбери направление:",
        reply_markup=category_inline_keyboard(),
    )


async def _show_roles_picker(
    message: Message,
    state: FSMContext,
    category_id: str,
    selected: set[str],
    saved_roles: list[str],
) -> None:
    await state.set_state(SubscribeFlow.picking_roles)
    await state.update_data(category_id=category_id, selected_roles=sorted(selected))
    await message.edit_text(
        _roles_step_text(category_id, selected, saved_roles),
        parse_mode="HTML",
        reply_markup=roles_inline_keyboard(category_id, selected),
    )


async def send_welcome(message: Message, subscribed: bool = False) -> None:
    await message.answer(
        "Привет! Выбери направление — каждый день в <b>10:00 (МСК)</b> "
        "я буду присылать новые вакансии в личку.\n\n"
        "Можно выбрать несколько ролей внутри направления.\n"
        "Источники: HeadHunter, Habr Career, GeekJob, GetMatch (для дизайнеров).",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(subscribed),
    )


async def send_category_picker(message: Message, state: FSMContext) -> None:
    await state.set_state(SubscribeFlow.picking_category)
    await state.update_data(selected_roles=[])
    await message.answer(
        "Шаг 1 из 2 — выбери направление:",
        reply_markup=category_inline_keyboard(),
    )


async def send_subscription_info(message: Message, db: VacancyDatabase) -> None:
    if not message.from_user:
        return

    subscriber = db.get_subscriber(message.from_user.id)
    if not subscriber or not subscriber.get("roles"):
        await message.answer(
            f"Ты пока не подписан.\nНажми «{BTN_CHOOSE_ROLES}» и пройди настройку.",
            reply_markup=main_menu_keyboard(subscribed=False),
        )
        return

    roles_text = format_subscription_roles(subscriber["roles"])
    await message.answer(
        f"Текущая подписка: <b>{roles_text}</b>\n"
        f"Изменить роли — «{BTN_CHOOSE_ROLES_AGAIN}»\n"
        "Отписаться — «Прекратить рассылку»",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(subscribed=True),
    )


async def unsubscribe_user(message: Message, db: VacancyDatabase, state: FSMContext) -> None:
    if not message.from_user:
        return

    await state.clear()
    subscriber = db.get_subscriber(message.from_user.id)
    if not subscriber:
        await message.answer(
            "Ты не подписан на рассылку.",
            reply_markup=main_menu_keyboard(subscribed=False),
        )
        return

    db.deactivate_subscriber(message.from_user.id)
    await message.answer(
        f"Рассылка остановлена.\nЧтобы вернуться — «{BTN_CHOOSE_ROLES}».",
        reply_markup=main_menu_keyboard(subscribed=False),
    )


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, db: VacancyDatabase) -> None:
    subscribed = (
        _is_subscribed(message.from_user.id, db) if message.from_user else False
    )
    await send_welcome(message, subscribed)
    await send_category_picker(message, state)


@router.message(F.text.in_({BTN_CHOOSE_ROLES, BTN_CHOOSE_ROLES_AGAIN}))
async def btn_choose_roles(message: Message, state: FSMContext) -> None:
    await send_category_picker(message, state)


@router.message(F.text == BTN_MY_SUBSCRIPTION)
async def btn_my_subscription(message: Message, db: VacancyDatabase) -> None:
    await send_subscription_info(message, db)


@router.message(F.text == BTN_UNSUBSCRIBE)
async def btn_unsubscribe(message: Message, db: VacancyDatabase, state: FSMContext) -> None:
    await unsubscribe_user(message, db, state)


@router.message(Command("stop"))
async def cmd_stop(message: Message, db: VacancyDatabase, state: FSMContext) -> None:
    await unsubscribe_user(message, db, state)


@router.message(Command("myrole"))
async def cmd_myrole(message: Message, db: VacancyDatabase) -> None:
    await send_subscription_info(message, db)


@router.callback_query(F.data.startswith(CALLBACK_CATEGORY_PREFIX))
async def on_category_selected(
    callback: CallbackQuery, state: FSMContext, db: VacancyDatabase
) -> None:
    if not callback.data:
        return

    category_id = callback.data[len(CALLBACK_CATEGORY_PREFIX) :]
    category = get_category(category_id)
    if not category:
        await callback.answer("Неизвестное направление", show_alert=True)
        return

    preselected: list[str] = []
    saved_roles: list[str] = []
    if callback.from_user:
        saved_roles = db.get_subscriber_roles(callback.from_user.id)
        preselected = [role_id for role_id in saved_roles if role_id in category.role_ids]

    await state.update_data(selected_roles=preselected)
    await callback.answer()
    if callback.message:
        await _show_roles_picker(
            callback.message,
            state,
            category_id,
            set(preselected),
            saved_roles,
        )


@router.callback_query(F.data == CALLBACK_BACK)
async def on_roles_back(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message:
        await _show_category_picker(callback.message, state)


@router.callback_query(F.data.startswith(CALLBACK_TOGGLE_PREFIX))
async def on_role_toggled(
    callback: CallbackQuery, state: FSMContext, db: VacancyDatabase
) -> None:
    if not callback.data:
        return

    role_id = callback.data[len(CALLBACK_TOGGLE_PREFIX) :]
    if role_id not in ROLES:
        await callback.answer("Неизвестная роль", show_alert=True)
        return

    data = await state.get_data()
    category_id = data.get("category_id")
    if not category_id:
        await callback.answer("Сначала выбери направление", show_alert=True)
        return

    selected = set(data.get("selected_roles") or [])
    if role_id in selected:
        selected.remove(role_id)
    else:
        selected.add(role_id)

    await state.update_data(selected_roles=sorted(selected))
    await callback.answer()

    saved_roles: list[str] = []
    if callback.from_user:
        saved_roles = db.get_subscriber_roles(callback.from_user.id)

    if callback.message:
        await callback.message.edit_text(
            _roles_step_text(category_id, selected, saved_roles),
            parse_mode="HTML",
            reply_markup=roles_inline_keyboard(category_id, selected),
        )


@router.callback_query(F.data == CALLBACK_CONTINUE)
async def on_roles_confirmed(callback: CallbackQuery, state: FSMContext, db: VacancyDatabase) -> None:
    if not callback.from_user:
        return

    data = await state.get_data()
    selected = data.get("selected_roles") or []
    if not selected:
        await callback.answer("Выбери хотя бы одну роль", show_alert=True)
        return

    db.replace_category_roles(
        callback.from_user.id,
        set(get_category(data["category_id"]).role_ids) if get_category(data.get("category_id", "")) else set(),
        selected,
    )
    await state.clear()
    await callback.answer("Подписка оформлена")

    all_roles = db.get_subscriber_roles(callback.from_user.id)
    roles_text = format_success_roles(all_roles)
    if callback.message:
        await callback.message.edit_text(
            f"✅ Готово! Каждый день в <b>10:00 (МСК)</b> буду присылать "
            f"<b>{roles_text}</b>.\n\n"
            "Чтобы добавить роли из другого направления — снова «Выбрать роли заново».",
            parse_mode="HTML",
        )
        await callback.message.answer(
            "Меню управления подпиской — кнопки ниже 👇",
            reply_markup=main_menu_keyboard(subscribed=True),
        )


@router.message()
async def fallback(message: Message, db: VacancyDatabase) -> None:
    subscribed = (
        _is_subscribed(message.from_user.id, db) if message.from_user else False
    )
    await message.answer(
        "Используй кнопки меню 👇",
        reply_markup=main_menu_keyboard(subscribed),
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

    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
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
