from __future__ import annotations

from typing import Any, Optional

import aiohttp

from bot.dates import parse_iso_datetime
from bot.filters import is_product_designer_vacancy
from bot.models import Vacancy
from bot.parsers.base import BaseParser

BASE_URL = "https://getmatch.ru"
API_URL = f"{BASE_URL}/api/offers"


class GetMatchParser(BaseParser):
    source = "getmatch.ru"

    async def fetch(self) -> list[Vacancy]:
        results: dict[str, Vacancy] = {}
        offset = 0
        limit = 50
        headers = {"Accept": "application/json", "User-Agent": "ProductDesignerVacancyBot/1.0"}

        async with aiohttp.ClientSession(headers=headers) as session:
            while offset < 500:
                params = {"specialization": "design", "offset": offset, "limit": limit}
                async with session.get(API_URL, params=params) as resp:
                    if resp.status != 200:
                        break
                    data = await resp.json()

                offers = data.get("offers", [])
                if not offers:
                    break

                for offer in offers:
                    if offer.get("language") not in (None, "ru"):
                        continue
                    vacancy = self._parse_item(offer)
                    if vacancy and is_product_designer_vacancy(vacancy.title):
                        results[vacancy.uid] = vacancy

                total = data.get("meta", {}).get("total", 0)
                offset += limit
                if offset >= total:
                    break

        return list(results.values())

    def _parse_item(self, offer: dict[str, Any]) -> Optional[Vacancy]:
        title = offer.get("position", "").strip()
        if not title:
            return None

        external_id = str(offer.get("id", ""))
        if not external_id:
            return None

        salary = self._format_salary(offer)
        location = self._format_location(offer)

        published_at = None
        if published := offer.get("published_at"):
            published_at = parse_iso_datetime(str(published))

        company_info = offer.get("company") or {}
        company = company_info.get("name") or offer.get("company_name") or "—"

        path = offer.get("url", "")
        url = f"{BASE_URL}{path}" if path.startswith("/") else path

        return Vacancy(
            source=self.source,
            external_id=external_id,
            title=title,
            company=company,
            url=url,
            salary=salary,
            location=location,
            published_at=published_at,
        )

    @staticmethod
    def _format_salary(offer: dict[str, Any]) -> Optional[str]:
        if offer.get("salary_hidden"):
            return "з/п скрыта"

        low = offer.get("salary_display_from")
        high = offer.get("salary_display_to")
        currency = offer.get("salary_currency") or "RUB"
        symbol = {"RUB": "₽", "USD": "$", "EUR": "€"}.get(currency, currency)

        if low and high:
            return f"{low:,} — {high:,} {symbol}".replace(",", " ")
        if low:
            return f"от {low:,} {symbol}".replace(",", " ")
        if high:
            return f"до {high:,} {symbol}".replace(",", " ")
        if desc := offer.get("salary_description"):
            return str(desc)
        return None

    @staticmethod
    def _format_location(offer: dict[str, Any]) -> Optional[str]:
        locations = offer.get("location_requirements") or []
        parts = []
        for loc in locations:
            country = loc.get("country")
            fmt = loc.get("format")
            if country:
                parts.append(country)
            if fmt == "remote":
                parts.append("удалённо")
            elif fmt == "office":
                parts.append("офис")
        return ", ".join(dict.fromkeys(parts)) if parts else None
