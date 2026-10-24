from __future__ import annotations

# Меньше число — выше приоритет при дедупе и в выдаче.
SOURCE_PRIORITY: dict[str, int] = {
    "hh.ru": 0,
    "careers": 1,
    "career.habr.com": 1,  # только подписки; у канала таких вакансий нет
    "getmatch.ru": 2,
    "geekjob.ru": 3,
    # Удалёнка по миру — только подписки.
    "himalayas.app": 4,
    "weworkremotely.com": 4,
    "jobicy.com": 4,
}


def source_rank(source: str) -> int:
    return SOURCE_PRIORITY.get(source, 99)
