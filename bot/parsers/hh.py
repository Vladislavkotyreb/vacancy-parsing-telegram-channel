from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import logging

import aiohttp

from bot.config import HH_AREAS, SEARCH_QUERIES, Settings
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
        headers = {"User-Agent": self.settings.hh_user_agent}
        date_from = (
            datetime.now(timezone.utc) - timedelta(hours=72)
        ).date().isoformat()

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
                            "date_from": date_from,
                        }
                        async with session.get(self.API_URL, params=params) as resp:
                            if resp.status != 200:
                                body = await resp.text()
                                logger.warning(
                                    "HH.ru API %s для area=%s query=%r: %s",
                                    resp.status,
                                    area,
                                    query,
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

    def _parse_item(self, item: dict[str, Any]) -> Optional[Vacancy]:
        title = item.get("name", "")
        if not title:
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
            published_at = datetime.fromisoformat(published.replace("Z", "+00:00"))

        employer = item.get("employer", {}) or {}

        return Vacancy(
            source=self.source,
            external_id=str(item["id"]),
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
