"""HH ответил 403: подписчики узнают о неполной подборке, канал работает как раньше."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock
from unittest.mock import AsyncMock

from bot.config import BIGTECH_HH_EMPLOYERS, Settings
from bot.database import VacancyDatabase
from bot.models import Vacancy
from bot.parsers.hh import HHParser
from bot.roles import get_role
from bot.subscriber_collect import SourceLimited, collect_for_role
from bot.subscriber_service import SubscriberService


def _settings(db_path: Path = Path("/tmp/unused.db")) -> Settings:
    return Settings(
        telegram_bot_token="test:token", telegram_chat_id=-100123, hh_user_agent="test/1.0",
        hh_access_token="", timezone="Europe/Moscow", max_vacancy_age_hours=72,
        db_path=db_path, telegram_admin_id=None,
    )


class _Response:
    def __init__(self, status: int) -> None:
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self):
        return {"items": [], "pages": 0}

    async def text(self):
        return ""


class _Session:
    """Отвечает 403 на всё и считает запросы."""

    def __init__(self, status: int = 403) -> None:
        self.status = status
        self.calls = 0

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        return _Response(self.status)


class HHParserForbiddenTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.parser = HHParser(_settings())
        sleep = mock.patch("bot.parsers.hh.asyncio.sleep", new=AsyncMock())
        sleep.start()
        self.addCleanup(sleep.stop)

    async def test_403_is_remembered(self):
        self.assertFalse(self.parser.forbidden_hit)
        await self.parser._search(_Session(), {}, {"text": "x"}, matcher=lambda t: True,
                                  max_pages=1, forbidden=False)
        self.assertTrue(self.parser.forbidden_hit)

    async def test_subscriber_bigtech_stops_after_first_403(self):
        session = _Session()
        await self.parser._fetch_bigtech_employers(
            session, {}, lambda t: True, ("a", "b"), stop_on_forbidden=True
        )
        self.assertEqual(session.calls, 1)

    async def test_channel_bigtech_behaviour_unchanged(self):
        """Канал не трогаем: он, как и раньше, проходит всех работодателей."""
        session = _Session()
        await self.parser._fetch_bigtech_employers(session, {}, lambda t: True, ("a", "b"))
        self.assertEqual(session.calls, len(BIGTECH_HH_EMPLOYERS) * 2)


class CollectForRoleForbiddenTest(unittest.IsolatedAsyncioTestCase):
    async def test_limited_hh_raises_with_partial_results(self):
        partial = [Vacancy(source="hh.ru", external_id="1", title="Product Designer",
                           company="А", url="https://hh.ru/vacancy/1",
                           published_at=datetime.now(timezone.utc))]
        with mock.patch("bot.subscriber_collect._fetch_hh", new=AsyncMock(return_value=(partial, "доступ ограничен (HTTP 403)"))), \
             mock.patch("bot.subscriber_collect._fetch_geekjob", new=AsyncMock(return_value=[])), \
             mock.patch("bot.subscriber_collect._fetch_habr", new=AsyncMock(return_value=[])), \
             mock.patch("bot.subscriber_collect._fetch_getmatch", new=AsyncMock(return_value=[])):
            with self.assertRaises(SourceLimited) as ctx:
                await collect_for_role(_settings(), get_role("product_designer"))
        self.assertEqual([v.uid for v in ctx.exception.vacancies], ["hh.ru:1"])

    async def test_no_403_returns_normally(self):
        with mock.patch("bot.subscriber_collect._fetch_hh", new=AsyncMock(return_value=([], ""))), \
             mock.patch("bot.subscriber_collect._fetch_geekjob", new=AsyncMock(return_value=[])), \
             mock.patch("bot.subscriber_collect._fetch_habr", new=AsyncMock(return_value=[])), \
             mock.patch("bot.subscriber_collect._fetch_getmatch", new=AsyncMock(return_value=[])):
            self.assertEqual(await collect_for_role(_settings(), get_role("product_designer")), [])


class DigestWithLimitedRoleTest(unittest.IsolatedAsyncioTestCase):
    async def test_partial_results_still_delivered_and_reported(self):
        db_path = Path(tempfile.mkdtemp()) / "test.db"
        db = VacancyDatabase(db_path)
        db.set_subscriber_roles(10, ["qa_manual"])
        db.set_subscriber_roles(11, ["product_designer"])
        bot = AsyncMock()
        service = SubscriberService(_settings(db_path), db, bot)

        async def collect(settings, role):
            vacancy = Vacancy(source="hh.ru", external_id=role.id, title=f"Вакансия {role.id}",
                              company="К", url=f"https://hh.ru/vacancy/{role.id}",
                              published_at=datetime.now(timezone.utc))
            if role.id == "qa_manual":
                raise SourceLimited("hh.ru", [vacancy])
            return [vacancy]

        with mock.patch("bot.subscriber_service.collect_for_role", side_effect=collect):
            stats = await service.run_daily_digests()

        self.assertEqual(stats.limited_roles, ["qa_manual"])
        self.assertEqual(stats.failed_roles, [])
        recipients = sorted(c.kwargs["chat_id"] for c in bot.send_message.await_args_list)
        self.assertEqual(recipients, [10, 11], "неполная подборка всё равно доставлена")


class _FlakySession:
    """Сначала отдаёт заданные ошибки/статусы, потом 200."""

    def __init__(self, failures) -> None:
        self.failures = list(failures)
        self.calls = 0

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        if self.failures:
            failure = self.failures.pop(0)
            if isinstance(failure, BaseException):
                raise failure
            return _Response(failure)
        return _Ok()


class _Ok(_Response):
    def __init__(self) -> None:
        super().__init__(200)

    async def json(self):
        return {"items": [], "pages": 1}


class HHNetworkFailureTest(unittest.IsolatedAsyncioTestCase):
    """Аудит 25.10.2026: обрыв сети ронял всю роль, 5xx тихо давал «собрано целиком»."""

    async def asyncSetUp(self) -> None:
        self.parser = HHParser(_settings())
        sleep = mock.patch("bot.parsers.hh.asyncio.sleep", new=AsyncMock())
        sleep.start()
        self.addCleanup(sleep.stop)

    async def _search(self, session):
        return await self.parser._search(session, {}, {"text": "x"}, matcher=lambda t: True,
                                         max_pages=1, forbidden=False)

    async def test_connection_reset_is_retried(self):
        import aiohttp
        session = _FlakySession([aiohttp.ClientConnectionError("reset")])
        await self._search(session)
        self.assertEqual(session.calls, 2)
        self.assertFalse(self.parser.incomplete)

    async def test_timeout_and_502_are_retried(self):
        import asyncio
        session = _FlakySession([asyncio.TimeoutError(), 502])
        await self._search(session)
        self.assertEqual(session.calls, 3)
        self.assertFalse(self.parser.incomplete)

    async def test_persistent_failure_marks_incomplete_without_raising(self):
        import aiohttp
        session = _FlakySession([aiohttp.ClientConnectionError("down")] * 10)
        await self._search(session)
        self.assertEqual(session.calls, 3)
        self.assertTrue(self.parser.incomplete)
        self.assertFalse(self.parser.forbidden_hit)

    async def test_400_is_not_retried_but_marks_incomplete(self):
        session = _FlakySession([400])
        await self._search(session)
        self.assertEqual(session.calls, 1)
        self.assertTrue(self.parser.incomplete)

    async def test_incomplete_hh_makes_role_limited_not_failed(self):
        vacancy = Vacancy(source="hh.ru", external_id="1", title="Python-разработчик", company="А",
                          url="https://hh.ru/vacancy/1", published_at=datetime.now(timezone.utc))
        with mock.patch("bot.subscriber_collect._fetch_hh",
                        new=AsyncMock(return_value=([vacancy], "часть запросов не прошла (сеть или 5xx)"))), \
             mock.patch("bot.subscriber_collect._fetch_habr", new=AsyncMock(return_value=[])), \
             mock.patch("bot.subscriber_collect._fetch_geekjob", new=AsyncMock(return_value=[])), \
             mock.patch("bot.subscriber_collect._fetch_getmatch", new=AsyncMock(return_value=[])), \
             mock.patch("bot.subscriber_collect._fetch_himalayas", new=AsyncMock(return_value=[])), \
             mock.patch("bot.subscriber_collect._fetch_wwr", new=AsyncMock(return_value=[])), \
             mock.patch("bot.subscriber_collect._fetch_jobicy", new=AsyncMock(return_value=[])):
            with self.assertRaises(SourceLimited) as ctx:
                await collect_for_role(_settings(), get_role("backend_python"))
        self.assertEqual([v.uid for v in ctx.exception.vacancies], ["hh.ru:1"])


if __name__ == "__main__":
    unittest.main()


class HHBreakerTest(unittest.IsolatedAsyncioTestCase):
    """Ревью 25.10.2026: без предохранителя лежащий HH растягивал сбор на часы."""

    async def asyncSetUp(self) -> None:
        sleep = mock.patch("bot.parsers.hh.asyncio.sleep", new=AsyncMock())
        sleep.start()
        self.addCleanup(sleep.stop)

    async def test_hh_down_stops_requests_for_other_roles(self):
        import aiohttp
        session = _FlakySession([aiohttp.ClientConnectionError("down")] * 1000)
        for _ in range(10):  # 10 ролей
            parser = HHParser(_settings())
            await parser._search(session, {}, {"text": "x"}, matcher=lambda t: True,
                                 max_pages=1, forbidden=False)
            self.assertTrue(parser.incomplete)
        # 3 страницы × 3 попытки до срабатывания, дальше — ни одного запроса.
        self.assertEqual(session.calls, 9)

    async def test_success_resets_failures(self):
        import aiohttp
        from bot.parsers import hh
        session = _FlakySession([aiohttp.ClientConnectionError("x")] * 3)
        await HHParser(_settings())._search(session, {}, {"text": "x"}, matcher=lambda t: True,
                                            max_pages=1, forbidden=False)
        await HHParser(_settings())._search(session, {}, {"text": "x"}, matcher=lambda t: True,
                                            max_pages=1, forbidden=False)
        self.assertEqual(hh._breaker["failures"], 0)
        self.assertFalse(hh._hh_paused())


class _RecordingSession:
    """Запоминает параметры запросов и отдаёт заданное число страниц."""

    def __init__(self, pages: int = 1) -> None:
        self.pages = pages
        self.calls: list[list] = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(list(params or []))
        pages = self.pages

        class _Page(_Response):
            async def json(self_inner):
                return {"items": [{"id": "1"}], "pages": pages}

        return _Page(200)


class CombinedQueriesTest(unittest.IsolatedAsyncioTestCase):
    """Сбор для подписчиков: все страны и компании одним запросом (26.10.2026)."""

    async def asyncSetUp(self) -> None:
        sleep = mock.patch("bot.parsers.hh.asyncio.sleep", new=AsyncMock())
        sleep.start()
        self.addCleanup(sleep.stop)

    async def _run(self, coro_factory, pages=1):
        session = _RecordingSession(pages)

        class _Ctx:
            async def __aenter__(self_inner):
                return session

            async def __aexit__(self_inner, *exc):
                return False

        with mock.patch("bot.parsers.hh.aiohttp.ClientSession", return_value=_Ctx()), \
             mock.patch.object(HHParser, "_parse_item", return_value=None):
            await coro_factory(HHParser(_settings()))
        return session

    async def test_one_request_per_phrase_with_all_areas(self):
        from bot.config import HH_AREAS
        session = await self._run(lambda p: p.fetch_for_queries(("python", "django"), lambda t: True))
        self.assertEqual(len(session.calls), 2)
        areas = [v for k, v in session.calls[0] if k == "area"]
        self.assertEqual(areas, [str(a) for a in HH_AREAS])

    async def test_old_mode_still_available(self):
        from bot.config import HH_AREAS
        session = await self._run(lambda p: p.fetch_for_queries(("python",), lambda t: True, combined=False))
        self.assertEqual(len(session.calls), len(HH_AREAS))

    async def test_bigtech_one_request_per_phrase_with_all_employers(self):
        session = await self._run(lambda p: p.fetch_bigtech(lambda t: True, ("python",)))
        self.assertEqual(len(session.calls), 1)
        employers = [v for k, v in session.calls[0] if k == "employer_id"]
        self.assertEqual(employers, [str(e) for _, e in BIGTECH_HH_EMPLOYERS])

    async def test_reads_up_to_20_pages(self):
        session = await self._run(lambda p: p.fetch_for_queries(("python",), lambda t: True), pages=50)
        self.assertEqual(len(session.calls), 20)
        self.assertEqual([v for k, v in session.calls[-1] if k == "page"], ["19"])

    async def test_channel_fetch_unchanged(self):
        from bot.config import HH_AREAS, SEARCH_QUERIES
        session = await self._run(lambda p: p.fetch())
        main_search = [c for c in session.calls if ("search_field", "name") in c]
        self.assertEqual(len(main_search), len(HH_AREAS) * len(SEARCH_QUERIES))
        self.assertTrue(all(sum(k == "area" for k, _ in c) == 1 for c in main_search))
