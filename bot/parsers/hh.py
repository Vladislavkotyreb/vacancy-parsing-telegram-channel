from __future__ import annotations

import asyncio
import logging
import math
from typing import Any, Callable, Optional

import aiohttp

from bot.config import (
    BIGTECH_HH_EMPLOYERS,
    BIGTECH_SEARCH_QUERIES,
    HH_AREAS,
    SEARCH_QUERIES,
    Settings,
)
from bot.dates import parse_iso_datetime
from bot.filters import is_product_designer_vacancy
from bot.grades import resolve_grade
from bot.models import Vacancy
from bot.parsers.base import BaseParser

logger = logging.getLogger(__name__)

HH_REQUEST_DELAY_SEC = 0.2


def _flatten_params(params: dict[str, Any]) -> list[tuple[str, str]]:
    """HH принимает повторяющиеся ключи (professional_role), aiohttp — только пары."""
    flat: list[tuple[str, str]] = []
    for key, value in params.items():
        if isinstance(value, (list, tuple)):
            flat.extend((key, str(item)) for item in value)
        else:
            flat.append((key, str(value)))
    return flat


class HHParser(BaseParser):
    source = "hh.ru"
    API_URL = "https://api.hh.ru/vacancies"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def fetch(self) -> list[Vacancy]:
        results: dict[str, Vacancy] = {}
        forbidden = False

        async with aiohttp.ClientSession(headers=self._headers()) as session:
            period = self._period_days()
            for area in HH_AREAS:
                for query in SEARCH_QUERIES:
                    forbidden = await self._search(
                        session,
                        results,
                        {
                            "text": query,
                            "area": area,
                            "per_page": 100,
                            "order_by": "publication_time",
                            "search_field": "name",
                            "period": period,
                        },
                        matcher=is_product_designer_vacancy,
                        max_pages=5,
                        forbidden=forbidden,
                    )
                    if forbidden:
                        break
                if forbidden:
                    break

            if not forbidden:
                await self._fetch_bigtech_employers(
                    session, results, matcher=is_product_designer_vacancy
                )

        return list(results.values())

    async def fetch_for_queries(
        self,
        queries: tuple[str, ...],
        matcher: Callable[[str], bool],
        *,
        max_pages: int = 3,
        professional_roles: tuple[int, ...] = (),
    ) -> list[Vacancy]:
        results: dict[str, Vacancy] = {}
        forbidden = False
        period = self._period_days()

        async with aiohttp.ClientSession(headers=self._headers()) as session:
            for area in HH_AREAS:
                for query in queries:
                    params: dict[str, Any] = {
                        "text": query,
                        "area": area,
                        "per_page": 100,
                        "order_by": "publication_time",
                        "search_field": "name",
                        "period": period,
                    }
                    # Сужает выдачу до нужной профобласти HH: для «тестировщика»
                    # это отсекает контроль качества на стройке и в производстве.
                    if professional_roles:
                        params["professional_role"] = professional_roles

                    forbidden = await self._search(
                        session,
                        results,
                        params,
                        matcher=matcher,
                        max_pages=max_pages,
                        forbidden=forbidden,
                    )
                    if forbidden:
                        break
                if forbidden:
                    break

        return list(results.values())

    async def _fetch_bigtech_employers(
        self,
        session: aiohttp.ClientSession,
        results: dict[str, Vacancy],
        matcher: Callable[[str], bool],
        queries: tuple[str, ...] | None = None,
        professional_roles: tuple[int, ...] = (),
    ) -> None:
        period = self._period_days()
        added = 0
        search_queries = queries or tuple(BIGTECH_SEARCH_QUERIES)

        for company_name, employer_id in BIGTECH_HH_EMPLOYERS:
            for query in search_queries:
                before = len(results)
                params: dict[str, Any] = {
                    "employer_id": employer_id,
                    "text": query,
                    "per_page": 100,
                    "order_by": "publication_time",
                    "period": period,
                }
                if professional_roles:
                    params["professional_role"] = professional_roles

                await self._search(
                    session,
                    results,
                    params,
                    matcher=matcher,
                    max_pages=2,
                    forbidden=False,
                )
                added += len(results) - before

        if added:
            logger.info("HH.ru bigtech employers: +%s вакансий", added)

    async def fetch_bigtech(
        self,
        matcher: Callable[[str], bool],
        queries: tuple[str, ...] | None = None,
        professional_roles: tuple[int, ...] = (),
    ) -> list[Vacancy]:
        results: dict[str, Vacancy] = {}
        async with aiohttp.ClientSession(headers=self._headers()) as session:
            await self._fetch_bigtech_employers(
                session, results, matcher, queries, professional_roles
            )
        return list(results.values())

    async def _search(
        self,
        session: aiohttp.ClientSession,
        results: dict[str, Vacancy],
        base_params: dict[str, Any],
        matcher: Callable[[str], bool],
        *,
        max_pages: int,
        forbidden: bool,
    ) -> bool:
        if forbidden:
            return True

        for page in range(max_pages):
            params = {**base_params, "page": page}
            async with session.get(self.API_URL, params=_flatten_params(params)) as resp:
                if resp.status == 403:
                    logger.warning(
                        "HH.ru API 403 (auth=%s). Проверьте HH_ACCESS_TOKEN и HH_USER_AGENT.",
                        "yes" if self.settings.hh_access_token else "no",
                    )
                    return True
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning(
                        "HH.ru API %s params=%s auth=%s: %s",
                        resp.status,
                        {k: v for k, v in params.items() if k != "page"},
                        "yes" if self.settings.hh_access_token else "no",
                        body[:200],
                    )
                    break
                data = await resp.json()

            items = data.get("items", [])
            if not items:
                break

            for item in items:
                vacancy = self._parse_item(item)
                if vacancy and matcher(vacancy.title):
                    results[vacancy.uid] = vacancy

            if page + 1 >= data.get("pages", 0):
                break

            await asyncio.sleep(HH_REQUEST_DELAY_SEC)

        await asyncio.sleep(HH_REQUEST_DELAY_SEC)
        return False

    def _period_days(self) -> int:
        hours = self.settings.max_vacancy_age_hours
        return max(1, math.ceil(hours / 24))

    def _headers(self) -> dict[str, str]:
        headers = {
            "User-Agent": self.settings.hh_user_agent,
            "Accept": "application/json",
        }
        if self.settings.hh_access_token:
            headers["Authorization"] = f"Bearer {self.settings.hh_access_token}"
        return headers

    def _parse_item(self, item: dict[str, Any]) -> Optional[Vacancy]:
        title = item.get("name", "")
        if not title:
            return None
        external_id = str(item.get("id", ""))
        if not external_id:
            return None

        salary = self._format_salary(item.get("salary"))
        location_parts = []
        if area := item.get("area"):
            location_parts.append(area.get("name", ""))
        location = ", ".join(part for part in location_parts if part) or None

        work_format = None
        schedule = item.get("schedule", {}) or {}
        if schedule.get("id") == "remote":
            work_format = "Удалённо"

        published_at = None
        if published := item.get("published_at"):
            published_at = parse_iso_datetime(published)

        employer = item.get("employer", {}) or {}
        experience = item.get("experience") or {}
        hh_experience_id = experience.get("id")

        return Vacancy(
            source=self.source,
            external_id=external_id,
            title=title,
            company=employer.get("name", "—"),
            url=item.get("alternate_url", ""),
            salary=salary,
            location=location,
            published_at=published_at,
            work_format=work_format,
            grade=resolve_grade(title, hh_experience_id),
        )

    @staticmethod
    def _format_salary(salary: Optional[dict[str, Any]]) -> Optional[str]:
        if not salary:
            return None

        currency = salary.get("currency", "RUR")
        symbol = {"RUR": "₽", "USD": "$", "EUR": "€", "KZT": "₸", "BYR": "Br"}.get(
            currency, currency
        )
        low = salary.get("from")
        high = salary.get("to")

        if low and high:
            return f"{low:,} — {high:,} {symbol}".replace(",", " ")
        if low:
            return f"от {low:,} {symbol}".replace(",", " ")
        if high:
            return f"до {high:,} {symbol}".replace(",", " ")
        return None
