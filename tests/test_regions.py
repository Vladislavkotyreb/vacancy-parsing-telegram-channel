"""Регион поиска: СНГ, удалёнка по миру или оба. Площадки «мира» и шаг /start."""

from __future__ import annotations

import tempfile
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from unittest.mock import AsyncMock

from bot.chat_main import (
    S0_REGION,
    region_keyboard,
    s0_pick_region,
    send_subscription_info,
    start_flow,
)
from bot.config import Settings
from bot.database import VacancyDatabase
from bot.models import Vacancy
from bot.parsers import world_remote
from bot.regions import BOTH, CIS, WORLD, for_region
from bot.subscriber_service import SubscriberService

NOW = datetime.now(timezone.utc)


def _v(source: str, title: str, n: int) -> Vacancy:
    return Vacancy(source=source, external_id=str(n), title=title, company=f"Компания {n}",
                   url=f"https://example.com/{n}", published_at=NOW - timedelta(hours=1))


class WorldParsersTest(unittest.TestCase):
    def test_himalayas_only_worldwide(self):
        base = {"title": "Senior Product Designer", "companyName": "Acme &amp; Co",
                "applicationLink": "https://himalayas.app/companies/acme/jobs/senior-product-designer",
                "pubDate": str(int(NOW.timestamp())), "minSalary": "90000", "maxSalary": "120000",
                "currency": "USD", "salaryPeriod": "yearly"}
        v = world_remote.parse_himalayas({**base, "locationRestrictions": "[]"})
        self.assertEqual(v.source, "himalayas.app")
        self.assertEqual(v.company, "Acme & Co")
        self.assertEqual(v.salary, "90 000–120 000 USD в год")
        self.assertEqual(v.location, "Удалённо, весь мир")
        self.assertEqual(v.grade, "Senior")
        self.assertIsNone(world_remote.parse_himalayas({**base, "locationRestrictions": "['United States']"}))

    def test_wwr_only_anywhere_and_title_split(self):
        def item(region):
            return ET.fromstring(
                f"<item><title>Acme: Senior Product Manager</title><region>{region}</region>"
                "<link>https://weworkremotely.com/remote-jobs/acme-senior-pm</link>"
                "<pubDate>Fri, 23 Oct 2026 16:55:36 +0000</pubDate></item>")
        v = world_remote.parse_wwr(item("Anywhere in the World"))
        self.assertEqual((v.company, v.title), ("Acme", "Senior Product Manager"))
        self.assertEqual(v.published_at, datetime(2026, 10, 23, 16, 55, 36, tzinfo=timezone.utc))
        self.assertIsNone(world_remote.parse_wwr(item("USA Only")))

    def test_jobicy_only_anywhere(self):
        base = {"id": 7, "jobTitle": "QA Engineer", "companyName": "Acme",
                "url": "https://jobicy.com/jobs/7-qa", "pubDate": "2026-10-23T18:57:36+00:00",
                "salaryMin": "", "salaryMax": ""}
        self.assertEqual(world_remote.parse_jobicy({**base, "jobGeo": "Anywhere"}).title, "QA Engineer")
        self.assertIsNone(world_remote.parse_jobicy({**base, "jobGeo": "USA"}))
        self.assertIsNone(world_remote.parse_jobicy({**base, "jobGeo": "Anywhere"}).salary)


class RegionFilterTest(unittest.TestCase):
    MIX = [_v("hh.ru", "A", 1), _v("career.habr.com", "B", 2), _v("himalayas.app", "C", 3),
           _v("weworkremotely.com", "D", 4), _v("jobicy.com", "E", 5)]

    def titles(self, region):
        return [v.title for v in for_region(self.MIX, region)]

    def test_split(self):
        self.assertEqual(self.titles(CIS), ["A", "B"])
        self.assertEqual(self.titles(WORLD), ["C", "D", "E"])
        self.assertEqual(self.titles(BOTH), ["A", "B", "C", "D", "E"])
        self.assertEqual(self.titles("что-то странное"), ["A", "B"])  # по умолчанию СНГ


def _settings(db_path: Path) -> Settings:
    return Settings(
        telegram_bot_token="test:token", telegram_chat_id=-100123, hh_user_agent="test/1.0",
        hh_access_token="", timezone="Europe/Moscow", max_vacancy_age_hours=72,
        db_path=db_path, telegram_admin_id=None,
    )


class DigestByRegionTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        path = Path(tempfile.mkdtemp()) / "test.db"
        self.db = VacancyDatabase(path)
        self.bot = AsyncMock()
        self.service = SubscriberService(_settings(path), self.db, self.bot)
        for user_id in (1, 2, 3):
            self.db.set_subscriber_roles(user_id, ["product_designer"])
        self.db.set_region(2, WORLD)
        self.db.set_region(3, BOTH)  # 1 не выбирал — значит СНГ

    async def run_digest(self):
        async def collect(settings, role):
            return [_v("hh.ru", "Продуктовый дизайнер СНГ", 1),
                    _v("himalayas.app", "Senior Product Designer World", 2)]
        with mock.patch("bot.subscriber_service.collect_for_role", side_effect=collect):
            await self.service.run_daily_digests()

    def text_for(self, user_id):
        return " ".join(c.kwargs["text"] for c in self.bot.send_message.await_args_list
                        if c.kwargs["chat_id"] == user_id)

    async def test_each_region_gets_its_sources(self):
        await self.run_digest()
        cis, world, both = self.text_for(1), self.text_for(2), self.text_for(3)
        self.assertIn("СНГ", cis)
        self.assertNotIn("World", cis)
        self.assertIn("World", world)
        self.assertNotIn("Продуктовый дизайнер СНГ", world)
        self.assertIn("СНГ", both)
        self.assertIn("World", both)

    async def test_header_lists_region_sources(self):
        await self.run_digest()
        self.assertIn("Источники: HeadHunter, Хабр Карьера, GeekJob, GetMatch\n", self.text_for(1))
        self.assertIn("Источники: Himalayas, We Work Remotely, Jobicy", self.text_for(2))
        self.assertIn("HeadHunter", self.text_for(3))
        self.assertIn("Himalayas", self.text_for(3))
        self.assertIn("🔗 Himalayas", self.text_for(2))


class RegionStepTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = VacancyDatabase(Path(tempfile.mkdtemp()) / "test.db")

    def test_default_is_cis_and_unknown_is_normalized(self):
        self.assertEqual(self.db.get_region(10), CIS)
        self.db.set_region(10, "mars")
        self.assertEqual(self.db.get_region(10), CIS)
        self.db.set_region(10, WORLD)
        self.assertEqual(self.db.get_region(10), WORLD)

    def test_keyboard_marks_current_and_fits_limit(self):
        rows = region_keyboard(WORLD).inline_keyboard
        texts = [row[0].text for row in rows]
        self.assertEqual(texts, ["СНГ", "✓ Удалёнка по миру", "СНГ + удалёнка по миру"])
        for row in rows:
            self.assertLessEqual(len(row[0].callback_data.encode()), 64)

    async def test_start_asks_region_first(self):
        message = SimpleNamespace(from_user=SimpleNamespace(id=10), answer=AsyncMock())
        await start_flow(message, self.db)
        self.assertIn("Шаг 1 из 3", message.answer.await_args.args[0])
        markup = message.answer.await_args.kwargs["reply_markup"]
        self.assertEqual(markup.inline_keyboard[0][0].text, "✓ СНГ")

    async def test_pick_saves_region_and_goes_to_specialty(self):
        message = SimpleNamespace(edit_text=AsyncMock())
        callback = SimpleNamespace(data=f"{S0_REGION}{BOTH}", from_user=SimpleNamespace(id=10),
                                   message=message, answer=AsyncMock())
        await s0_pick_region(callback, self.db)
        self.assertEqual(self.db.get_region(10), BOTH)
        self.assertIn("Шаг 2 из 3", message.edit_text.await_args.args[0])

    async def test_my_subscription_shows_region(self):
        self.db.set_subscriber_roles(10, ["backend_php"])
        self.db.set_region(10, WORLD)
        message = SimpleNamespace(from_user=SimpleNamespace(id=10), answer=AsyncMock())
        await send_subscription_info(message, self.db)
        self.assertIn("Где ищу: <b>Удалёнка по миру</b>", message.answer.await_args.args[0])


if __name__ == "__main__":
    unittest.main()


class WorldBugsTest(unittest.IsolatedAsyncioTestCase):
    def test_qa_automation_needs_qa_context(self):
        from bot.role_filters import is_qa_automation_vacancy as qa
        self.assertFalse(qa("Sales Development Representative - CRM, Conversational AI & Messaging Automation"))
        self.assertFalse(qa("Marketing Automation Manager"))
        for title in ("QA Engineer (Automation)", "Test Automation Engineer", "Automation QA",
                      "Automation Engineer (Python)", "Senior SDET / Automation"):
            self.assertTrue(qa(title), title)

    def test_himalayas_id_from_job_page_not_slug(self):
        # Одинаковый адрес вакансии у разных компаний — разные вакансии.
        def item(company):
            return {"title": "Paid Ads Specialist", "companyName": company, "locationRestrictions": "[]",
                    "pubDate": str(int(NOW.timestamp())),
                    "guid": f"https://himalayas.app/companies/{company}/jobs/paid-ads-specialist",
                    "applicationLink": f"https://himalayas.app/companies/{company}/jobs/paid-ads-specialist?utm_source=api"}
        a, b = world_remote.parse_himalayas(item("acme")), world_remote.parse_himalayas(item("globex"))
        self.assertNotEqual(a.uid, b.uid)
        self.assertNotIn("utm_source", a.url)

    async def test_old_pinned_job_on_first_page_does_not_stop_paging(self):
        pages = []

        class Resp:
            def __init__(self, data):
                self.status, self._data = 200, data
            async def json(self):
                return self._data
            async def __aenter__(self):
                return self
            async def __aexit__(self, *exc):
                return False

        class Session:
            def __init__(self, *a, **k):
                pass
            def get(self, url, params=None):
                page = params["page"]
                pages.append(page)
                def job(n, hours):
                    return {"title": f"Job {n}", "companyName": "c", "locationRestrictions": "[]",
                            "guid": f"https://himalayas.app/companies/c/jobs/{n}",
                            "pubDate": str(int((NOW - timedelta(hours=hours)).timestamp()))}
                if page == 1:  # закреплённая вакансия недельной давности + свежие
                    return Resp({"jobs": [job(0, 24 * 7), job(1, 1), job(2, 2)]})
                if page == 2:
                    return Resp({"jobs": [job(3, 10), job(4, 30)]})
                return Resp({"jobs": [job(5, 100), job(6, 110)]})
            async def __aenter__(self):
                return self
            async def __aexit__(self, *exc):
                return False

        import aiohttp
        with mock.patch("bot.parsers.world_remote.aiohttp.ClientSession", Session), \
             mock.patch("bot.parsers.world_remote.PAGE_PAUSE_SEC", 0):
            jobs = await world_remote.fetch_himalayas(72, aiohttp.ClientTimeout(total=5))
        self.assertEqual(pages, [1, 2, 3])  # дошли до страницы, где свежих не осталось
        self.assertEqual(len(jobs), 7)


class WorldTitleNoiseTest(unittest.TestCase):
    def test_region_only_and_ai_gigs_are_dropped(self):
        def himalayas(title):
            return world_remote.parse_himalayas({
                "title": title, "companyName": "c", "locationRestrictions": "[]",
                "pubDate": str(int(NOW.timestamp())), "guid": "https://himalayas.app/companies/c/jobs/x"})
        for title in ("Data Engineering Tech Lead (LatAm Only)", "Senior Product Designer (US)",
                      "QA Engineer – Creative Automation (100% Remote) (LATAM", "Life Sciences Research Expert (Python)",
                      "AI Tutor — Python"):
            self.assertIsNone(himalayas(title), title)
        for title in ("Senior Product Designer", "Join us: Product Manager", "Data Engineer (Remote)"):
            self.assertIsNotNone(himalayas(title), title)

    def test_workflow_automation_is_not_qa(self):
        from bot.role_filters import is_qa_automation_vacancy as qa
        self.assertFalse(qa("Workflow Automation Engineer"))
        self.assertFalse(qa("AI Automation Engineer"))
        self.assertTrue(qa("Senior Automation Engineer"))
