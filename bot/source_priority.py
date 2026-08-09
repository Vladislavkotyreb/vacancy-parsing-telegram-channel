from __future__ import annotations

# Меньше число — выше приоритет при дедупе и в выдаче.
SOURCE_PRIORITY: dict[str, int] = {
    "hh.ru": 0,
    "careers": 1,
    "getmatch.ru": 2,
    "geekjob.ru": 3,
}


def source_rank(source: str) -> int:
    return SOURCE_PRIORITY.get(source, 99)
