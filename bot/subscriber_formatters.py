from __future__ import annotations

from typing import Optional

from bot.models import Vacancy
from bot.regions import CIS, DEFAULT_REGION, WORLD, normalize_region
from bot.roles import get_role
from bot.formatters import (
    TELEGRAM_MAX_LENGTH,
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


# Метка в ссылке t.me/<бот>?start=share: так /stats видит, сколько людей
# пришло по пересланной подборке. Ссылка в тексте переживает и пересылку, и копирование.
SHARE_START = "share"


def _share_footer(share_url: str) -> str:
    return f'\n\n👥 Коллегам тоже пригодится: <a href="{escape_html(share_url)}">подписаться на подборку</a>'


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
    share_url: Optional[str] = None,
) -> tuple[list[str], int]:
    if not new_vacancies:
        return [], 0

    messages, included = build_paginated_digest(
        format_subscriber_header(
            role_label, len(new_vacancies), total_found, max_age_hours, total_new, region
        ),
        new_vacancies,
        channel_footer=False,
    )
    if share_url:
        footer = _share_footer(share_url)
        # Не влезает в последнее сообщение — без строки: она не стоит лишнего сообщения.
        if len(messages[-1]) + len(footer) <= TELEGRAM_MAX_LENGTH:
            messages[-1] += footer
    return messages, included


def format_empty_notice(role_ids: list[str]) -> str:
    """«Новых вакансий нет»: важное — в заголовке, ниже — что будет дальше.

    Для нескольких ролей — «по выбранным ролям», а не перечисление в скобках.
    «Найдено всего» не пишем: рядом с «новых нет» эта цифра только путает.
    """
    role = get_role(role_ids[0]) if len(role_ids) == 1 else None
    label = role.label if role else "по выбранным ролям"
    return f"📭 <b>Новых вакансий {escape_html(label)} нет</b>\nЗавтра в\u00a010:00 проверю снова"
