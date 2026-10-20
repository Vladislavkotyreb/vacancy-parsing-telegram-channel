"""Чат-бот для подписок на персональные дайджесты вакансий.

Флоу выбора ролей не хранит состояние: категория едет в callback_data кнопок,
а отмеченные роли читаются из галочек в самой клавиатуре. Поэтому рестарт
процесса не ломает уже показанные пользователю клавиатуры.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

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

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]

from bot.config import Settings
from bot.database import VacancyDatabase
from bot.role_categories import CATEGORIES, CATEGORY_IDS, get_category
from bot.roles import ROLES
from bot.russian import format_subscription_roles, format_success_roles
from bot.stats import format_admin_stats, format_users_page, users_page_count

logger = logging.getLogger(__name__)
router = Router()
PID_FILE = Path(__file__).resolve().parent.parent / "logs" / "chat-bot.pid"

BTN_MY_SUBSCRIPTION = "Мои вакансии"
BTN_UNSUBSCRIBE = "Прекратить рассылку"
BTN_CHOOSE_ROLES = "Выбрать роли"
BTN_CHOOSE_ROLES_AGAIN = "Выбрать роли заново"

S1_CAT = "s1:cat:"
S2_ROLE = "s2:role:"  # s2:role:<category_id>:<role_id>
S2_SAVE = "s2:save:"  # s2:save:<category_id>
S2_BACK = "s2:back"
ADMIN_USERS_PAGE = "adm:users:"  # adm:users:<page>

# Префикс отмеченной роли в клавиатуре — он же признак «роль в черновике».
MARK = "✓ "


def _acquire_single_instance() -> None:
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    if PID_FILE.exists():
        try:
            old_pid = int(PID_FILE.read_text().strip())
            # Свой же pid в файле — не конфликт: его мог записать скрипт запуска
            # раньше, чем мы сюда дошли. Иначе бот принял бы себя за второй
            # экземпляр и вышел, а watchdog никогда не поднял бы его обратно.
            if old_pid != os.getpid():
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


class TrackActivityMiddleware:
    """Отмечает, что человек что-то сделал в боте сегодня — основа DAU/MAU.

    Пишется только факт действия и профиль (имя, username), тексты сообщений
    не храним. Ошибка записи не должна мешать боту ответить.
    """

    # Только то, что человек делает сам. Служебные апдейты вроде my_chat_member
    # (в том числе блокировка бота) активностью не считаются.
    TRACKED_UPDATES = ("message", "callback_query")

    def __init__(self, db: VacancyDatabase, timezone_name: str) -> None:
        self.db = db
        self.tz = ZoneInfo(timezone_name)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is not None and not user.is_bot and self._is_user_action(event):
            try:
                self.db.record_activity(
                    user.id,
                    user.username,
                    user.first_name,
                    user.last_name,
                    day=datetime.now(self.tz).date().isoformat(),
                )
            except Exception:
                logger.exception("Не удалось записать активность пользователя %s", user.id)
        return await handler(event, data)

    @classmethod
    def _is_user_action(cls, event: TelegramObject) -> bool:
        return any(getattr(event, kind, None) is not None for kind in cls.TRACKED_UPDATES)


def _is_admin(user_id: int, settings: Settings) -> bool:
    return settings.telegram_admin_id is not None and user_id == settings.telegram_admin_id


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


def _parse_role_callback(data: str) -> tuple[str, str]:
    """s2:role:<category_id>:<role_id> → (category_id, role_id)."""
    category_id, _, role_id = data[len(S2_ROLE) :].partition(":")
    return category_id, role_id


def _draft_from_keyboard(markup: Optional[InlineKeyboardMarkup]) -> set[str]:
    """Черновик выбора живёт в самой клавиатуре, а не в памяти процесса."""
    draft: set[str] = set()
    if not markup:
        return draft

    for row in markup.inline_keyboard:
        for button in row:
            data = button.callback_data or ""
            if not data.startswith(S2_ROLE) or not button.text.startswith(MARK):
                continue
            _, role_id = _parse_role_callback(data)
            if role_id:
                draft.add(role_id)
    return draft


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
        mark = MARK if role_id in draft else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark}{role.button_label}",
                    callback_data=f"{S2_ROLE}{category_id}:{role_id}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(text="← Назад", callback_data=S2_BACK),
            InlineKeyboardButton(text="Продолжить", callback_data=f"{S2_SAVE}{category_id}"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _specialty_step_text() -> str:
    return "\n".join(
        [
            "<b>Шаг 1 из 2</b> — специальность",
            "Нажми на направление:",
        ]
    )


def _vacancy_step_text(category_id: str, draft: set[str], saved_roles: list[str]) -> str:
    category = get_category(category_id)
    title = category.title if category else category_id
    category_saved = _saved_roles_for_category(saved_roles, category_id)

    if draft:
        picked = f"Сейчас отмечено: <b>{format_subscription_roles(sorted(draft))}</b>"
    else:
        picked = "Сейчас отмечено: <i>ничего</i>"

    lines = [
        f"<b>Шаг 2 из 2</b> — вакансии ({title})",
        picked,
    ]
    if category_saved:
        lines.append(
            f"Уже в подписке ({title}): "
            f"<b>{format_subscription_roles(category_saved)}</b>"
        )
    lines.extend(
        [
            "",
            "Отметь вакансии и нажми «Продолжить».",
            "Пустой выбор + «Продолжить» — убрать направление и вернуться на шаг 1.",
            "«Назад» — отменить без сохранения.",
        ]
    )
    return "\n".join(lines)


async def _show_specialty_step(message: Message) -> None:
    await message.edit_text(
        _specialty_step_text(),
        parse_mode="HTML",
        reply_markup=specialty_keyboard(),
    )


async def _show_vacancy_step(
    message: Message,
    category_id: str,
    draft: set[str],
    saved_roles: list[str],
) -> None:
    await message.edit_text(
        _vacancy_step_text(category_id, draft, saved_roles),
        parse_mode="HTML",
        reply_markup=vacancy_keyboard(category_id, draft),
    )


async def send_welcome(message: Message, subscribed: bool = False) -> None:
    await message.answer(
        "Привет! Каждый день в <b>10:00 (МСК)</b> присылаю новые вакансии в личку.\n\n"
        "Сначала специальность, потом вакансии — можно несколько.\n"
        "Источники: HeadHunter, GeekJob, GetMatch (для дизайнеров).",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(subscribed),
    )


async def start_flow(message: Message) -> None:
    await message.answer(
        _specialty_step_text(),
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


async def unsubscribe_user(message: Message, db: VacancyDatabase) -> None:
    if not message.from_user:
        return

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
async def cmd_start(message: Message, db: VacancyDatabase) -> None:
    subscribed = _is_subscribed(message.from_user.id, db) if message.from_user else False
    await send_welcome(message, subscribed)
    await start_flow(message)


@router.message(F.text.in_({BTN_CHOOSE_ROLES, BTN_CHOOSE_ROLES_AGAIN}))
async def btn_choose_roles(message: Message) -> None:
    await start_flow(message)


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


@router.message(Command("stats"))
async def cmd_stats(message: Message, db: VacancyDatabase, settings: Settings) -> None:
    if not message.from_user:
        return
    if not _is_admin(message.from_user.id, settings):
        await message.answer("Команда только для администратора.")
        return

    text = format_admin_stats(
        db, settings.timezone, exclude_user_id=settings.telegram_admin_id
    )
    await message.answer(text, parse_mode="HTML")


# --- Шаг 1: специальность (тап → сразу шаг 2) ---

@router.callback_query(F.data.startswith(S1_CAT))
async def s1_pick_specialty(callback: CallbackQuery, db: VacancyDatabase) -> None:
    if not callback.data or not callback.message or not callback.from_user:
        return

    category_id = callback.data[len(S1_CAT) :]
    if not get_category(category_id):
        await callback.answer("Неизвестная специальность", show_alert=True)
        return

    saved_roles = db.get_subscriber_roles(callback.from_user.id)
    draft = set(_saved_roles_for_category(saved_roles, category_id))

    await callback.answer()
    await _show_vacancy_step(callback.message, category_id, draft, saved_roles)


# --- Шаг 2: вакансии ---

@router.callback_query(F.data == S2_BACK)
async def s2_back(callback: CallbackQuery) -> None:
    if not callback.message:
        return

    await callback.answer("Выбор отменён")
    await _show_specialty_step(callback.message)


@router.callback_query(F.data.startswith(S2_ROLE))
async def s2_toggle_vacancy(callback: CallbackQuery, db: VacancyDatabase) -> None:
    if not callback.data or not callback.message or not callback.from_user:
        return

    category_id, role_id = _parse_role_callback(callback.data)
    if not get_category(category_id):
        await callback.answer("Сначала выбери специальность", show_alert=True)
        return
    if role_id not in ROLES:
        await callback.answer("Неизвестная роль", show_alert=True)
        return

    draft = _draft_from_keyboard(callback.message.reply_markup)
    if role_id in draft:
        draft.remove(role_id)
    else:
        draft.add(role_id)

    await callback.answer()

    saved_roles = db.get_subscriber_roles(callback.from_user.id)
    await _show_vacancy_step(callback.message, category_id, draft, saved_roles)


@router.callback_query(F.data.startswith(S2_SAVE))
async def s2_save(callback: CallbackQuery, db: VacancyDatabase) -> None:
    if not callback.data or not callback.from_user or not callback.message:
        return

    category_id = callback.data[len(S2_SAVE) :]
    category = get_category(category_id)
    if not category:
        await callback.answer("Сначала выбери направление", show_alert=True)
        return

    draft = sorted(_draft_from_keyboard(callback.message.reply_markup))

    if not draft:
        saved_roles = db.get_subscriber_roles(callback.from_user.id)
        if _saved_roles_for_category(saved_roles, category_id):
            db.replace_category_roles(
                callback.from_user.id,
                set(category.role_ids),
                [],
            )
            if not db.get_subscriber_roles(callback.from_user.id):
                db.deactivate_subscriber(callback.from_user.id)

        await callback.answer()
        await _show_specialty_step(callback.message)
        return

    db.replace_category_roles(
        callback.from_user.id,
        set(category.role_ids),
        draft,
    )
    await callback.answer("Подписка сохранена")

    all_roles = db.get_subscriber_roles(callback.from_user.id)
    roles_text = format_success_roles(all_roles)
    await callback.message.edit_text(
        f"✅ Готово! Каждый день в <b>10:00 (МСК)</b> буду присылать "
        f"<b>{roles_text}</b>.\n\n"
        "Чтобы изменить другое направление — «Выбрать роли заново».",
        parse_mode="HTML",
    )
    await callback.message.answer(
        "Меню 👇",
        reply_markup=main_menu_keyboard(subscribed=True),
    )


def users_keyboard(page: int, pages: int) -> Optional[InlineKeyboardMarkup]:
    if pages <= 1:
        return None
    row = []
    if page > 1:
        row.append(
            InlineKeyboardButton(text="← Назад", callback_data=f"{ADMIN_USERS_PAGE}{page - 1}")
        )
    if page < pages:
        row.append(
            InlineKeyboardButton(text="Вперёд →", callback_data=f"{ADMIN_USERS_PAGE}{page + 1}")
        )
    return InlineKeyboardMarkup(inline_keyboard=[row])


def _users_view(db: VacancyDatabase, settings: Settings, page: int) -> tuple[str, Optional[InlineKeyboardMarkup]]:
    users = db.list_users()
    pages = users_page_count(len(users))
    page = min(max(page, 1), pages)
    text = format_users_page(users, page, settings.timezone, settings.telegram_admin_id)
    return text, users_keyboard(page, pages)


@router.message(Command("users"))
async def cmd_users(message: Message, db: VacancyDatabase, settings: Settings) -> None:
    if not message.from_user:
        return
    if not _is_admin(message.from_user.id, settings):
        await message.answer("Команда только для администратора.")
        return

    text, keyboard = _users_view(db, settings, page=1)
    await message.answer(
        text, parse_mode="HTML", reply_markup=keyboard, disable_web_page_preview=True
    )


@router.callback_query(F.data.startswith(ADMIN_USERS_PAGE))
async def cb_users_page(callback: CallbackQuery, db: VacancyDatabase, settings: Settings) -> None:
    if not callback.data or not callback.message or not callback.from_user:
        return
    if not _is_admin(callback.from_user.id, settings):
        await callback.answer("Только для администратора", show_alert=True)
        return

    try:
        page = int(callback.data[len(ADMIN_USERS_PAGE):])
    except ValueError:
        page = 1

    text, keyboard = _users_view(db, settings, page)
    await callback.answer()
    await callback.message.edit_text(
        text, parse_mode="HTML", reply_markup=keyboard, disable_web_page_preview=True
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

    dp = Dispatcher()
    dp.update.middleware(InjectMiddleware(db=db, settings=settings))
    dp.update.middleware(TrackActivityMiddleware(db, settings.timezone))
    dp.include_router(router)

    logger.info("Чат-бот подписок запущен (polling)")
    try:
        await dp.start_polling(bot)
    finally:
        _release_single_instance()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
