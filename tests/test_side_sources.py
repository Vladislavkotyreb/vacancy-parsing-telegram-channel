"""GeekJob и GetMatch в подписках: поиск через qs, GetMatch — один раз на прогон,
сбой дополнительных площадок не валит роль, сайт Сбера больше не опрашивается."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock
from unittest.mock import AsyncMock

from bot.config import Settings
from bot.database import VacancyDatabase
from bot.models import Vacancy
from bot.roles import get_role
from bot.subscriber_collect import _fetch_geekjob, collect_for_role, shared_feeds
from bot.subscriber_formatters import format_subscriber_header
from bot.subscriber_service import SubscriberService

NOW = datetime.now(timezone.utc)


def _settings(db_path: Path = Path("/tmp/unused.db")) -> Settings:
    return Settings(
        telegram_bot_token="test:token", telegram_chat_id=-100123, hh_user_agent="test/1.0",
        hh_access_token="", timezone="Europe/Moscow", max_vacancy_age_hours=72,
        db_path=db_path, telegram_admin_id=None,
    )


def _gm(n: int, title: str) -> Vacancy:
    return Vacancy(source="getmatch.ru", external_id=str(n), title=title, company=f"Компания {n}",
                   url=f"https://getmatch.ru/vacancies/{n}", published_at=NOW)


GETMATCH_FEED = [
    _gm(1, "Senior Python Developer"),
    _gm(2, "Product Designer"),
    _gm(3, "Data Engineer"),
]


class _FakeResponse:
    def __init__(self, data):
        self.status = 200
        self._data = data

    async def json(self):
        return self._data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    """Лента GeekJob из трёх страниц, по вакансии на странице."""

    calls: list = []
    TITLES = {1: "Python Developer", 2: "Product Designer", 3: "QA Engineer"}

    def __init__(self, *args, **kwargs):
        pass

    def get(self, url, params=None):
        _FakeSession.calls.append(dict(params or {}))
        page = int(params["page"])
        item = {"id": f"id-{page}", "position": self.TITLES[page],
                "company": {"name": "Компания"}, "log": {"modify": "сегодня"}}
        return _FakeResponse({"data": [item], "nextpage": page + 1 if page < 3 else 0})

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class GeekJobFeedTest(unittest.IsolatedAsyncioTestCase):
    async def test_reads_whole_catalogue_without_search(self):
        # Поиск GeekJob либо игнорируется (`search`), либо отдаёт часть каталога
        # по релевантности (`qs`) — весь каталог в 3 страницах полнее.
        _FakeSession.calls = []
        with mock.patch("bot.subscriber_collect.aiohttp.ClientSession", _FakeSession):
            vacancies = await _fetch_geekjob()

        self.assertEqual([p["page"] for p in _FakeSession.calls], [1, 2, 3])
        for params in _FakeSession.calls:
            self.assertEqual(set(params), {"page"})
        self.assertEqual(sorted(v.title for v in vacancies),
                         ["Product Designer", "Python Developer", "QA Engineer"])

    async def test_feed_downloaded_once_per_run_and_filtered_per_role(self):
        _FakeSession.calls = []
        with mock.patch("bot.subscriber_collect.aiohttp.ClientSession", _FakeSession), \
             mock.patch("bot.subscriber_collect._fetch_hh", new=AsyncMock(return_value=([], False))), \
             mock.patch("bot.subscriber_collect._fetch_habr", new=AsyncMock(return_value=[])), \
             mock.patch("bot.subscriber_collect._fetch_getmatch", new=AsyncMock(return_value=[])), \
             shared_feeds():
            python = await collect_for_role(_settings(), get_role("backend_python"))
            qa = await collect_for_role(_settings(), get_role("qa_manual"))

        self.assertEqual(len(_FakeSession.calls), 3)
        self.assertEqual([v.title for v in python], ["Python Developer"])
        self.assertEqual([v.title for v in qa], ["QA Engineer"])


class GetMatchSharedTest(unittest.IsolatedAsyncioTestCase):
    def patches(self, getmatch):
        return (
            mock.patch("bot.subscriber_collect._fetch_hh", new=AsyncMock(return_value=([], False))),
            mock.patch("bot.subscriber_collect._fetch_geekjob", new=AsyncMock(return_value=[])),
            mock.patch("bot.subscriber_collect._fetch_habr", new=AsyncMock(return_value=[])),
            mock.patch("bot.subscriber_collect._fetch_getmatch", new=getmatch),
        )

    async def test_fetched_once_per_run_and_filtered_per_role(self):
        getmatch = AsyncMock(return_value=list(GETMATCH_FEED))
        hh, geek, habr, gm = self.patches(getmatch)
        with hh, geek, habr, gm, shared_feeds():
            python = await collect_for_role(_settings(), get_role("backend_python"))
            designer = await collect_for_role(_settings(), get_role("product_designer"))
            data = await collect_for_role(_settings(), get_role("data_engineer"))

        self.assertEqual(getmatch.await_count, 1)
        self.assertEqual([v.title for v in python], ["Senior Python Developer"])
        self.assertEqual([v.title for v in designer], ["Product Designer"])
        self.assertEqual([v.title for v in data], ["Data Engineer"])

    async def test_no_stale_feed_outside_a_run(self):
        getmatch = AsyncMock(return_value=list(GETMATCH_FEED))
        hh, geek, habr, gm = self.patches(getmatch)
        with hh, geek, habr, gm:
            await collect_for_role(_settings(), get_role("backend_python"))
            await collect_for_role(_settings(), get_role("backend_python"))
        self.assertEqual(getmatch.await_count, 2)

    async def test_daily_run_downloads_getmatch_once(self):
        db_path = Path(tempfile.mkdtemp()) / "test.db"
        db = VacancyDatabase(db_path)
        for user_id, role in [(1, "backend_python"), (2, "qa_manual"), (3, "data_engineer")]:
            db.set_subscriber_roles(user_id, [role])
        service = SubscriberService(_settings(db_path), db, AsyncMock())

        getmatch = AsyncMock(return_value=list(GETMATCH_FEED))
        hh, geek, habr, gm = self.patches(getmatch)
        with hh, geek, habr, gm:
            stats = await service.run_daily_digests()

        self.assertEqual(getmatch.await_count, 1)
        self.assertEqual(stats.failed_roles, [])


class SideSourceFailureTest(unittest.IsolatedAsyncioTestCase):
    async def test_getmatch_or_geekjob_down_keeps_hh_results(self):
        hh_vacancy = Vacancy(source="hh.ru", external_id="1", title="Python-разработчик",
                             company="А", url="https://hh.ru/vacancy/1", published_at=NOW)
        for broken in ("_fetch_getmatch", "_fetch_geekjob"):
            with self.subTest(broken=broken), \
                 mock.patch("bot.subscriber_collect._fetch_hh",
                            new=AsyncMock(return_value=([hh_vacancy], False))), \
                 mock.patch("bot.subscriber_collect._fetch_geekjob", new=AsyncMock(return_value=[])), \
                 mock.patch("bot.subscriber_collect._fetch_habr", new=AsyncMock(return_value=[])), \
                 mock.patch("bot.subscriber_collect._fetch_getmatch", new=AsyncMock(return_value=[])), \
                 mock.patch(f"bot.subscriber_collect.{broken}",
                            new=AsyncMock(side_effect=RuntimeError("площадка недоступна"))):
                result = await collect_for_role(_settings(), get_role("backend_python"))
            self.assertEqual([v.uid for v in result], ["hh.ru:1"])

    async def test_failed_getmatch_is_not_retried_for_every_role(self):
        getmatch = AsyncMock(side_effect=RuntimeError("таймаут"))
        with mock.patch("bot.subscriber_collect._fetch_hh", new=AsyncMock(return_value=([], False))), \
             mock.patch("bot.subscriber_collect._fetch_geekjob", new=AsyncMock(return_value=[])), \
             mock.patch("bot.subscriber_collect._fetch_habr", new=AsyncMock(return_value=[])), \
             mock.patch("bot.subscriber_collect._fetch_getmatch", new=getmatch), \
             shared_feeds():
            for role_id in ("backend_python", "qa_manual", "data_engineer"):
                await collect_for_role(_settings(), get_role(role_id))
        self.assertEqual(getmatch.await_count, 1)


class SberCareersRemovedTest(unittest.IsolatedAsyncioTestCase):
    async def test_collect_does_not_touch_sber_site(self):
        careers = AsyncMock(return_value=[])
        with mock.patch("bot.parsers.bigtech.BigTechCareersParser.fetch_matching", new=careers), \
             mock.patch("bot.subscriber_collect._fetch_hh", new=AsyncMock(return_value=([], False))), \
             mock.patch("bot.subscriber_collect._fetch_geekjob", new=AsyncMock(return_value=[])), \
             mock.patch("bot.subscriber_collect._fetch_habr", new=AsyncMock(return_value=[])), \
             mock.patch("bot.subscriber_collect._fetch_getmatch", new=AsyncMock(return_value=[])):
            await collect_for_role(_settings(), get_role("product_designer"))
        careers.assert_not_awaited()

    def test_digest_header_lists_only_real_sources(self):
        header = format_subscriber_header("продакт-менеджера", 5, 10)
        self.assertIn("Источники: HeadHunter, Хабр Карьера, GeekJob, GetMatch", header)
        self.assertNotIn("Карьера (бигтех)", header)


if __name__ == "__main__":
    unittest.main()
