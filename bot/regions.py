"""Где искать вакансии: СНГ, удалёнка по миру или оба.

Регион хранится отдельно от ролей (`user_region`): человек выбирает его первым
шагом /start, ещё до подписки. Кто не выбирал — СНГ, так что подписчики,
пришедшие до 24.10.2026, получают ровно то же, что и раньше.
"""

from __future__ import annotations

from typing import Iterable

from bot.models import Vacancy
from bot.parsers.world_remote import WORLD_SOURCES

CIS = "cis"
WORLD = "world"
BOTH = "both"
DEFAULT_REGION = CIS

# Порядок — как в клавиатуре.
REGION_BUTTONS = {
    CIS: "СНГ",
    WORLD: "Удалёнка по миру",
    BOTH: "СНГ + удалёнка по миру",
}

# «Каждый день присылаю новые вакансии … {фраза}»
_PHRASES = {
    CIS: "по СНГ",
    WORLD: "на удалёнку по миру",
    BOTH: "по СНГ и на удалёнку по миру",
}


def normalize_region(region: str) -> str:
    return region if region in REGION_BUTTONS else DEFAULT_REGION


def region_phrase(region: str) -> str:
    return _PHRASES[normalize_region(region)]


def wants_source(region: str, source: str) -> bool:
    region = normalize_region(region)
    if region == BOTH:
        return True
    is_world = source in WORLD_SOURCES
    return is_world if region == WORLD else not is_world


def for_region(vacancies: Iterable[Vacancy], region: str) -> list[Vacancy]:
    return [v for v in vacancies if wants_source(region, v.source)]
