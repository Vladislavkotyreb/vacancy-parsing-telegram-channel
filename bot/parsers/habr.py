from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

from bot.dates import parse_iso_datetime, parse_russian_date
from bot.filters import is_product_designer_vacancy
from bot.models import Vacancy
from bot.parsers.base import BaseParser

BASE_URL = "https://career.habr.com"
SEARCH_URL = f"{BASE_URL}/vacancies"


class HabrParser(BaseParser):
    source = "habr.com"

    async def fetch(self) -> list[Vacancy]:
        results: dict[str, Vacancy] = {}
        queries = ["продуктовый дизайнер", "product designer", "ux ui designer"]

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }

        async with aiohttp.ClientSession(headers=headers) as session:
            for query in queries:
                for page in range(1, 4):
                    params = {"q": query, "page": page}
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

        for card in soup.select("div.vacancy-card"):
            title_link = card.select_one("a.vacancy-card__title-link")
            if not title_link:
                title_link = card.select_one('a[href^="/vacancies/"][aria-label]')
            if not title_link:
                continue

            href = title_link.get("href", "")
            title = title_link.get_text(strip=True) or title_link.get("aria-label", "").strip()
            external_id = self._extract_id(href)
            if not external_id or not title or external_id in seen_ids:
                continue
            seen_ids.add(external_id)

            company = self._extract_company(card)
            salary = None
            location = None

            meta_text = card.get_text(" ", strip=True)
            salary_match = re.search(
                r"(\d[\d\s]*(?:\s*—\s*\d[\d\s]*)?\s*(?:₽|\$|€|руб\.?))",
                meta_text,
            )
            if salary_match:
                salary = salary_match.group(1).strip()

            meta_lower = meta_text.lower()
            if "удал" in meta_lower:
                location = "Удалённо"
            elif "офис" in meta_lower:
                location = "Офис"

            published_at = None
            time_el = card.select_one("time[datetime]")
            if time_el:
                published_at = parse_iso_datetime(time_el.get("datetime", ""))

            results.append(
                Vacancy(
                    source=self.source,
                    external_id=external_id,
                    title=title,
                    company=company,
                    url=urljoin(BASE_URL, href),
                    salary=salary,
                    location=location,
                    published_at=published_at,
                )
            )

        if not results:
            results = self._parse_html_fallback(html)

        return results

    @staticmethod
    def _extract_company(card) -> str:
        for company_link in card.select('a[href*="/companies/"]'):
            href = company_link.get("href", "")
            if "/scores/" in href:
                continue
            name = company_link.get_text(strip=True)
            if name:
                return name

        company_el = card.select_one(".vacancy-card__company")
        if company_el:
            name = re.sub(r"\s*\d+\.\d+\s*$", "", company_el.get_text(strip=True)).strip()
            if name:
                return name

        return "—"

    def _parse_html_fallback(self, html: str) -> list[Vacancy]:
        results: list[Vacancy] = []
        for href, title in re.findall(
            r'href="(/vacancies/\d+[^"]*)"[^>]*>([^<]+)<', html
        ):
            title = title.strip()
            external_id = self._extract_id(href)
            if not external_id or not title:
                continue
            results.append(
                Vacancy(
                    source=self.source,
                    external_id=external_id,
                    title=title,
                    company="—",
                    url=urljoin(BASE_URL, href),
                )
            )
        return results

    @staticmethod
    def _extract_id(href: str) -> Optional[str]:
        match = re.search(r"/vacancies/(\d+)", href)
        return match.group(1) if match else None
