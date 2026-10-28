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
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    TelegramObject,
)

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]

from bot.config import Settings
from bot.runtime import limit_threads
from bot.database import VacancyDatabase
from bot.digest_more import (
    DIGEST_MORE,
    NOTHING_LEFT,
    pending_overflow,
    send_overflow,
    user_lock,
)
from bot.role_categories import CATEGORIES, CATEGORY_IDS, get_category
from bot.regions import REGION_BUTTONS, normalize_region, region_phrase
from bot.roles import ROLES
from bot.russian import format_subscription_roles, format_success_roles
from bot.menu import (
    BTN_CHOOSE_ROLES,
    BTN_CHOOSE_ROLES_AGAIN,
    BTN_MY_SUBSCRIPTION,
    BTN_NOW,
    BTN_UNSUBSCRIBE,
    main_menu_keyboard,
)
from bot.subscriber_service import SubscriberService
from bot.stats import (
    USERS_PAGE_SIZE,
    format_admin_stats,
    format_users_page,
    users_page_count,
)

logger = logging.getLogger(__name__)
router = Router()
PID_FILE = Path(__file__).resolve().parent.parent / "logs" / "chat-bot.pid"

# Повторное нажатие «Вакансии сейчас» раньше — просто подсказка, без новой выборки.
NOW_COOLDOWN_SEC = 60
NOW_TEXTS = {
    "not_subscribed": "Сначала выбери роли — кнопка «Выбрать роли» внизу.",
    "no_cache": "Вакансии ещё собираются — первая подборка придёт с утренней рассылкой.",
    "nothing_new": "Новых вакансий пока нет — всё свежее ты уже получил.\nУтром проверю снова.",
    "digest_running": "Утренняя рассылка идёт прямо сейчас — подборка придёт через пару минут.",
}
DIGEST_LOCK = Path(__file__).resolve().parent.parent / "logs" / "digest.lock"


def _digest_running() -> bool:
    """Утренняя рассылка держит flock на logs/digest.lock (bot/run_once.py) всё время работы.

    Пока она идёт, кнопку не обслуживаем: рассылка отмечает вакансии после
    отправки, и нажатие в эти секунды прислало бы часть подборки дважды.
    """
    import fcntl

    if not DIGEST_LOCK.exists():
        return False
    try:
        with open(DIGEST_LOCK, "a") as handle:
            fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)
            fcntl.flock(handle, fcntl.LOCK_UN)
        return False
    except OSError:
        return True

S0_REGION = "s0:reg:"  # s0:reg:<cis|world|both>
S1_CAT = "s1:cat:"
S2_ROLE = "s2:role:"  # s2:role:<category_id>:<role_id>
S2_SAVE = "s2:save:"  # s2:save:<category_id>
S2_BACK = "s2:back"
ADMIN_USERS_PAGE = "adm:users:"  # adm:users:<page>
# Подтверждение отписки: случайное нажатие «Прекратить рассылку» отписывало сразу.
UNSUB_YES = "u:yes"
UNSUB_NO = "u:no"
PROFILE_FETCH_CONCURRENCY = 5
PROFILE_FETCH_TIMEOUT_SEC = 5
# Паузы между попытками достучаться до Телеграма на старте (~3 минуты в сумме).
STARTUP_RETRY_DELAYS_SEC = (5, 10, 20, 30, 60, 60)

# Префикс отмеченной роли в клавиатуре — он же признак «роль в черновике».
MARK = "✓ "
STALE_BUTTON_TEXT = "Эта кнопка устарела. Нажми «Выбрать роли» в меню внизу."


# Один экземпляр — через flock, а не по pid в файле. Pid-замок ломался трижды:
# бот принимал свой pid за чужой; номер умершего процесса доставался чужой
# программе — и бот не поднимался вовсе; закрываясь, копия стирала pid-файл
# следующей, и ручной перезапуск плодил дубли (4 копии 25.10.2026). flock
# снимает ядро при любой смерти процесса, даже kill -9; файл замка не удаляют.
LOCK_FILE = PID_FILE.with_name("chat-bot.lock")
_lock_handle = None


def _acquire_single_instance() -> None:
    global _lock_handle
    import fcntl

    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    handle = open(LOCK_FILE, "a")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        logger.error("Чат-бот уже запущен (замок %s занят). Выход.", LOCK_FILE)
        sys.exit(1)
    _lock_handle = handle
    # pid-файл — только для людей: кто сейчас держит бота.
    PID_FILE.write_text(str(os.getpid()))


def _release_single_instance() -> None:
    global _lock_handle
    try:
        if PID_FILE.read_text().strip() == str(os.getpid()):
            PID_FILE.unlink()
    except (OSError, ValueError):
        pass
    if _lock_handle is not None:
        _lock_handle.close()
        _lock_handle = None


async def _answer(callback: CallbackQuery, text: Optional[str] = None, show_alert: bool = False) -> None:
    """Ответ на нажатие, который не роняет обработчик.

    После сбоя сети Телеграм отдаёт накопленные нажатия с опозданием, и ответ
    на них падает с «query is too old». Раньше это обрывало обработчик уже после
    записи в базу: роли сохранены, а человек не видит ни подтверждения, ни меню.
    """
    try:
        await callback.answer(text, show_alert=show_alert)
    except TelegramBadRequest as exc:
        logger.info("Ответ на нажатие не ушёл (%s): %s", callback.data, exc)


class StaleCallbackMiddleware:
    """Нажатие под сообщением, которое бот уже не может править (слишком старое,
    удалённое — InaccessibleMessage): у обработчиков нет edit_text, и они падали,
    а кнопка крутилась без ответа."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # «Показать остальные» работает и без сообщения: остаток берётся по id.
        if (
            isinstance(event, CallbackQuery)
            and not isinstance(event.message, Message)
            and not (event.data or "").startswith(DIGEST_MORE)
        ):
            await _answer(event, STALE_BUTTON_TEXT, show_alert=True)
            return None
        return await handler(event, data)


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


def region_keyboard(current: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{MARK if region == current else ''}{label}",
                callback_data=f"{S0_REGION}{region}",
            )
        ]
        for region, label in REGION_BUTTONS.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _region_step_text() -> str:
    return "\n".join(
        [
            "<b>Шаг 1 из 3</b> — где искать",
            "«СНГ» — HeadHunter, Хабр Карьера, GeekJob, GetMatch",
            "«Удалёнка по миру» — вакансии на английском, открытые для любой страны",
        ]
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
            "<b>Шаг 2 из 3</b> — специальность",
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
        f"<b>Шаг 3 из 3</b> — вакансии ({title})",
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
            "Пустой выбор + «Продолжить» — убрать направление и вернуться к специальностям.",
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
        "Сначала выбери, где искать, потом специальность и вакансии — можно несколько.",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(subscribed),
    )


async def start_flow(message: Message, db: VacancyDatabase) -> None:
    current = db.get_region(message.from_user.id) if message.from_user else ""
    await message.answer(
        _region_step_text(),
        parse_mode="HTML",
        reply_markup=region_keyboard(current),
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
    region = REGION_BUTTONS[db.get_region(message.from_user.id)]
    await message.answer(
        f"Текущая подписка: <b>{roles_text}</b>\n"
        f"Где ищу: <b>{region}</b>\n"
        f"Изменить — «{BTN_CHOOSE_ROLES_AGAIN}»\n"
        "Отписаться — «Прекратить рассылку»",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(subscribed=True),
    )


def unsubscribe_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Да, отписаться", callback_data=UNSUB_YES)],
            [InlineKeyboardButton(text="Нет, оставить", callback_data=UNSUB_NO)],
        ]
    )


async def unsubscribe_user(message: Message, db: VacancyDatabase) -> None:
    """Сначала спрашиваем: отписка — только по «Да, отписаться»."""
    if not message.from_user:
        return

    if not _is_subscribed(message.from_user.id, db):
        await message.answer(
            "Ты не подписан на рассылку.",
            reply_markup=main_menu_keyboard(subscribed=False),
        )
        return

    roles_text = format_subscription_roles(db.get_subscriber_roles(message.from_user.id))
    await message.answer(
        f"Точно отписаться? Перестану присылать <b>{roles_text}</b>.",
        parse_mode="HTML",
        reply_markup=unsubscribe_confirm_keyboard(),
    )


@router.callback_query(F.data == UNSUB_YES)
async def unsub_yes(callback: CallbackQuery, db: VacancyDatabase) -> None:
    if not callback.from_user or not callback.message:
        return
    await _answer(callback)
    if _is_subscribed(callback.from_user.id, db):
        db.deactivate_subscriber(callback.from_user.id)
    await callback.message.edit_text(
        f"Рассылка остановлена.\nЧтобы вернуться — «{BTN_CHOOSE_ROLES}».",
    )
    await callback.message.answer("Меню 👇", reply_markup=main_menu_keyboard(subscribed=False))


@router.callback_query(F.data == UNSUB_NO)
async def unsub_no(callback: CallbackQuery, db: VacancyDatabase) -> None:
    if not callback.from_user or not callback.message:
        return
    await _answer(callback, "Подписка осталась")
    await callback.message.edit_text("👍 Подписка осталась — завтра в\u00a010:00 пришлю новые вакансии.")


@router.message(Command("start"))
async def cmd_start(message: Message, db: VacancyDatabase) -> None:
    subscribed = _is_subscribed(message.from_user.id, db) if message.from_user else False
    await send_welcome(message, subscribed)
    await start_flow(message, db)


@router.message(F.text.in_({BTN_CHOOSE_ROLES, BTN_CHOOSE_ROLES_AGAIN}))
async def btn_choose_roles(message: Message, db: VacancyDatabase) -> None:
    await start_flow(message, db)


_now_pressed_at: dict[int, float] = {}


@router.message(F.text == BTN_NOW)
async def btn_now(message: Message, db: VacancyDatabase, settings: Settings, bot: Bot) -> None:
    """Свежие вакансии по своим ролям прямо сейчас — из утреннего сбора, HH заново не опрашиваем."""
    if not message.from_user:
        return
    user_id = message.from_user.id
    now = time.monotonic()
    lock = user_lock(user_id)
    if lock.locked() or now - _now_pressed_at.get(user_id, -NOW_COOLDOWN_SEC) < NOW_COOLDOWN_SEC:
        await message.answer("Только что отправил — новые вакансии появятся утром.")
        return
    if _digest_running():
        await message.answer(NOW_TEXTS["digest_running"])
        return
    _now_pressed_at[user_id] = now
    async with lock:
        outcome = await SubscriberService(settings, db, bot).send_now(user_id)
    if outcome in NOW_TEXTS:
        subscribed = outcome != "not_subscribed"
        await message.answer(NOW_TEXTS[outcome], reply_markup=main_menu_keyboard(subscribed))


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

# --- Шаг 1: где искать ---
@router.callback_query(F.data.startswith(S0_REGION))
async def s0_pick_region(callback: CallbackQuery, db: VacancyDatabase) -> None:
    """Регион сохраняется сразу: он общий для всех ролей и нужен даже без подписки."""
    if not callback.data or not callback.from_user or not callback.message:
        return
    region = normalize_region(callback.data[len(S0_REGION):])
    db.set_region(callback.from_user.id, region)
    await _answer(callback, f"Ищу: {REGION_BUTTONS[region]}")
    await _show_specialty_step(callback.message)


@router.callback_query(F.data.startswith(S1_CAT))
async def s1_pick_specialty(callback: CallbackQuery, db: VacancyDatabase) -> None:
    if not callback.data or not callback.message or not callback.from_user:
        return

    category_id = callback.data[len(S1_CAT) :]
    if not get_category(category_id):
        await _answer(callback, "Неизвестная специальность", show_alert=True)
        return

    saved_roles = db.get_subscriber_roles(callback.from_user.id)
    draft = set(_saved_roles_for_category(saved_roles, category_id))

    await _answer(callback)
    await _show_vacancy_step(callback.message, category_id, draft, saved_roles)


# --- Шаг 2: вакансии ---

@router.callback_query(F.data == S2_BACK)
async def s2_back(callback: CallbackQuery) -> None:
    if not callback.message:
        return

    await _answer(callback, "Выбор отменён")
    await _show_specialty_step(callback.message)


@router.callback_query(F.data.startswith(S2_ROLE))
async def s2_toggle_vacancy(callback: CallbackQuery, db: VacancyDatabase) -> None:
    if not callback.data or not callback.message or not callback.from_user:
        return

    category_id, role_id = _parse_role_callback(callback.data)
    if not get_category(category_id):
        await _answer(callback, "Сначала выбери специальность", show_alert=True)
        return
    if role_id not in ROLES:
        await _answer(callback, "Неизвестная роль", show_alert=True)
        return

    draft = _draft_from_keyboard(callback.message.reply_markup)
    if role_id in draft:
        draft.remove(role_id)
    else:
        draft.add(role_id)

    await _answer(callback)

    saved_roles = db.get_subscriber_roles(callback.from_user.id)
    await _show_vacancy_step(callback.message, category_id, draft, saved_roles)


@router.callback_query(F.data.startswith(S2_SAVE))
async def s2_save(callback: CallbackQuery, db: VacancyDatabase) -> None:
    if not callback.data or not callback.from_user or not callback.message:
        return

    category_id = callback.data[len(S2_SAVE) :]
    category = get_category(category_id)
    if not category:
        await _answer(callback, "Сначала выбери направление", show_alert=True)
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

        await _answer(callback)
        await _show_specialty_step(callback.message)
        return

    db.replace_category_roles(
        callback.from_user.id,
        set(category.role_ids),
        draft,
    )
    await _answer(callback, "Подписка сохранена")

    all_roles = db.get_subscriber_roles(callback.from_user.id)
    roles_text = format_success_roles(all_roles)
    region = region_phrase(db.get_region(callback.from_user.id))
    await callback.message.edit_text(
        f"✅ Готово! Каждый день в <b>10:00 (МСК)</b> буду присылать "
        f"<b>{roles_text}</b> {region}.\n\n"
        "Не хочешь ждать утра — нажми «🔎 Вакансии сейчас» внизу.\n"
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


async def _fill_missing_profiles(bot: Bot, db: VacancyDatabase, users: list[dict]) -> None:
    """Имена для тех, кого бот знает только по id, — через getChat.

    Подписчик, который после подписки ничего не нажимает, иначе получит имя
    только со следующей рассылкой, а отписавшийся — никогда. Найденное
    сохраняется, поэтому повторные открытия страницы запросов не делают.
    """
    missing = [user for user in users if not user["first_name"] and not user["username"]]
    if not missing:
        return

    semaphore = asyncio.Semaphore(PROFILE_FETCH_CONCURRENCY)

    async def fetch(user: dict) -> None:
        async with semaphore:
            try:
                chat = await asyncio.wait_for(
                    bot.get_chat(user["user_id"]), PROFILE_FETCH_TIMEOUT_SEC
                )
            except Exception as exc:
                # Не страшно: строка останется с id, список всё равно покажем.
                logger.info("getChat %s не отдал профиль: %s", user["user_id"], exc)
                return

        user.update(
            username=chat.username, first_name=chat.first_name, last_name=chat.last_name
        )
        try:
            db.upsert_user_profile(
                user["user_id"], chat.username, chat.first_name, chat.last_name
            )
        except Exception:
            logger.exception("Не удалось сохранить профиль %s", user["user_id"])

    await asyncio.gather(*(fetch(user) for user in missing))


async def _users_view(
    bot: Bot, db: VacancyDatabase, settings: Settings, page: int
) -> tuple[str, Optional[InlineKeyboardMarkup]]:
    users = db.list_users()
    pages = users_page_count(len(users))
    page = min(max(page, 1), pages)
    start = (page - 1) * USERS_PAGE_SIZE
    # Срез держит те же словари, так что найденные имена попадут и в вывод.
    await _fill_missing_profiles(bot, db, users[start:start + USERS_PAGE_SIZE])
    text = format_users_page(users, page, settings.timezone, settings.telegram_admin_id)
    return text, users_keyboard(page, pages)


@router.message(Command("users"))
async def cmd_users(
    message: Message, db: VacancyDatabase, settings: Settings, bot: Bot
) -> None:
    if not message.from_user:
        return
    if not _is_admin(message.from_user.id, settings):
        await message.answer("Команда только для администратора.")
        return

    text, keyboard = await _users_view(bot, db, settings, page=1)
    await message.answer(
        text, parse_mode="HTML", reply_markup=keyboard, disable_web_page_preview=True
    )


@router.callback_query(F.data.startswith(ADMIN_USERS_PAGE))
async def cb_users_page(
    callback: CallbackQuery, db: VacancyDatabase, settings: Settings, bot: Bot
) -> None:
    if not callback.data or not callback.message or not callback.from_user:
        return
    if not _is_admin(callback.from_user.id, settings):
        await _answer(callback, "Только для администратора", show_alert=True)
        return

    try:
        page = int(callback.data[len(ADMIN_USERS_PAGE):])
    except ValueError:
        page = 1

    await _answer(callback)
    text, keyboard = await _users_view(bot, db, settings, page)
    await callback.message.edit_text(
        text, parse_mode="HTML", reply_markup=keyboard, disable_web_page_preview=True
    )


@router.callback_query(F.data.startswith(DIGEST_MORE))
async def cb_digest_more(
    callback: CallbackQuery, db: VacancyDatabase, settings: Settings, bot: Bot
) -> None:
    """«Показать остальные» под подборкой: остаток — один раз, потом кнопка исчезает.

    Остаток берётся по id нажавшего, а из callback — только дата подборки,
    так что чужую подборку через подделанный callback не получить.
    """
    if not callback.data or not callback.from_user:
        return
    user_id = callback.from_user.id
    day = callback.data[len(DIGEST_MORE):]

    async with user_lock(user_id):
        vacancies = pending_overflow(db, settings, user_id, day)
        if not vacancies:
            db.clear_digest_overflow(user_id, day)
            await _answer(callback, NOTHING_LEFT)
            await _drop_button(callback)
            return

        await _answer(callback)
        await send_overflow(bot, db, user_id, vacancies)
        db.clear_digest_overflow(user_id, day)

    logger.info("Подписчик %s открыл остаток подборки %s: %s вакансий", user_id, day, len(vacancies))
    await _drop_button(callback)


async def _drop_button(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception as exc:
        # Старое сообщение (недоступно боту) или кнопку уже убрали — не страшно.
        logger.info("Кнопку под подборкой не убрать: %s", exc)


@router.callback_query()
async def stale_button(callback: CallbackQuery) -> None:
    """Кнопки прошлых версий бота (другой формат callback_data): ответить, а не молчать."""
    await _answer(callback, STALE_BUTTON_TEXT, show_alert=True)


@router.message()
async def fallback(message: Message, db: VacancyDatabase) -> None:
    subscribed = _is_subscribed(message.from_user.id, db) if message.from_user else False
    await message.answer(
        "Используй кнопки меню 👇",
        reply_markup=main_menu_keyboard(subscribed),
    )


async def _wait_for_telegram(bot: Bot, delays: tuple[float, ...] = STARTUP_RETRY_DELAYS_SEC) -> None:
    """Ждём связь с Телеграмом, а не падаем на старте.

    Исходящая сеть хостинга рвётся раз в 15–30 минут. start_polling первым делом
    зовёт getMe, и в такой момент бот выходил с ошибкой — поднимал его только
    watchdog минут через пять (так было при деплое 24.10.2026). Дальше, во время
    polling, обрывы aiogram переживает сам.
    """
    for attempt, delay in enumerate(delays, start=1):
        try:
            await bot.get_me()
            return
        except TelegramNetworkError as exc:
            logger.warning(
                "Телеграм недоступен на старте (попытка %s), повтор через %s с: %s",
                attempt,
                delay,
                exc,
            )
            await asyncio.sleep(delay)
    await bot.get_me()  # последняя попытка: ошибка уйдёт в лог, дальше — watchdog


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    limit_threads()

    settings = Settings.from_env()
    db = VacancyDatabase(settings.db_path)
    bot = Bot(token=settings.telegram_bot_token)

    _acquire_single_instance()

    dp = Dispatcher()
    dp.update.middleware(InjectMiddleware(db=db, settings=settings))
    dp.update.middleware(TrackActivityMiddleware(db, settings.timezone))
    dp.callback_query.middleware(StaleCallbackMiddleware())
    dp.include_router(router)

    logger.info("Чат-бот подписок запущен (polling)")
    try:
        await _wait_for_telegram(bot)
        await dp.start_polling(bot)
    finally:
        _release_single_instance()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
