from __future__ import annotations

from bot.models import Vacancy

SOURCE_LABELS = {
    "hh.ru": "HeadHunter",
    "habr.com": "Habr Career",
    "geekjob.ru": "GeekJob",
    "getmatch.ru": "GetMatch",
    "djinni.co": "Djinni",
    "dou.ua": "DOU",
    "remote-job.ru": "Remote-job.ru",
}


TELEGRAM_MAX_LENGTH = 4096


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


def format_combined_digest(
    new_vacancies: list[Vacancy], total_found: int
) -> tuple[str, int]:
    """Собирает все вакансии в одно сообщение. Возвращает (текст, число включённых)."""
    header = format_digest_header(len(new_vacancies), total_found)
    if not new_vacancies:
        return header, 0

    separator = "\n\n" + "—" * 16 + "\n\n"
    parts = [header]
    included = 0

    for vacancy in new_vacancies:
        block = format_vacancy(vacancy)
        candidate = separator.join(parts + [block])
        omitted = len(new_vacancies) - included - 1
        suffix = (
            f"\n\n… и ещё {omitted} (не влезло в лимит Telegram — {TELEGRAM_MAX_LENGTH} символов)"
            if omitted > 0
            else ""
        )

        if len(candidate + suffix) > TELEGRAM_MAX_LENGTH:
            break

        parts.append(block)
        included += 1

    message = separator.join(parts)
    omitted = len(new_vacancies) - included
    if omitted:
        message += (
            f"\n\n… и ещё {omitted} (не влезло в лимит Telegram — {TELEGRAM_MAX_LENGTH} символов)"
        )

    return message, included


def escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
