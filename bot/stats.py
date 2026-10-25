from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]

from bot.database import VacancyDatabase
from bot.formatters import escape_html
from bot.roles import ROLES
from bot.russian import format_subscription_roles

USERS_PAGE_SIZE = 20
TELEGRAM_MAX_LENGTH = 4096


# Роли первой версии бота: в меню их нет, а подписчики на них остались. Без
# пометки в /stats они путаются с одноимёнными разделами меню.
LEGACY_ROLE_LABELS = {
    "frontend": "Frontend (старая роль, весь фронтенд)",
    "backend": "Backend (старая роль, весь бэкенд)",
}


def _role_label(role_id: str) -> str:
    if role_id in LEGACY_ROLE_LABELS:
        return LEGACY_ROLE_LABELS[role_id]
    role = ROLES.get(role_id)
    return role.button_label if role else role_id


def _period_title(days: Optional[int]) -> str:
    if days is None:
        return "за всё время"
    return f"за {days} дн."


def format_admin_stats(
    db: VacancyDatabase,
    timezone_name: str,
    days: Optional[int] = None,
    exclude_user_id: Optional[int] = None,
) -> str:
    period_label = _period_title(days)
    audience = db.audience_stats(timezone_name, exclude_user_id=exclude_user_id)
    active = db.count_active_subscribers(exclude_user_id=exclude_user_id)
    roles = db.subscriber_role_summary(timezone_name, days=days, exclude_user_id=exclude_user_id)
    delivery = db.subscriber_delivery_stats(
        timezone_name, days=days, exclude_user_id=exclude_user_id
    )
    channel = db.channel_post_stats(timezone_name, days=days)

    reach_pct = 0
    if active > 0:
        reach_pct = round(delivery["users_period"] / active * 100)

    came, came_subscribed = db.came_from_stats("share", exclude_user_id=exclude_user_id)

    lines = [
        f"📊 <b>Статистика {period_label}</b>",
        "",
        *_audience_lines(audience, f"• Пришли по ссылке из подборки: {came}, из них подписаны {came_subscribed}"),
        "",
        "<b>Подписчики</b>",
        f"• Активных: <b>{active}</b>",
    ]

    if roles:
        received = "получали вакансии" if days is None else f"получали за {days} дн."
        lines.append(f"• По ролям (подписаны · {received}):")
        for role_id, subscribed, reached in roles:
            lines.append(f"  — {escape_html(_role_label(role_id))}: {subscribed} · {reached}")
    else:
        lines.append("• Роли не выбраны")

    lines.extend(
        [
            "",
            "<b>Рассылка в бот</b>",
            f"• Вакансий отправлено: <b>{delivery['sent_period']}</b>",
            f"• Получили хотя бы 1 вакансию: <b>{delivery['users_period']}</b> из {active} ({reach_pct}%)",
            f"• Сегодня: {delivery['sent_today']} вакансий → {delivery['users_today']} чел.",
        ]
    )


    posted_label = "всего" if days is None else f"за {days} дн."
    lines.extend(
        [
            "",
            "<b>Канал @prdsvac</b>",
            f"• Всего вакансий в базе: <b>{channel['total_known']}</b>",
            f"• Опубликовано {posted_label}: <b>{channel['posted_period']}</b>",
            f"• Сегодня в канал: <b>{channel['posted_today']}</b>",
        ]
    )

    last_run = channel.get("last_run")
    if last_run:
        lines.append(
            f"• Последний fetch: {last_run['started_at']} "
            f"(найдено {last_run['found_total']}, новых {last_run['posted_new']}, {last_run['status']})"
        )

    lines.extend(
        [
            "",
            "<i>Админ в подсчётах не учитывается. Просмотры постов канала — только в "
            "Telegram → Статистика канала.</i>",
        ]
    )

    return "\n".join(lines)


def _audience_lines(audience: dict, *extra: str) -> list[str]:
    """Строки «Аудитории»; extra — дополнительные пункты перед сноской."""
    dau, mau = audience["dau"], audience["mau"]
    stickiness = f"{round(dau / mau * 100)}%" if mau else "—"

    lines = [
        "<b>Аудитория</b>",
        f"• Активные сегодня (DAU): <b>{dau}</b>",
        f"• Активные за 30 дней (MAU): <b>{mau}</b> · DAU/MAU {stickiness}",
        f"• Получили дайджест: сегодня <b>{audience['reach_today']}</b>"
        f" · за 30 дней <b>{audience['reach_month']}</b>",
        f"• Новые подписки: сегодня {audience['new_today']}"
        f" · за 7 дн. {audience['new_week']} · за 30 дн. {audience['new_month']}",
        f"• Отписались: за 7 дн. {audience['left_week']}"
        f" · за 30 дн. {audience['left_month']}"
        f" (из них заблокировали бота: {audience['blocked_month']})",
    ]

    lines.extend(extra)

    since = audience["tracking_since"]
    if since:
        lines.append(
            f"<i>Активные — те, кто что-то делал в боте; учёт ведётся с "
            f"{_format_day(since)}. Получившие дайджест — с начала рассылок.</i>"
        )
    else:
        lines.append(
            "<i>Активность ещё не записана: счёт DAU/MAU начнётся с первых "
            "действий в боте после обновления.</i>"
        )
    return lines


def _format_day(day_iso: str) -> str:
    year, month, day = day_iso.split("-")
    return f"{day}.{month}.{year}"


def _local_date(iso_utc: Optional[str], tz: ZoneInfo):
    if not iso_utc:
        return None
    return datetime.fromisoformat(iso_utc).astimezone(tz).date()


def _format_when(iso_utc: Optional[str], tz: ZoneInfo, today) -> Optional[str]:
    day = _local_date(iso_utc, tz)
    if day is None:
        return None
    if day == today:
        return "сегодня"
    if day == today - timedelta(days=1):
        return "вчера"
    return day.strftime("%d.%m.%Y")


def _user_name(user: dict) -> str:
    name = " ".join(part for part in (user["first_name"], user["last_name"]) if part)
    return name[:40] if name else "Без имени"


def _user_status(user: dict, tz: ZoneInfo, today) -> str:
    if user["active"] is None:
        return "не подписан"
    if user["active"]:
        roles = format_subscription_roles(user["roles"]) if user["roles"] else "без ролей"
        since = _format_when(user["subscribed_at"], tz, today)
        return f"{escape_html(roles)} · с {since}" if since else escape_html(roles)

    verb = "заблокировал бота" if user["unsubscribe_reason"] == "blocked" else "отписался"
    when = _format_when(user["unsubscribed_at"], tz, today)
    return f"{verb} {when}" if when else verb


def users_page_count(total: int, page_size: int = USERS_PAGE_SIZE) -> int:
    return max(1, math.ceil(total / page_size))


def format_users_page(
    users: list[dict],
    page: int,
    timezone_name: str,
    admin_id: Optional[int] = None,
    page_size: int = USERS_PAGE_SIZE,
) -> str:
    """Страница списка пользователей для админа. page — с единицы."""
    tz = ZoneInfo(timezone_name)
    today = datetime.now(tz).date()
    pages = users_page_count(len(users), page_size)
    page = min(max(page, 1), pages)
    subscribed = sum(1 for user in users if user["active"])

    header = f"👥 <b>Пользователи</b>: {len(users)} · подписаны {subscribed}"
    if pages > 1:
        header += f"\nСтраница {page} из {pages}"
    if not users:
        return header + "\n\nПока никого — бот ещё не записал ни одного действия."

    lines = [header, ""]
    start = (page - 1) * page_size
    for number, user in enumerate(users[start:start + page_size], start=start + 1):
        name = escape_html(_user_name(user))
        # Ссылку tg://user Телеграм молча убирает, если у человека закрыта
        # пересылка сообщений. @username кликабелен всегда, а id в <code>
        # копируется по тапу и не принимается клиентом за номер телефона.
        title = f'{number}. <a href="tg://user?id={user["user_id"]}">{name}</a>'
        if user["username"]:
            title += f" @{escape_html(user['username'])}"
        if admin_id is not None and user["user_id"] == admin_id:
            title += " (вы)"
        title += f" · <code>{user['user_id']}</code>"

        details = _user_status(user, tz, today)
        seen = _format_when(user["last_seen_at"], tz, today)
        if seen:
            details += f" · был {seen}"

        lines.append(title)
        lines.append(f"    {details}")

    text = "\n".join(lines)
    if len(text) > TELEGRAM_MAX_LENGTH:
        text = text[: TELEGRAM_MAX_LENGTH - 1] + "…"
    return text
