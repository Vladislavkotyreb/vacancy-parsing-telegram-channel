from __future__ import annotations

from typing import Optional

from bot.models import Vacancy
from bot.regions import CIS, DEFAULT_REGION, WORLD, normalize_region
from bot.roles import get_role
from bot.formatters import (
    build_paginated_digest,
    escape_html,
)

# Площадки, которые опрашивает сбор подписок. Сайт Сбера («Карьера (бигтех)»)
# убран: он ничего не находил, вакансии Сбера приходят с HH.
SOURCE_LABELS = {
    "hh.ru": "HeadHunter",
    "career.habr.com": "Хабр Карьера",
    "geekjob.ru": "GeekJob",
    "getmatch.ru": "GetMatch",
}
WORLD_SOURCE_LABELS = {
    "himalayas.app": "Himalayas",
    "weworkremotely.com": "We Work Remotely",
    "jobicy.com": "Jobicy",
}


def _sources_line(region: str) -> str:
    labels = {
        CIS: SOURCE_LABELS,
        WORLD: WORLD_SOURCE_LABELS,
    }.get(normalize_region(region), {**SOURCE_LABELS, **WORLD_SOURCE_LABELS})
    return f"Источники: {', '.join(labels.values())}"


def format_subscriber_header(
    role_label: str,
    new_count: int,
    total_found: int,
    max_age_hours: int = 72,
    total_new: Optional[int] = None,
    region: str = DEFAULT_REGION,
) -> str:
    header = (
        f"✨ <b>{new_count} новых вакансий</b> {escape_html(role_label)} "
        f"(за последние {max_age_hours} ч)\n"
        f"{_sources_line(region)}"
    )
    if total_new is not None and total_new > new_count:
        # Остальные придут в следующие дни, если не устареют, — но это не
        # гарантировано, поэтому ничего не обещаем, только называем число.
        header += f"\nПоказаны {new_count} самых свежих из {total_new}"
    return header


def format_subscriber_digest(
    role_label: str,
    new_vacancies: list[Vacancy],
    total_found: int,
    max_age_hours: int = 72,
    total_new: Optional[int] = None,
    region: str = DEFAULT_REGION,
) -> tuple[list[str], int]:
    if not new_vacancies:
        return [], 0

    return build_paginated_digest(
        format_subscriber_header(
            role_label, len(new_vacancies), total_found, max_age_hours, total_new, region
        ),
        new_vacancies,
        channel_footer=False,
    )


def format_empty_notice(role_ids: list[str], already_sent: bool = False, max_age_hours: int = 72) -> str:
    """«Новых вакансий нет»: важное — в заголовке, ниже — почему и что дальше.

    Для нескольких ролей — «по выбранным ролям», а не перечисление в скобках.
    «Найдено всего» не пишем: рядом с «новых нет» эта цифра только путает.

    already_sent — свежие вакансии были, но человек их уже получил. Давние
    подписчики видят так почти всё, и голое «нет» читалось как «бот сломался»
    (26.10.2026: 14 из 25 давних подписчиков получили «нет»).
    """
    role = get_role(role_ids[0]) if len(role_ids) == 1 else None
    label = role.label if role else "по выбранным ролям"
    period = _period_phrase(max_age_hours)
    reason = f"Все свежие {period} вы уже получили" if already_sent else f"{period[0].upper()}{period[1:]} новых не появилось"
    return (
        f"📭 <b>Новых вакансий {escape_html(label)} сегодня нет</b>\n"
        f"{reason}. Завтра в\u00a010:00 проверю снова"
    )


def _period_phrase(hours: int) -> str:
    """72 → «за 3 дня», 24 → «за сутки», 36 → «за 36 ч»."""
    if hours == 24:
        return "за сутки"
    if hours % 24 == 0:
        days = hours // 24
        word = "день" if days % 10 == 1 and days % 100 != 11 else (
            "дня" if days % 10 in (2, 3, 4) and days % 100 not in (12, 13, 14) else "дней")
        return f"за {days} {word}"
    return f"за {hours} ч"
