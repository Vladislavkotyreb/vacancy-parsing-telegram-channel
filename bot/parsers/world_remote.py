"""Удалёнка по миру: вакансии, открытые для кандидатов из любой страны.

Только подписки с регионом «мир» или «оба». Каждая площадка — общая лента на
прогон (как Хабр, GeekJob, GetMatch), роли отбирают свои вакансии по названию.
Берём только вакансии без ограничения по стране: «USA Only» человеку из СНГ
бесполезна.

- Himalayas — `worldwide=true`, по 20 за запрос, за 72 ч ~10 страниц.
- We Work Remotely — одна RSS-лента на ~5 дней, регион «Anywhere in the World».
- Jobicy — `geo=anywhere`, одна страница ~ неделя.

Indeed и LinkedIn не подключены: открытого API нет, сайты блокируют ботов
(403/429), правила запрещают парсинг. Remote OK бесплатно отдаёт ленту с
задержкой — за 72 ч ни одной вакансии наших ролей.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Optional

import aiohttp

from bot.dates import ensure_aware, parse_iso_datetime, utc_now
from bot.grades import extract_grade
from bot.models import Vacancy

logger = logging.getLogger(__name__)

HIMALAYAS = "himalayas.app"
WWR = "weworkremotely.com"
JOBICY = "jobicy.com"
WORLD_SOURCES = frozenset({HIMALAYAS, WWR, JOBICY})

HIMALAYAS_URL = "https://himalayas.app/jobs/api/search"
HIMALAYAS_MAX_PAGES = 25  # ~500 вакансий: с запасом на 72 часа
WWR_URL = "https://weworkremotely.com/remote-jobs.rss"
WWR_ANYWHERE = "anywhere in the world"
JOBICY_URL = "https://jobicy.com/api/v2/remote-jobs"
PAGE_PAUSE_SEC = 0.3
REMOTE_WORLDWIDE = "Удалённо, весь мир"
HEADERS = {"Accept": "application/json", "User-Agent": "ProductDesignerVacancyBot/1.0"}

_PERIODS = {"yearly": "в год", "year": "в год", "monthly": "в месяц", "month": "в месяц",
            "hourly": "в час", "hour": "в час"}


def _text(value: Any) -> str:
    return " ".join(html.unescape(str(value or "")).split())


def _salary(low: Any, high: Any, currency: Any, period: Any) -> Optional[str]:
    def number(value: Any) -> Optional[int]:
        try:
            amount = int(float(value))
        except (TypeError, ValueError):
            return None
        return amount if amount > 0 else None

    low_n, high_n = number(low), number(high)
    if not low_n and not high_n:
        return None
    amount = (
        f"{low_n:,}–{high_n:,}" if low_n and high_n and low_n != high_n
        else f"{(low_n or high_n):,}"
    ).replace(",", " ")
    tail = " ".join(p for p in (_text(currency), _PERIODS.get(str(period or "").lower(), "")) if p)
    return f"{amount} {tail}".strip()


# Площадка пометила вакансию «весь мир», а в названии — «(LatAm Only)», «US».
_REGION_IN_TITLE = (
    re.compile(r"\b(?:latam|latin america|north america|americas|canada|emea|apac|europe|"
               r"india|brazil|mexico|philippines|united states|united kingdom)\b", re.I),
    re.compile(r"\b(?:US|USA|U\.S\.|UK|EU)\b"),  # с учётом регистра: не «us» в тексте
)
# Подработки по разметке и обучению ИИ: «Research Expert (Python)», «AI Tutor».
_AI_GIGS = re.compile(r"\b(?:tutor|annotat\w*|rater|ai trainer|ai training|research expert)\b", re.I)


def _restricted_or_gig(title: str) -> bool:
    return any(p.search(title) for p in _REGION_IN_TITLE) or bool(_AI_GIGS.search(title))


def _vacancy(source: str, external_id: str, title: str, company: str, url: str,
             published_at: Optional[datetime], salary: Optional[str] = None) -> Optional[Vacancy]:
    if not title or not external_id or not url or _restricted_or_gig(title):
        return None
    return Vacancy(
        source=source,
        external_id=external_id,
        title=title,
        company=company or "—",
        url=url,
        salary=salary,
        location=REMOTE_WORLDWIDE,
        published_at=published_at,
        work_format="Удалённо",
        grade=extract_grade(title),
    )


# --- Himalayas ---

def parse_himalayas(item: dict[str, Any]) -> Optional[Vacancy]:
    # Поле приходит строкой вида "['United States']"; пустое — весь мир.
    restrictions = str(item.get("locationRestrictions") or "").strip()
    if restrictions not in ("", "[]"):
        return None
    # guid — постоянная страница вакансии. Последний кусок ссылки не годится в id:
    # «paid-ads-specialist» встречается у разных компаний.
    url = _text(item.get("guid") or item.get("applicationLink")).split("?", 1)[0]
    external_id = url.split("/companies/", 1)[-1]
    try:
        published = datetime.fromtimestamp(int(item.get("pubDate")), timezone.utc)
    except (TypeError, ValueError):
        published = None
    return _vacancy(
        HIMALAYAS, external_id, _text(item.get("title")),
        _text(item.get("companyName")), url, published,
        _salary(item.get("minSalary"), item.get("maxSalary"), item.get("currency"),
                item.get("salaryPeriod")),
    )


async def fetch_himalayas(max_age_hours: int, timeout: aiohttp.ClientTimeout) -> list[Vacancy]:
    cutoff = utc_now() - timedelta(hours=max_age_hours)
    results: dict[str, Vacancy] = {}
    async with aiohttp.ClientSession(headers=HEADERS, timeout=timeout) as session:
        for page in range(1, HIMALAYAS_MAX_PAGES + 1):
            params = {"worldwide": "true", "sort": "recent", "page": page}
            async with session.get(HIMALAYAS_URL, params=params) as resp:
                if resp.status != 200:
                    logger.warning("Himalayas: HTTP %s на странице %s", resp.status, page)
                    break
                data = await resp.json()
            items = data.get("jobs") or []
            if not items:
                break
            dates = []
            for item in items:
                vacancy = parse_himalayas(item)
                if vacancy:
                    results[vacancy.uid] = vacancy
                    if vacancy.published_at:
                        dates.append(vacancy.published_at)
            # Стоп, когда свежих на странице не осталось: на первой странице
            # Himalayas бывают старые вакансии, и «хоть одна старая» обрывала сбор.
            if dates and max(dates) < cutoff:
                break
            await asyncio.sleep(PAGE_PAUSE_SEC)
    return list(results.values())


# --- We Work Remotely ---

def parse_wwr(item: ET.Element) -> Optional[Vacancy]:
    if _text(item.findtext("region")).lower() != WWR_ANYWHERE:
        return None
    # Заголовок — «Компания: Должность».
    company, _, title = _text(item.findtext("title")).partition(": ")
    if not title:
        company, title = "", company
    url = _text(item.findtext("link") or item.findtext("guid"))
    try:
        published = ensure_aware(parsedate_to_datetime(item.findtext("pubDate") or ""))
    except (TypeError, ValueError):
        published = None
    return _vacancy(WWR, url.rstrip("/").rsplit("/", 1)[-1], title, company, url, published)


async def fetch_wwr(timeout: aiohttp.ClientTimeout) -> list[Vacancy]:
    async with aiohttp.ClientSession(headers=HEADERS, timeout=timeout) as session:
        async with session.get(WWR_URL) as resp:
            if resp.status != 200:
                logger.warning("We Work Remotely: HTTP %s", resp.status)
                return []
            body = await resp.text()
    root = ET.fromstring(body)
    vacancies = (parse_wwr(item) for item in root.iter("item"))
    return [v for v in vacancies if v]


# --- Jobicy ---

def parse_jobicy(item: dict[str, Any]) -> Optional[Vacancy]:
    if _text(item.get("jobGeo")).lower() != "anywhere":
        return None
    return _vacancy(
        JOBICY, _text(item.get("id")), _text(item.get("jobTitle")),
        _text(item.get("companyName")), _text(item.get("url")),
        parse_iso_datetime(str(item.get("pubDate") or "")),
        _salary(item.get("salaryMin"), item.get("salaryMax"), item.get("salaryCurrency"),
                item.get("salaryPeriod")),
    )


async def fetch_jobicy(timeout: aiohttp.ClientTimeout) -> list[Vacancy]:
    async with aiohttp.ClientSession(headers=HEADERS, timeout=timeout) as session:
        async with session.get(JOBICY_URL, params={"count": 50, "geo": "anywhere"}) as resp:
            if resp.status != 200:
                logger.warning("Jobicy: HTTP %s", resp.status)
                return []
            data = await resp.json()
    vacancies = (parse_jobicy(item) for item in data.get("jobs") or [])
    return [v for v in vacancies if v]
