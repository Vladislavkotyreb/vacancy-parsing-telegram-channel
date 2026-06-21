from __future__ import annotations

from typing import Any, Optional

import aiohttp

from bot.dates import parse_russian_date
from bot.filters import is_product_designer_vacancy
from bot.models import Vacancy
from bot.parsers.base import BaseParser

BASE_URL = "https://geekjob.ru"
API_URL = f"{BASE_URL}/json/find/vacancy"


class GeekJobParser(BaseParser):
    source = "geekjob.ru"

    async def fetch(self) -> list[Vacancy]:
        results: dict[str, Vacancy] = {}
        queries = ["продуктовый дизайнер", "product designer", "ux designer", "дизайнер"]

        headers = {"User-Agent": "ProductDesignerVacancyBot/1.0"}

        async with aiohttp.ClientSession(headers=headers) as session:
            for query in queries:
                page = 1
                while page <= 5:
                    params = {"search": query, "page": page}
                    async with session.get(API_URL, params=params) as resp:
                        if resp.status != 200:
                            break
                        data = await resp.json()

                    items = data.get("data", [])
                    if not items:
                        break

                    for item in items:
                        vacancy = self._parse_item(item)
                        if vacancy and is_product_designer_vacancy(vacancy.title):
                            results[vacancy.uid] = vacancy

                    next_page = data.get("nextpage")
                    if not next_page or next_page <= page:
                        break
                    page = int(next_page)

        return list(results.values())

    def _parse_item(self, item: dict[str, Any]) -> Optional[Vacancy]:
        title = item.get("position", "").strip()
        if not title:
            return None

        job_format = item.get("jobFormat") or {}
        formats = []
        if job_format.get("remote"):
            formats.append("Удалённо")
        if job_format.get("inhouse"):
            formats.append("Офис")
        if job_format.get("relocate"):
            formats.append("Релокация")

        location_parts = []
        if country := item.get("country"):
            location_parts.append(country)
        if city := item.get("city"):
            location_parts.append(city)
        location = ", ".join(location_parts) or (", ".join(formats) if formats else None)

        company = (item.get("company") or {}).get("name", "—")
        external_id = str(item.get("id", ""))
        if not external_id:
            return None

        published_at = None
        log = item.get("log") or {}
        if modify := log.get("modify"):
            published_at = parse_russian_date(str(modify))

        return Vacancy(
            source=self.source,
            external_id=external_id,
            title=title,
            company=company,
            url=f"{BASE_URL}/vacancy/{external_id}",
            salary=item.get("salary"),
            location=location,
            work_format=", ".join(formats) if formats else None,
            published_at=published_at,
        )
