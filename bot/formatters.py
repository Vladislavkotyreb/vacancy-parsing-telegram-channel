from __future__ import annotations

from bot.models import Vacancy

SOURCE_LABELS = {
    "hh.ru": "HeadHunter",
    "habr.com": "Habr Career",
    "geekjob.ru": "GeekJob",
    "getmatch.ru": "GetMatch",
    "remote-job.ru": "Remote-job.ru",
}

TELEGRAM_MAX_LENGTH = 4096
SEPARATOR = "\n\n" + "—" * 16 + "\n\n"


def format_vacancy(vacancy: Vacancy) -> str:
    source = SOURCE_LABELS.get(vacancy.source, vacancy.source)
    lines = [
        f"🎨 <b>{escape_html(vacancy.title)}</b>",
        f"🏢 {escape_html(vacancy.company)}",
    ]

    if vacancy.salary:
        lines.append(f"💰 {escape_html(vacancy.salary)}")

    location = vacancy.location or vacancy.work_format
    if location:
        lines.append(f"📍 {escape_html(location)}")

    lines.append(f"🔗 {source}")
    lines.append(f'<a href="{vacancy.url}">Открыть вакансию</a>')

    return "\n".join(lines)


def format_digest_header(new_count: int, total_found: int) -> str:
    if new_count == 0:
        return (
            "📭 <b>Новых вакансий продуктового дизайнера нет</b>\n"
            f"Проверено площадок: {len(SOURCE_LABELS)} · найдено всего: {total_found}"
        )
    return (
        f"✨ <b>{new_count} новых вакансий</b> продуктового дизайнера\n"
        f"Источники: {', '.join(SOURCE_LABELS.values())}"
    )


def format_continuation_header(part: int, total_parts: int) -> str:
    return f"✨ <b>Продолжение</b> ({part}/{total_parts})"


def format_combined_digest(
    new_vacancies: list[Vacancy], total_found: int
) -> tuple[list[str], int]:
    """Собирает вакансии в одно или несколько сообщений. Возвращает (тексты, число включённых)."""
    if not new_vacancies:
        return [format_digest_header(0, total_found)], 0

    messages: list[str] = []
    parts = [format_digest_header(len(new_vacancies), total_found)]
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

    return messages, included


def escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
