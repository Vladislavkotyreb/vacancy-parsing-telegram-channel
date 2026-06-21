from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

from bot.filters import is_product_designer_vacancy
from bot.models import Vacancy
from bot.parsers.base import BaseParser

BASE_URL = "https://djinni.co"
SEARCH_PATH = "/jobs/"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class DjinniParser(BaseParser):
    source = "djinni.co"

    async def fetch(self) -> list[Vacancy]:
        results: dict[str, Vacancy] = {}
        queries = [
            {"primary_keyword": "Design", "title": "product designer"},
            {"primary_keyword": "Design", "title": "продуктовый дизайнер"},
            {"primary_keyword": "Design", "title": "ux designer"},
        ]
        headers = {"User-Agent": USER_AGENT}

        async with aiohttp.ClientSession(headers=headers) as session:
            for query in queries:
                for page in range(1, 4):
                    params = {**query, "page": page}
                    async with session.get(
                        urljoin(BASE_URL, SEARCH_PATH), params=params
                    ) as resp:
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

        for card in soup.select("div.job-item"):
            header_link = card.select_one("a.job_item__header-link")
            title_el = card.select_one("h2.job-item__position")
            if not header_link or not title_el:
                continue

            href = header_link.get("href", "")
            external_id = self._extract_id(href)
            title = title_el.get_text(strip=True)
            if not external_id or not title or external_id in seen_ids:
                continue
            seen_ids.add(external_id)

            company_el = card.select_one("span.small.text-gray-800")
            company = company_el.get_text(strip=True) if company_el else "—"

            location_el = card.select_one(".location-text")
            location = location_el.get_text(" ", strip=True) if location_el else None

            meta = card.select_one(".fw-medium.d-flex")
            work_format = None
            if meta:
                meta_text = meta.get_text(" ", strip=True).lower()
                if "remote" in meta_text or "віддал" in meta_text:
                    work_format = "Удалённо"

            results.append(
                Vacancy(
                    source=self.source,
                    external_id=external_id,
                    title=title,
                    company=company or "—",
                    url=urljoin(BASE_URL, href.split("?")[0]),
                    location=location,
                    work_format=work_format,
                )
            )

        return results

    @staticmethod
    def _extract_id(href: str) -> Optional[str]:
        match = re.search(r"/jobs/(\d+)", href)
        return match.group(1) if match else None
