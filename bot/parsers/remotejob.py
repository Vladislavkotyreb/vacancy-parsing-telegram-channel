from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

from bot.filters import is_product_designer_vacancy
from bot.models import Vacancy
from bot.parsers.base import BaseParser

BASE_URL = "https://remote-job.ru"
SEARCH_URL = f"{BASE_URL}/search"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class RemoteJobParser(BaseParser):
    source = "remote-job.ru"

    async def fetch(self) -> list[Vacancy]:
        results: dict[str, Vacancy] = {}
        queries = [
            "product designer",
            "продуктовый дизайнер",
            "ux designer",
            "product design",
        ]
        headers = {"User-Agent": USER_AGENT}

        async with aiohttp.ClientSession(headers=headers) as session:
            for query in queries:
                for page in range(1, 4):
                    params = {
                        "search[query]": query,
                        "search[searchType]": "vacancy",
                        "page": page,
                    }
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

        for link in soup.select('a[href*="/vacancy/show/"]'):
            href = link.get("href", "")
            external_id = self._extract_id(href)
            if not external_id or external_id in seen_ids:
                continue

            title = self._clean_title(link)
            if not title or len(title) < 4:
                continue
            seen_ids.add(external_id)

            h2 = link.find_parent("h2")
            company = "—"
            salary = None
            if h2:
                company_link = h2.select_one('small a[href*="companyName"]')
                if company_link:
                    company = company_link.get_text(strip=True) or company

                salary_el = h2.find_next("h3")
                if salary_el:
                    salary_text = salary_el.get_text(strip=True)
                    if salary_text and "не указана" not in salary_text.lower():
                        salary = salary_text

            location = None
            if title and "удален" in title.lower():
                location = "Удалённо"

            results.append(
                Vacancy(
                    source=self.source,
                    external_id=external_id,
                    title=title,
                    company=company,
                    url=urljoin(BASE_URL, href),
                    salary=salary,
                    location=location,
                    work_format="Удалённо",
                )
            )

        return results

    @staticmethod
    def _extract_id(href: str) -> Optional[str]:
        match = re.search(r"/vacancy/show/(\d+)/", href)
        return match.group(1) if match else None

    @staticmethod
    def _clean_title(link) -> str:
        text = link.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"Design\s+er\b", "Designer", text, flags=re.I)
        text = re.sub(r"\d{1,2}\s+\w+\s+\d{4},?$", "", text).strip(" ,")
        return text.strip()
