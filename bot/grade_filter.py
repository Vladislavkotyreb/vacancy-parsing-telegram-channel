"""Фильтр подборки по уровню (грейду), который выбрал подписчик.

Главное правило: вакансия с неизвестным уровнем приходит всем. У GetMatch и
GeekJob уровня нет вовсе, у Хабра — у трети вакансий; если такие отсекать,
подписчик молча потеряет большую часть подборки. Фильтр убирает только то,
что явно не подходит: стажёрскую вакансию для Senior и т. п.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

from bot.grades import extract_grade
from bot.models import Vacancy

LEVELS = ("junior", "middle", "senior", "lead")
LEVEL_LABELS = {
    "junior": "Junior / стажёр",
    "middle": "Middle",
    "senior": "Senior",
    "lead": "Lead / Head",
}

_GRADE_TO_LEVEL = {
    "Стажёр": "junior",
    "Junior": "junior",
    "Middle": "middle",
    "Senior": "senior",
    "Lead": "lead",
    "Head": "lead",
    "Principal": "lead",
    "Staff": "lead",
}

# Русские названия, которых нет в bot/grades.py. Туда их не добавляем: тот
# модуль подписывает грейд и в постах канала, а канал без просьбы не трогаем.
_EXTRA_TITLE_LEVELS = (
    (re.compile(r"тимлид|техлид|руководител|главн\w*\s+(?:разработ|инженер|дизайн|аналит|программист)", re.I), "lead"),
    (re.compile(r"\bведущ", re.I), "senior"),
    (re.compile(r"стажир|без\s+опыта", re.I), "junior"),
)

# «1–3 года» пишут и для джунов, и для мидлов — поэтому диапазоны.
_HH_EXPERIENCE_LEVELS = {
    "noExperience": frozenset({"junior"}),
    "between1And3": frozenset({"junior", "middle"}),
    "between3And6": frozenset({"middle", "senior"}),
    "moreThan6": frozenset({"senior", "lead"}),
}


def normalize_levels(levels: Iterable[str]) -> list[str]:
    """Известные уровни в порядке LEVELS; все четыре — то же, что «любой»."""
    chosen = [level for level in LEVELS if level in set(levels)]
    return [] if len(chosen) == len(LEVELS) else chosen


def vacancy_levels(vacancy: Vacancy) -> Optional[frozenset]:
    """Уровни, которым подходит вакансия; None — неизвестно."""
    title_grade = extract_grade(vacancy.title)
    if title_grade in _GRADE_TO_LEVEL:
        return frozenset({_GRADE_TO_LEVEL[title_grade]})
    for pattern, level in _EXTRA_TITLE_LEVELS:
        if pattern.search(vacancy.title):
            return frozenset({level})
    if vacancy.experience in _HH_EXPERIENCE_LEVELS:
        return _HH_EXPERIENCE_LEVELS[vacancy.experience]
    if vacancy.grade in _GRADE_TO_LEVEL:  # Хабр: квалификация из карточки
        return frozenset({_GRADE_TO_LEVEL[vacancy.grade]})
    return None


def filter_by_levels(vacancies: list[Vacancy], levels: Iterable[str]) -> list[Vacancy]:
    wanted = set(normalize_levels(levels))
    if not wanted:
        return vacancies
    result = []
    for vacancy in vacancies:
        known = vacancy_levels(vacancy)
        if known is None or known & wanted:
            result.append(vacancy)
    return result


def levels_phrase(levels: Iterable[str]) -> str:
    chosen = normalize_levels(levels)
    return ", ".join(LEVEL_LABELS[level] for level in chosen) if chosen else "все уровни"
