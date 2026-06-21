from __future__ import annotations

import re
from typing import Optional

import aiohttp
from bs4 import BeautifulSoup

from bot.filters import is_product_designer_vacancy
from bot.models import Vacancy
from bot.parsers.base import BaseParser

BASE_URL = "https://jobs.dou.ua"
SEARCH_URL = f"{BASE_URL}/vacancies/"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class DouParser(BaseParser):
    source = "dou.ua"

    async def fetch(self) -> list[Vacancy]:
        results: dict[str, Vacancy] = {}
        headers = {"User-Agent": USER_AGENT}

        async with aiohttp.ClientSession(headers=headers) as session:
            for page in range(0, 3):
                params = {"category": "Design"}
                if page:
                    params["page"] = page

                async with session.get(SEARCH_URL, params=params) as resp:
                    if resp.status != 200:
                        break
                    html = await resp.text()

                page_results = self._parse_html(html)
                if not page_results:
                    break

                for vacancy in page_results:
                    if is_product_designer_vacancy(vacancy.title):
                        results[vacancy.uid] = vacancy

        return list(results.values())

    def _parse_html(self, html: str) -> list[Vacancy]:
        soup = BeautifulSoup(html, "lxml")
        results: list[Vacancy] = []
        seen_ids: set[str] = set()

        for item in soup.select("li.l-vacancy"):
            title_link = item.select_one("div.title > a.vt")
            if not title_link:
                continue

            href = title_link.get("href", "")
            external_id = self._extract_id(href)
            title = title_link.get_text(strip=True)
            if not external_id or not title or external_id in seen_ids:
                continue
            seen_ids.add(external_id)

            company_el = item.select_one("a.company")
            company = company_el.get_text(strip=True) if company_el else "—"

            location_el = item.select_one("span.cities")
            location = location_el.get_text(strip=True) if location_el else None

            salary_el = item.select_one("span.salary")
            salary = salary_el.get_text(strip=True) if salary_el else None

            results.append(
                Vacancy(
                    source=self.source,
                    external_id=external_id,
                    title=title,
                    company=company or "—",
                    url=href,
                    salary=salary,
                    location=location,
                )
            )

        return results

    @staticmethod
    def _extract_id(href: str) -> Optional[str]:
        match = re.search(r"/vacancies/(\d+)/", href)
        return match.group(1) if match else None
