from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Awaitable, Callable, Iterator, Optional

import aiohttp

from bot.config import Settings
from bot.cross_source import dedupe_across_sources
from bot.models import Vacancy
from bot.parsers import habr_career
from bot.parsers.geekjob import GeekJobParser
from bot.parsers.getmatch import GetMatchParser
from bot.parsers.hh import HHParser
from bot.roles import Role

logger = logging.getLogger(__name__)

GETMATCH_API_URL = "https://getmatch.ru/api/offers"
GEEKJOB_API_URL = "https://geekjob.ru/json/find/vacancy"
# GeekJob и GetMatch — дополнение к HH. Без таймаута зависшая площадка держала
# бы каждую роль по 5 минут (умолчание aiohttp).
SIDE_SOURCE_TIMEOUT = aiohttp.ClientTimeout(total=20)
# Сейчас у GeekJob 3 страницы; 5 — с запасом, если каталог подрастёт.
GEEKJOB_MAX_PAGES = 5

# Ленты, общие для всех ролей одного прогона рассылки (см. shared_feeds).
_run_feeds: ContextVar[Optional[dict]] = ContextVar("subscriber_run_feeds", default=None)


class SourceLimited(Exception):
    """Площадка ограничила запросы (HTTP 403): собранное неполное, но годное.

    Несёт то, что успело собраться, — подписчики получат хотя бы это, а админ
    узнает, что роль собрана не целиком.
    """

    def __init__(self, source: str, vacancies: list[Vacancy]) -> None:
        super().__init__(f"{source}: доступ ограничен (HTTP 403)")
        self.source = source
        self.vacancies = vacancies


@contextmanager
def shared_feeds() -> Iterator[None]:
    """Общие ленты на один прогон рассылки: GetMatch качается один раз на все роли.

    Вне этого блока каждый вызов collect_for_role качает ленту заново — так
    кэш не переживает прогон и не протухает между запусками и тестами.
    """
    token = _run_feeds.set({})
    try:
        yield
    finally:
        _run_feeds.reset(token)


async def collect_for_role(settings: Settings, role: Role) -> list[Vacancy]:
    results: dict[str, Vacancy] = {}
    hh_vacancies, hh_limited = await _fetch_hh(settings, role)

    # Сайт Сбера (BigTechCareersParser) здесь больше не опрашивается: вакансии
    # он подгружает скриптом, парсер их не видел, а вакансии Сбера и так
    # приходят с HH через поиск по работодателям.
    hours = settings.max_vacancy_age_hours
    for source, vacancies in [
        ("hh.ru", hh_vacancies),
        ("career.habr.com", await _shared_feed("career.habr.com", lambda: _fetch_habr(hours))),
        ("geekjob.ru", await _shared_feed("geekjob.ru", _fetch_geekjob)),
        ("getmatch.ru", await _shared_feed("getmatch.ru", _fetch_getmatch)),
    ]:
        matched = [vacancy for vacancy in vacancies if role.matcher(vacancy.title)]
        logger.info(
            "Подписчики [%s] %s: найдено %s, подошло %s",
            role.id,
            source,
            len(vacancies),
            len(matched),
        )
        for vacancy in matched:
            results[vacancy.uid] = vacancy

    collected = dedupe_across_sources(list(results.values()))
    if hh_limited:
        raise SourceLimited("hh.ru", collected)
    return collected


async def _side_source(name: str, fetch: Awaitable[list[Vacancy]]) -> list[Vacancy]:
    """Сбой Хабра, GeekJob или GetMatch не валит роль: подписчик получит хотя бы HH."""
    try:
        return await fetch
    except Exception as exc:
        logger.warning("%s недоступен, собираем без него: %r", name, exc)
        return []


async def _shared_feed(
    name: str, fetch: Callable[[], Awaitable[list[Vacancy]]]
) -> list[Vacancy]:
    """Лента площадки целиком; внутри shared_feeds — одна на прогон, вместе со сбоем.

    GeekJob и GetMatch маленькие: вся свежая лента — несколько страниц, а их
    поиск либо не работает (GetMatch), либо сортирует по релевантности и
    показывает часть каталога (GeekJob). Дешевле и полнее скачать ленту раз
    и отобрать вакансии фильтром каждой роли.
    """
    feeds = _run_feeds.get()
    if feeds is not None and name in feeds:
        return feeds[name]
    vacancies = await _side_source(name, fetch())
    if feeds is not None:
        feeds[name] = vacancies
    return vacancies


async def _fetch_habr(max_age_hours: int) -> list[Vacancy]:
    return await habr_career.fetch_recent(max_age_hours, SIDE_SOURCE_TIMEOUT)


async def _fetch_getmatch() -> list[Vacancy]:
    """Все свежие вакансии GetMatch одной лентой, роль отбирает свои по названию.

    Фильтр specialization сайт игнорирует — на любое значение отдаёт все
    IT-вакансии, поэтому не передаём его. Лента идёт от новых к старым,
    500 штук — это примерно две недели, с запасом больше 72 часов.
    """
    parser = GetMatchParser()
    results: dict[str, Vacancy] = {}
    offset = 0
    limit = 50
    headers = {"Accept": "application/json", "User-Agent": "ProductDesignerVacancyBot/1.0"}

    async with aiohttp.ClientSession(headers=headers, timeout=SIDE_SOURCE_TIMEOUT) as session:
        while offset < 500:
            params = {"offset": offset, "limit": limit}
            async with session.get(GETMATCH_API_URL, params=params) as resp:
                if resp.status != 200:
                    break
                data = await resp.json()

            offers = data.get("offers", [])
            if not offers:
                break

            for offer in offers:
                if offer.get("language") not in (None, "ru"):
                    continue
                vacancy = parser._parse_item(offer)
                if vacancy:
                    results[vacancy.uid] = vacancy

            total = data.get("meta", {}).get("total", 0)
            offset += limit
            if offset >= total:
                break

    return list(results.values())


async def _fetch_hh(settings: Settings, role: Role) -> tuple[list[Vacancy], bool]:
    """Вакансии с HH и признак, что HH ограничил запросы (ответил 403)."""
    parser = HHParser(settings)
    vacancies = await parser.fetch_for_queries(
        role.hh_queries,
        role.matcher,
        professional_roles=role.hh_professional_roles,
    )
    # HH уже отказал на основном поиске — к бигтеху идти незачем, будет тот же 403.
    bigtech = [] if parser.forbidden_hit else await parser.fetch_bigtech(
        role.matcher,
        role.hh_queries,
        role.hh_professional_roles,
    )
    merged = {vacancy.uid: vacancy for vacancy in vacancies}
    for vacancy in bigtech:
        merged[vacancy.uid] = vacancy
    return list(merged.values()), parser.forbidden_hit


async def _fetch_geekjob() -> list[Vacancy]:
    """Весь каталог GeekJob: около 270 вакансий на 3 страницах, от новых к старым.

    Поиск не используем: `search` сайт игнорирует, а `qs` сортирует по
    релевантности и отдаёт лишь часть каталога — старые вакансии сверху.
    """
    base = GeekJobParser()
    results: dict[str, Vacancy] = {}
    headers = {"User-Agent": "ProductDesignerVacancyBot/1.0"}

    async with aiohttp.ClientSession(headers=headers, timeout=SIDE_SOURCE_TIMEOUT) as session:
        page = 1
        while page <= GEEKJOB_MAX_PAGES:
            async with session.get(GEEKJOB_API_URL, params={"page": page}) as resp:
                if resp.status != 200:
                    break
                data = await resp.json()

            items = data.get("data", [])
            if not items:
                break
            for item in items:
                vacancy = base._parse_item(item)
                if vacancy:
                    results[vacancy.uid] = vacancy

            next_page = data.get("nextpage")
            if not next_page or int(next_page) <= page:
                break
            page = int(next_page)

    return list(results.values())
