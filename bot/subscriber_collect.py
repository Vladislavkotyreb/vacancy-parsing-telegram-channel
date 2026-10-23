from __future__ import annotations

import logging

import aiohttp

from bot.config import Settings
from bot.dates import dedupe_by_title_company
from bot.models import Vacancy
from bot.parsers.bigtech import BigTechCareersParser
from bot.parsers.geekjob import GeekJobParser
from bot.parsers.getmatch import GetMatchParser
from bot.parsers.hh import HHParser
from bot.roles import Role

logger = logging.getLogger(__name__)

GETMATCH_API_URL = "https://getmatch.ru/api/offers"


class SourceLimited(Exception):
    """Площадка ограничила запросы (HTTP 403): собранное неполное, но годное.

    Несёт то, что успело собраться, — подписчики получат хотя бы это, а админ
    узнает, что роль собрана не целиком.
    """

    def __init__(self, source: str, vacancies: list[Vacancy]) -> None:
        super().__init__(f"{source}: доступ ограничен (HTTP 403)")
        self.source = source
        self.vacancies = vacancies


async def collect_for_role(settings: Settings, role: Role) -> list[Vacancy]:
    results: dict[str, Vacancy] = {}
    hh_vacancies, hh_limited = await _fetch_hh(settings, role)

    for source, vacancies in [
        ("hh.ru", hh_vacancies),
        ("careers", await _fetch_careers(settings, role)),
        ("geekjob.ru", await _fetch_geekjob(role)),
    ]:
        logger.info("Подписчики [%s] %s: найдено %s", role.id, source, len(vacancies))
        for vacancy in vacancies:
            if role.matcher(vacancy.title):
                results[vacancy.uid] = vacancy

    if role.uses_getmatch:
        getmatch_vacancies = await _fetch_getmatch(role)
        logger.info("Подписчики [%s] getmatch.ru: найдено %s", role.id, len(getmatch_vacancies))
        for vacancy in getmatch_vacancies:
            if role.matcher(vacancy.title):
                results[vacancy.uid] = vacancy

    collected = dedupe_by_title_company(list(results.values()))
    if hh_limited:
        raise SourceLimited("hh.ru", collected)
    return collected


async def _fetch_getmatch(role: Role) -> list[Vacancy]:
    """GetMatch для подписчиков: без фильтра product designer из канального парсера."""
    parser = GetMatchParser()
    results: dict[str, Vacancy] = {}
    offset = 0
    limit = 50
    headers = {"Accept": "application/json", "User-Agent": "ProductDesignerVacancyBot/1.0"}

    async with aiohttp.ClientSession(headers=headers) as session:
        while offset < 500:
            params = {"specialization": "design", "offset": offset, "limit": limit}
            async with session.get(GETMATCH_API_URL, params=params) as resp:
                if resp.status != 200:
                    break
                data = await resp.json()

            offers = data.get("offers", [])
            if not offers:
                break

            for offer in offers:
                if offer.get("language") not in (None, "ru"):
                    continue
                vacancy = parser._parse_item(offer)
                if vacancy:
                    results[vacancy.uid] = vacancy

            total = data.get("meta", {}).get("total", 0)
            offset += limit
            if offset >= total:
                break

    return list(results.values())


async def _fetch_hh(settings: Settings, role: Role) -> tuple[list[Vacancy], bool]:
    """Вакансии с HH и признак, что HH ограничил запросы (ответил 403)."""
    parser = HHParser(settings)
    vacancies = await parser.fetch_for_queries(
        role.hh_queries,
        role.matcher,
        professional_roles=role.hh_professional_roles,
    )
    # HH уже отказал на основном поиске — к бигтеху идти незачем, будет тот же 403.
    bigtech = [] if parser.forbidden_hit else await parser.fetch_bigtech(
        role.matcher,
        role.hh_queries,
        role.hh_professional_roles,
    )
    merged = {vacancy.uid: vacancy for vacancy in vacancies}
    for vacancy in bigtech:
        merged[vacancy.uid] = vacancy
    return list(merged.values()), parser.forbidden_hit


async def _fetch_careers(settings: Settings, role: Role) -> list[Vacancy]:
    parser = BigTechCareersParser(settings)
    return await parser.fetch_matching(role.matcher, search_queries=role.hh_queries)


async def _fetch_geekjob(role: Role) -> list[Vacancy]:
    base = GeekJobParser()
    results: dict[str, Vacancy] = {}
    headers = {"User-Agent": "ProductDesignerVacancyBot/1.0"}

    async with aiohttp.ClientSession(headers=headers) as session:
        for query in role.geekjob_queries:
            page = 1
            while page <= 3:
                params = {"search": query, "page": page}
                async with session.get(
                    "https://geekjob.ru/json/find/vacancy", params=params
                ) as resp:
                    if resp.status != 200:
                        break
                    data = await resp.json()

                items = data.get("data", [])
                if not items:
                    break

                for item in items:
                    vacancy = base._parse_item(item)
                    if vacancy:
                        results[vacancy.uid] = vacancy

                next_page = data.get("nextpage")
                if not next_page or next_page <= page:
                    break
                page = int(next_page)

    return list(results.values())
