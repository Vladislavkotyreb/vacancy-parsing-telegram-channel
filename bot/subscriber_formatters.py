from __future__ import annotations

from bot.models import Vacancy
from bot.formatters import (
    build_paginated_digest,
    escape_html,
)

SOURCE_LABELS = {
    "hh.ru": "HeadHunter",
    "habr.com": "Habr Career",
    "geekjob.ru": "GeekJob",
    "getmatch.ru": "GetMatch",
}


def format_subscriber_header(
    role_label: str, new_count: int, total_found: int, max_age_hours: int = 72
) -> str:
    if new_count == 0:
        return (
            f"📭 <b>Новых вакансий {escape_html(role_label)} нет</b>\n"
            f"Найдено всего: {total_found}\n"
            f"Учитываются только вакансии за последние {max_age_hours} ч"
        )
    return (
        f"✨ <b>{new_count} новых вакансий</b> {escape_html(role_label)} "
        f"(за последние {max_age_hours} ч)\n"
        f"Источники: {', '.join(SOURCE_LABELS.values())}"
    )


def format_subscriber_digest(
    role_label: str,
    new_vacancies: list[Vacancy],
    total_found: int,
    max_age_hours: int = 72,
) -> tuple[list[str], int]:
    if not new_vacancies:
        return [format_subscriber_header(role_label, 0, total_found, max_age_hours)], 0

    return build_paginated_digest(
        format_subscriber_header(role_label, len(new_vacancies), total_found, max_age_hours),
        new_vacancies,
        channel_footer=False,
    )
