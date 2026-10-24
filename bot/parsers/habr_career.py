"""Хабр Карьера: вся свежая лента IT-вакансий, от новых к старым.

Открытый JSON без ключа. Больше 50 вакансий за запрос сайт не отдаёт; за
72 часа набирается ~700 вакансий — около 14 страниц. Нужен только подпискам:
роли отбирают свои вакансии по названию, как в GeekJob и GetMatch.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Optional

import aiohttp

from bot.dates import ensure_aware, parse_iso_datetime, utc_now
from bot.grades import extract_grade
from bot.models import Vacancy

logger = logging.getLogger(__name__)

BASE_URL = "https://career.habr.com"
API_URL = f"{BASE_URL}/api/frontend/vacancies"
SOURCE = "career.habr.com"
PER_PAGE = 50  # больше сайт не отдаёт
MAX_PAGES = 30  # ~1500 вакансий: с запасом на 72 часа
PAGE_PAUSE_SEC = 0.3

# Квалификация Хабра → грейд, как его показывает дайджест.
_GRADES = {
    "intern": "Стажёр",
    "junior": "Junior",
    "middle": "Middle",
    "senior": "Senior",
    "lead": "Lead",
}


def parse_item(item: dict[str, Any]) -> Optional[Vacancy]:
    title = " ".join(str(item.get("title") or "").split())
    vacancy_id = item.get("id")
    if not title or not vacancy_id or item.get("archived") or item.get("hidden"):
        return None

    company = (item.get("company") or {}).get("title") or "—"
    salary = (item.get("salary") or {}).get("formatted") or None
    remote = bool(item.get("remoteWork"))
    cities = [loc.get("title") for loc in item.get("locations") or [] if loc.get("title")]
    location = ", ".join(cities) or ("Удалённо" if remote else None)
    published = (item.get("publishedDate") or {}).get("date")
    qualification = str(item.get("qualification") or "").lower()

    return Vacancy(
        source=SOURCE,
        external_id=str(vacancy_id),
        title=title,
        company=company,
        url=BASE_URL + (item.get("href") or f"/vacancies/{vacancy_id}"),
        salary=salary,
        location=location,
        published_at=parse_iso_datetime(published) if published else None,
        work_format="Удалённо" if remote else None,
        grade=extract_grade(title) or _GRADES.get(qualification),
    )


async def fetch_recent(max_age_hours: int, timeout: aiohttp.ClientTimeout) -> list[Vacancy]:
    """Лента за max_age_hours: листаем, пока последняя вакансия страницы не старше."""
    cutoff = utc_now() - timedelta(hours=max_age_hours)
    results: dict[str, Vacancy] = {}
    headers = {"Accept": "application/json", "User-Agent": "ProductDesignerVacancyBot/1.0"}

    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
        for page in range(1, MAX_PAGES + 1):
            params = {"type": "all", "sort": "date", "page": page, "per_page": PER_PAGE}
            async with session.get(API_URL, params=params) as resp:
                if resp.status != 200:
                    logger.warning("Хабр Карьера: HTTP %s на странице %s", resp.status, page)
                    break
                data = await resp.json()

            items = data.get("list") or []
            if not items:
                break
            page_dates = []
            for item in items:
                vacancy = parse_item(item)
                if vacancy is None:
                    continue
                results[vacancy.uid] = vacancy
                if vacancy.published_at:
                    page_dates.append(ensure_aware(vacancy.published_at))

            # Стоп, когда свежих на странице не осталось. Не «хоть одна старая»:
            # закреплённое старое объявление на первой странице оборвало бы сбор.
            if page_dates and max(page_dates) < cutoff:
                break
            await asyncio.sleep(PAGE_PAUSE_SEC)

    return list(results.values())
