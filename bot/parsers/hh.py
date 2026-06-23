from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import aiohttp

from bot.config import HH_AREAS, SEARCH_QUERIES, Settings
from bot.dates import parse_iso_datetime
from bot.filters import is_product_designer_vacancy
from bot.models import Vacancy
from bot.parsers.base import BaseParser

logger = logging.getLogger(__name__)


class HHParser(BaseParser):
    source = "hh.ru"
    API_URL = "https://api.hh.ru/vacancies"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def fetch(self) -> list[Vacancy]:
        results: dict[str, Vacancy] = {}
        headers = self._headers()
        date_to_dt = datetime.now(timezone.utc)
        date_from_dt = date_to_dt - timedelta(hours=self.settings.max_vacancy_age_hours)
        date_from = date_from_dt.isoformat(timespec="seconds")
        date_to = date_to_dt.isoformat(timespec="seconds")

        async with aiohttp.ClientSession(headers=headers) as session:
            for area in HH_AREAS:
                for query in SEARCH_QUERIES:
                    page = 0
                    while page < 5:
                        params = {
                            "text": query,
                            "area": area,
                            "per_page": 100,
                            "page": page,
                            "order_by": "publication_time",
                            "search_field": "name",
                            "date_from": date_from,
                            "date_to": date_to,
                        }
                        async with session.get(self.API_URL, params=params) as resp:
                            if resp.status == 403:
                                logger.warning(
                                    "HH.ru API 403 (доступ запрещён, auth=%s). "
                                    "Пропускаю источник — задайте HH_ACCESS_TOKEN.",
                                    "yes" if self.settings.hh_access_token else "no",
                                )
                                return list(results.values())
                            if resp.status != 200:
                                body = await resp.text()
                                logger.warning(
                                    "HH.ru API %s для area=%s query=%r auth=%s: %s",
                                    resp.status,
                                    area,
                                    query,
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
                            if vacancy and is_product_designer_vacancy(vacancy.title):
                                results[vacancy.uid] = vacancy

                        page += 1
                        if page >= data.get("pages", 0):
                            break

        return list(results.values())

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
