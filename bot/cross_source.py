"""Одна вакансия на разных площадках — одна в подборке.

Обычный дедуп (`dedupe_key`) сравнивает название и компанию почти дословно, а
площадки пишут их по-разному: «RWB» и «RWB (Wildberries & Russ)», «Банк ВТБ» и
«Банк ВТБ (ПАО)», «медиа сервисов» и «медиасервисов». На живой выдаче так
проскакивало ~2% дублей между HH, Хабр Карьерой и GetMatch.

Ключ здесь мягче, но осторожный: грейд не выкидываем — «Младший» и «Старший
инженер по тестированию» одной компании — разные вакансии. Нужен только
подпискам; канал работает на `dedupe_key`, его поведение не меняется.
"""

from __future__ import annotations

import re

from bot.dates import dedupe_by_title_company, ensure_aware
from bot.models import Vacancy
from bot.source_priority import source_rank

_LEGAL_FORMS = re.compile(r"\b(?:ооо|ао|пао|зао|оао|нао|ип|llc|ltd|inc|jsc|gmbh)\b")
# Только бесспорные пары: одна и та же компания под разными именами на площадках.
# «MTS Web Services» и «МТС Банк» — разные компании, их здесь нет.
_COMPANY_ALIASES = {
    "сбер банк": "сбер",
    "сбербанк": "сбер",
    "sber": "сбер",
    "2gis": "2гис",
    "ozon tech": "ozon",
    "озон": "ozon",
    "rwb": "wildberries",
    "вайлдберриз": "wildberries",
    "т банк": "т банк",
    "t bank": "т банк",
    "tbank": "т банк",
    "тинькофф": "т банк",
    "tinkoff": "т банк",
    "yandex": "яндекс",
    "банк втб": "втб",
    "uzum technologies": "uzum",
    "kaspersky": "лаборатория касперского",
    "avito": "авито",
}


def normalize_company(company: str) -> str:
    text = (company or "").lower().replace("ё", "е")
    text = re.sub(r"\([^)]*\)", " ", text)  # «RWB (Wildberries & Russ)» → «RWB»
    text = re.sub(r"[«»\"'“”„]", " ", text)
    text = _LEGAL_FORMS.sub(" ", text)
    text = re.sub(r"[\W_]+", " ", text).strip()
    return _COMPANY_ALIASES.get(text, text)


def normalize_title(title: str) -> str:
    """Без пробелов и знаков: «медиа сервисов» = «медиасервисов», «Go-разработчик» = «Go разработчик»."""
    return re.sub(r"[\W_]+", "", (title or "").lower().replace("ё", "е"))


def merge_key(title: str, company: str) -> str:
    return f"{normalize_title(title)}|{normalize_company(company)}"


def dedupe_across_sources(vacancies: list[Vacancy]) -> list[Vacancy]:
    """Обычный дедуп, затем склейка по мягкому ключу. Из дублей остаётся вакансия
    с площадки повыше (HH первым), при равенстве — более свежая."""
    deduped = dedupe_by_title_company(vacancies)
    best: dict[str, Vacancy] = {}
    for vacancy in sorted(deduped, key=_preference):
        best.setdefault(merge_key(vacancy.title, vacancy.company), vacancy)
    keep = {id(v) for v in best.values()}
    return [v for v in deduped if id(v) in keep]  # порядок показа прежний


def _preference(vacancy: Vacancy) -> tuple[int, float]:
    published = ensure_aware(vacancy.published_at).timestamp() if vacancy.published_at else 0.0
    return source_rank(vacancy.source), -published
