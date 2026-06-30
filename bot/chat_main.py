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

S1_CAT = "s1:cat:"
S2_ROLE = "s2:role:"
S2_SAVE = "s2:save"
S2_BACK = "s2:back"


class SubscribeFlow(StatesGroup):
    specialty = State()
    vacancy = State()


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


def _saved_roles_for_category(saved_roles: list[str], category_id: str) -> list[str]:
    category = get_category(category_id)
    if not category:
        return []
    allowed = set(category.role_ids)
    return [role_id for role_id in saved_roles if role_id in allowed]


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


def specialty_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=CATEGORIES[category_id].title,
                callback_data=f"{S1_CAT}{category_id}",
            )
        ]
        for category_id in CATEGORY_IDS
        if category_id in CATEGORIES
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def vacancy_keyboard(category_id: str, draft: set[str]) -> InlineKeyboardMarkup:
    category = get_category(category_id)
    if not category:
        return InlineKeyboardMarkup(inline_keyboard=[])

    rows: list[list[InlineKeyboardButton]] = []
    for role_id in category.role_ids:
        role = ROLES.get(role_id)
        if not role:
            continue
        mark = "✓ " if role_id in draft else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark}{role.button_label}",
                    callback_data=f"{S2_ROLE}{role_id}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(text="← Назад", callback_data=S2_BACK),
            InlineKeyboardButton(text="Продолжить", callback_data=S2_SAVE),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _specialty_step_text(saved_roles: list[str]) -> str:
    lines = ["<b>Шаг 1 из 2</b> — специальность", "Нажми на направление:"]
    if saved_roles:
        lines.append(f"В подписке: <b>{format_subscription_roles(saved_roles)}</b>")
    return "\n".join(lines)


def _vacancy_step_text(category_id: str, draft: set[str], saved_roles: list[str]) -> str:
    category = get_category(category_id)
    title = category.title if category else category_id

    if draft:
        picked = f"Сейчас отмечено: <b>{format_subscription_roles(sorted(draft))}</b>"
    else:
        picked = "Сейчас отмечено: <i>ничего</i>"

    lines = [
        f"<b>Шаг 2 из 2</b> — вакансии ({title})",
        picked,
    ]
    if saved_roles:
        lines.append(f"В подписке: <b>{format_subscription_roles(saved_roles)}</b>")
    lines.extend(
        [
            "",
            "Отметь вакансии и нажми «Продолжить».",
            "«Назад» — отменить выбор и вернуться к специальности.",
        ]
    )
    return "\n".join(lines)


async def _show_specialty_step(
    message: Message, state: FSMContext, saved_roles: list[str]
) -> None:
    await state.set_state(SubscribeFlow.specialty)
    await state.update_data(category_id=None, draft_roles=[])
    await message.edit_text(
        _specialty_step_text(saved_roles),
        parse_mode="HTML",
        reply_markup=specialty_keyboard(),
    )


async def _show_vacancy_step(
    message: Message,
    state: FSMContext,
    category_id: str,
    draft: set[str],
    saved_roles: list[str],
) -> None:
    await state.set_state(SubscribeFlow.vacancy)
    await state.update_data(category_id=category_id, draft_roles=sorted(draft))
    await message.edit_text(
        _vacancy_step_text(category_id, draft, saved_roles),
        parse_mode="HTML",
        reply_markup=vacancy_keyboard(category_id, draft),
    )


async def send_welcome(message: Message, subscribed: bool = False) -> None:
    await message.answer(
        "Привет! Каждый день в <b>10:00 (МСК)</b> присылаю новые вакансии в личку.\n\n"
        "Сначала специальность, потом вакансии — можно несколько.\n"
        "Источники: HeadHunter, Habr Career, GeekJob, GetMatch (для дизайнеров).",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(subscribed),
    )


async def start_flow(message: Message, state: FSMContext, saved_roles: list[str] | None = None) -> None:
    await state.clear()
    await state.set_state(SubscribeFlow.specialty)
    await state.update_data(category_id=None, draft_roles=[])
    roles = saved_roles or []
    await message.answer(
        _specialty_step_text(roles),
        parse_mode="HTML",
        reply_markup=specialty_keyboard(),
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
        f"Изменить — «{BTN_CHOOSE_ROLES_AGAIN}»\n"
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
    subscribed = _is_subscribed(message.from_user.id, db) if message.from_user else False
    await send_welcome(message, subscribed)
    saved = db.get_subscriber_roles(message.from_user.id) if message.from_user else []
    await start_flow(message, state, saved)


@router.message(F.text.in_({BTN_CHOOSE_ROLES, BTN_CHOOSE_ROLES_AGAIN}))
async def btn_choose_roles(message: Message, state: FSMContext, db: VacancyDatabase) -> None:
    saved = db.get_subscriber_roles(message.from_user.id) if message.from_user else []
    await start_flow(message, state, saved)


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


# --- Шаг 1: специальность (тап → сразу шаг 2) ---

@router.callback_query(F.data.startswith(S1_CAT))
async def s1_pick_specialty(
    callback: CallbackQuery, state: FSMContext, db: VacancyDatabase
) -> None:
    if not callback.data or not callback.message or not callback.from_user:
        return

    category_id = callback.data[len(S1_CAT) :]
    if not get_category(category_id):
        await callback.answer("Неизвестная специальность", show_alert=True)
        return

    saved_roles = db.get_subscriber_roles(callback.from_user.id)
    draft = set(_saved_roles_for_category(saved_roles, category_id))

    await callback.answer()
    await _show_vacancy_step(callback.message, state, category_id, draft, saved_roles)


# --- Шаг 2: вакансии ---

@router.callback_query(F.data == S2_BACK)
async def s2_back(callback: CallbackQuery, state: FSMContext, db: VacancyDatabase) -> None:
    if not callback.message:
        return

    saved_roles = db.get_subscriber_roles(callback.from_user.id) if callback.from_user else []

    await state.clear()
    await state.set_state(SubscribeFlow.specialty)
    await state.update_data(category_id=None, draft_roles=[])

    await callback.answer("Выбор отменён")
    await _show_specialty_step(callback.message, state, saved_roles)


@router.callback_query(F.data.startswith(S2_ROLE))
async def s2_toggle_vacancy(
    callback: CallbackQuery, state: FSMContext, db: VacancyDatabase
) -> None:
    if not callback.data or not callback.message:
        return

    role_id = callback.data[len(S2_ROLE) :]
    if role_id not in ROLES:
        await callback.answer("Неизвестная роль", show_alert=True)
        return

    data = await state.get_data()
    category_id = data.get("category_id")
    if not category_id:
        await callback.answer("Сначала выбери специальность", show_alert=True)
        return

    draft = set(data.get("draft_roles") or [])
    if role_id in draft:
        draft.remove(role_id)
    else:
        draft.add(role_id)

    await state.update_data(draft_roles=sorted(draft))
    await callback.answer()

    saved_roles = db.get_subscriber_roles(callback.from_user.id) if callback.from_user else []
    await callback.message.edit_text(
        _vacancy_step_text(category_id, draft, saved_roles),
        parse_mode="HTML",
        reply_markup=vacancy_keyboard(category_id, draft),
    )


@router.callback_query(F.data == S2_SAVE)
async def s2_save(callback: CallbackQuery, state: FSMContext, db: VacancyDatabase) -> None:
    if not callback.from_user or not callback.message:
        return

    if await state.get_state() != SubscribeFlow.vacancy.state:
        await callback.answer("Сначала выбери вакансии", show_alert=True)
        return

    data = await state.get_data()
    draft = data.get("draft_roles") or []
    category_id = data.get("category_id")
    category = get_category(category_id) if category_id else None

    if not draft:
        await callback.answer("Выбери хотя бы одну вакансию", show_alert=True)
        return

    db.replace_category_roles(
        callback.from_user.id,
        set(category.role_ids) if category else set(),
        draft,
    )
    await state.clear()
    await callback.answer("Подписка сохранена")

    all_roles = db.get_subscriber_roles(callback.from_user.id)
    roles_text = format_success_roles(all_roles)
    await callback.message.edit_text(
        f"✅ Готово! Каждый день в <b>10:00 (МСК)</b> буду присылать "
        f"<b>{roles_text}</b>.\n\n"
        "Чтобы добавить другое направление — «Выбрать роли заново».",
        parse_mode="HTML",
    )
    await callback.message.answer(
        "Меню 👇",
        reply_markup=main_menu_keyboard(subscribed=True),
    )


@router.message()
async def fallback(message: Message, db: VacancyDatabase) -> None:
    subscribed = _is_subscribed(message.from_user.id, db) if message.from_user else False
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
