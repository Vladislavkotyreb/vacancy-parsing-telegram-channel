from __future__ import annotations

from typing import Optional

from bot.models import Vacancy
from bot.roles import get_role
from bot.formatters import (
    build_paginated_digest,
    escape_html,
)

SOURCE_LABELS = {
    "hh.ru": "HeadHunter",
    "careers": "Карьера (бигтех)",
    "geekjob.ru": "GeekJob",
    "getmatch.ru": "GetMatch",
}


def format_subscriber_header(
    role_label: str,
    new_count: int,
    total_found: int,
    max_age_hours: int = 72,
    total_new: Optional[int] = None,
) -> str:
    header = (
        f"✨ <b>{new_count} новых вакансий</b> {escape_html(role_label)} "
        f"(за последние {max_age_hours} ч)\n"
        f"Источники: {', '.join(SOURCE_LABELS.values())}"
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
) -> tuple[list[str], int]:
    if not new_vacancies:
        return [], 0

    return build_paginated_digest(
        format_subscriber_header(
            role_label, len(new_vacancies), total_found, max_age_hours, total_new
        ),
        new_vacancies,
        channel_footer=False,
    )


def format_empty_notice(role_ids: list[str]) -> str:
    """«Новых вакансий нет»: важное — в заголовке, ниже — что будет дальше.

    Для нескольких ролей — «по выбранным ролям», а не перечисление в скобках.
    «Найдено всего» не пишем: рядом с «новых нет» эта цифра только путает.
    """
    role = get_role(role_ids[0]) if len(role_ids) == 1 else None
    label = role.label if role else "по выбранным ролям"
    return f"📭 <b>Новых вакансий {escape_html(label)} нет</b>\nЗавтра в\u00a010:00 проверю снова"
