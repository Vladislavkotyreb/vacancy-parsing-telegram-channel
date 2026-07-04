from __future__ import annotations

from typing import Optional

from bot.database import VacancyDatabase
from bot.formatters import escape_html
from bot.roles import ROLES


def _role_label(role_id: str) -> str:
    role = ROLES.get(role_id)
    return role.button_label if role else role_id


def _period_title(days: Optional[int]) -> str:
    if days is None:
        return "за всё время"
    return f"за {days} дн."


def format_admin_stats(
    db: VacancyDatabase, timezone_name: str, days: Optional[int] = None
) -> str:
    period_label = _period_title(days)
    active = db.count_active_subscribers()
    role_counts = db.subscriber_role_counts()
    delivery = db.subscriber_delivery_stats(timezone_name, days=days)
    sent_by_role = db.subscriber_sent_by_role(timezone_name, days=days)
    channel = db.channel_post_stats(timezone_name, days=days)

    reach_pct = 0
    if active > 0:
        reach_pct = round(delivery["users_period"] / active * 100)

    lines = [
        f"📊 <b>Статистика {period_label}</b>",
        "",
        "<b>Подписчики</b>",
        f"• Активных: <b>{active}</b>",
    ]

    if role_counts:
        lines.append("• Выбранные роли:")
        for role_id, count in role_counts:
            lines.append(f"  — {escape_html(_role_label(role_id))}: {count}")
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

    if sent_by_role:
        role_period = "всего" if days is None else "за период"
        lines.append(f"• По ролям ({role_period}):")
        for role_id, count in sent_by_role:
            lines.append(f"  — {escape_html(_role_label(role_id))}: {count}")

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
            "<i>Просмотры постов канала — только в Telegram → Статистика канала.</i>",
        ]
    )

    return "\n".join(lines)
