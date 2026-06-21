from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from bot.models import Vacancy

MONTHS = {
    "январ": 1,
    "феврал": 2,
    "март": 3,
    "апрел": 4,
    "ма": 5,
    "июн": 6,
    "июл": 7,
    "август": 8,
    "сентябр": 9,
    "октябр": 10,
    "ноябр": 11,
    "декабр": 12,
}

RU_DATE_RE = re.compile(
    r"(\d{1,2})\s+(" + "|".join(MONTHS) + r")[a-я]*\s+(\d{4})",
    re.I,
)
RU_DATE_NO_YEAR_RE = re.compile(
    r"(\d{1,2})\s+(" + "|".join(MONTHS) + r")[a-я]*",
    re.I,
)
RELATIVE_DAYS_RE = re.compile(r"(\d+)\s+(?:день|дня|дней)\s+назад", re.I)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_iso_datetime(value: str) -> Optional[datetime]:
    text = value.strip()
    if not text:
        return None
    try:
        return ensure_aware(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except ValueError:
        return None


def parse_russian_date(text: str, *, now: Optional[datetime] = None) -> Optional[datetime]:
    now = ensure_aware(now or utc_now())
    source = text.strip().lower()
    if not source:
        return None

    if "сегодня" in source:
        return now
    if "вчера" in source:
        return now - timedelta(days=1)

    relative = RELATIVE_DAYS_RE.search(source)
    if relative:
        return now - timedelta(days=int(relative.group(1)))

    match = RU_DATE_RE.search(source)
    if match:
        day, month_name, year = match.groups()
        month = _month_number(month_name)
        if month:
            return datetime(int(year), month, int(day), tzinfo=now.tzinfo)

    match = RU_DATE_NO_YEAR_RE.search(source)
    if match:
        day, month_name = match.groups()
        month = _month_number(month_name)
        if month:
            year = now.year
            candidate = datetime(year, month, int(day), tzinfo=now.tzinfo)
            if candidate > now + timedelta(days=1):
                candidate = candidate.replace(year=year - 1)
            return candidate

    return None


def _month_number(name: str) -> Optional[int]:
    lowered = name.lower()
    for prefix, number in MONTHS.items():
        if lowered.startswith(prefix):
            return number
    return None


def is_fresh(vacancy: Vacancy, max_age_hours: int, *, now: Optional[datetime] = None) -> bool:
    if not vacancy.published_at:
        return False
    published = ensure_aware(vacancy.published_at)
    cutoff = ensure_aware(now or utc_now()) - timedelta(hours=max_age_hours)
    return published >= cutoff


def dedupe_key(title: str, company: str) -> str:
    def normalize(value: str) -> str:
        text = value.lower().strip()
        text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
        return re.sub(r"\s+", " ", text).strip()

    return f"{normalize(title)}|{normalize(company)}"


def dedupe_by_title_company(vacancies: list[Vacancy]) -> list[Vacancy]:
    best: dict[str, Vacancy] = {}
    ordered = sorted(
        vacancies,
        key=lambda item: ensure_aware(item.published_at) if item.published_at else datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    for vacancy in ordered:
        key = dedupe_key(vacancy.title, vacancy.company)
        if key not in best:
            best[key] = vacancy
    return sorted(
        best.values(),
        key=lambda item: ensure_aware(item.published_at) if item.published_at else datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
