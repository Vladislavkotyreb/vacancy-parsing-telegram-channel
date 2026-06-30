from __future__ import annotations

from bot.grades import extract_grade
from bot.models import Vacancy

SOURCE_LABELS = {
    "hh.ru": "HeadHunter",
    "habr.com": "Habr Career",
    "geekjob.ru": "GeekJob",
    "getmatch.ru": "GetMatch",
}

TELEGRAM_MAX_LENGTH = 4096
SEPARATOR = "\n\n" + "—" * 16 + "\n\n"
CHANNEL_FOOTER = "\n\n" + "—" * 9 + "\n" + '<a href="https://t.me/prdsvac">Product design vacancies daily</a>'


def format_vacancy(vacancy: Vacancy) -> str:
    source = SOURCE_LABELS.get(vacancy.source, vacancy.source)
    lines = [
        f"🎨 <b>{escape_html(vacancy.title)}</b>",
    ]

    if grade := extract_grade(vacancy.title):
        lines.append(f"📊 {escape_html(grade)}")

    lines.extend([
        f"🏢 {escape_html(vacancy.company)}",
    ])

    if vacancy.salary:
        lines.append(f"💰 {escape_html(vacancy.salary)}")

    location = vacancy.location or vacancy.work_format
    if location:
        lines.append(f"📍 {escape_html(location)}")

    lines.append(f"🔗 {source}")
    lines.append(f'<a href="{escape_html(vacancy.url)}">Открыть вакансию</a>')

    return "\n".join(lines)


def format_digest_header(new_count: int, total_found: int, max_age_hours: int = 72) -> str:
    if new_count == 0:
        return (
            "📭 <b>Новых вакансий продуктового дизайнера нет</b>\n"
            f"Проверено площадок: {len(SOURCE_LABELS)} · найдено всего: {total_found}\n"
            f"Учитываются только вакансии за последние {max_age_hours} ч"
        )
    return (
        f"✨ <b>{new_count} новых вакансий</b> продуктового дизайнера "
        f"(за последние {max_age_hours} ч)\n"
        f"Источники: {', '.join(SOURCE_LABELS.values())}"
    )


def format_continuation_header(part: int, total_parts: int) -> str:
    return f"✨ <b>Продолжение</b> ({part}/{total_parts})"


def build_paginated_digest(
    header: str,
    new_vacancies: list[Vacancy],
    *,
    channel_footer: bool = False,
) -> tuple[list[str], int]:
    """Собирает вакансии в одно или несколько сообщений. Возвращает (тексты, число включённых)."""
    if not new_vacancies:
        return [header], 0

    messages: list[str] = []
    parts = [header]
    included = 0

    for vacancy in new_vacancies:
        block = format_vacancy(vacancy)
        if len(SEPARATOR.join(parts + [block])) <= TELEGRAM_MAX_LENGTH:
            parts.append(block)
            included += 1
            continue

        if parts:
            messages.append(SEPARATOR.join(parts))

        parts = [block]
        if len(parts[0]) > TELEGRAM_MAX_LENGTH:
            parts = [parts[0][: TELEGRAM_MAX_LENGTH - 1] + "…"]
        included += 1

    if parts:
        messages.append(SEPARATOR.join(parts))

    if len(messages) > 1:
        total_parts = len(messages)
        messages[1:] = [
            format_continuation_header(index, total_parts) + SEPARATOR + message
            for index, message in enumerate(messages[1:], start=2)
        ]

    if messages and channel_footer:
        messages[-1] += CHANNEL_FOOTER

    return messages, included


def format_combined_digest(
    new_vacancies: list[Vacancy], total_found: int, max_age_hours: int = 72
) -> tuple[list[str], int]:
    if not new_vacancies:
        return [format_digest_header(0, total_found, max_age_hours)], 0

    return build_paginated_digest(
        format_digest_header(len(new_vacancies), total_found, max_age_hours),
        new_vacancies,
        channel_footer=True,
    )


def escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
