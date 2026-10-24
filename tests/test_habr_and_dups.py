"""Хабр Карьера в подписках и склейка одной вакансии с разных площадок.

Пары — из живой выдачи 24.10.2026 (Хабр ↔ HH ↔ GetMatch)."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
from unittest.mock import AsyncMock

import aiohttp

from bot.config import Settings
from bot.cross_source import dedupe_across_sources, merge_key
from bot.database import VacancyDatabase
from bot.formatters import format_digest_header, format_vacancy
from bot.models import Vacancy
from bot.parsers import habr_career
from bot.roles import get_role
from bot.subscriber_collect import collect_for_role, shared_feeds

NOW = datetime.now(timezone.utc)


def _v(source: str, title: str, company: str, n: int = 1, hours_ago: float = 1) -> Vacancy:
    return Vacancy(source=source, external_id=f"{source}-{n}", title=title, company=company,
                   url=f"https://example.com/{source}/{n}", published_at=NOW - timedelta(hours=hours_ago))


def _habr_item(n: int, title: str = "Python-разработчик", hours_ago: float = 1, **extra) -> dict:
    item = {
        "id": 1000000 + n, "href": f"/vacancies/{1000000 + n}", "title": title,
        "company": {"title": "Контур"}, "remoteWork": True, "qualification": "Middle",
        "salary": {"from": 200000, "to": None, "formatted": "от 200 000 ₽"},
        "publishedDate": {"date": (NOW - timedelta(hours=hours_ago)).isoformat()},
        "locations": None, "archived": False, "hidden": False,
    }
    item.update(extra)
    return item


def _settings() -> Settings:
    return Settings(
        telegram_bot_token="test:token", telegram_chat_id=-100123, hh_user_agent="test/1.0",
        hh_access_token="", timezone="Europe/Moscow", max_vacancy_age_hours=72,
        db_path=Path("/tmp/unused.db"), telegram_admin_id=None,
    )


class HabrParseTest(unittest.TestCase):
    def test_fields(self):
        v = habr_career.parse_item(_habr_item(1, title="Senior Go-разработчик"))
        self.assertEqual(v.source, "career.habr.com")
        self.assertEqual(v.url, "https://career.habr.com/vacancies/1000001")
        self.assertEqual(v.company, "Контур")
        self.assertEqual(v.salary, "от 200 000 ₽")
        self.assertEqual(v.work_format, "Удалённо")
        self.assertEqual(v.location, "Удалённо")
        self.assertEqual(v.grade, "Senior")  # из названия — важнее поля квалификации
        self.assertLess(abs((v.published_at - NOW).total_seconds() + 3600), 5)

    def test_grade_from_qualification_and_cities(self):
        v = habr_career.parse_item(_habr_item(2, qualification="Intern", remoteWork=False,
                                              locations=[{"title": "Москва"}, {"title": "Казань"}]))
        self.assertEqual(v.grade, "Стажёр")
        self.assertEqual(v.location, "Москва, Казань")
        self.assertIsNone(v.work_format)

    def test_archived_hidden_and_empty_are_skipped(self):
        self.assertIsNone(habr_career.parse_item(_habr_item(3, archived=True)))
        self.assertIsNone(habr_career.parse_item(_habr_item(4, hidden=True)))
        self.assertIsNone(habr_career.parse_item(_habr_item(5, title="  ")))

    def test_card_shows_habr_but_channel_header_does_not(self):
        card = format_vacancy(habr_career.parse_item(_habr_item(6)))
        self.assertIn("Хабр Карьера", card)
        # Канал Хабр не опрашивает — и не должен его перечислять.
        self.assertNotIn("Хабр", format_digest_header(3, 10))


class _Resp:
    def __init__(self, data, status=200):
        self.status, self._data = status, data

    async def json(self):
        return self._data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _HabrSession:
    """Страница N — вакансии возрастом 30·N часов: третья уже старше 72 ч."""

    pages: list = []

    def __init__(self, *args, **kwargs):
        pass

    def get(self, url, params=None):
        page = params["page"]
        _HabrSession.pages.append(page)
        if page > 4:
            return _Resp({"list": []})
        items = [_habr_item(page * 10 + i, hours_ago=30 * page - 5 + i * 5) for i in range(2)]
        return _Resp({"list": items})

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class HabrFetchTest(unittest.IsolatedAsyncioTestCase):
    async def test_pages_until_older_than_cutoff(self):
        _HabrSession.pages = []
        with mock.patch("bot.parsers.habr_career.aiohttp.ClientSession", _HabrSession), \
             mock.patch("bot.parsers.habr_career.PAGE_PAUSE_SEC", 0):
            vacancies = await habr_career.fetch_recent(72, aiohttp.ClientTimeout(total=5))
        self.assertEqual(_HabrSession.pages, [1, 2, 3])  # на 3-й нашлась вакансия старше 72 ч
        self.assertEqual(len(vacancies), 6)

    async def test_habr_once_per_run_and_filtered_by_role(self):
        habr = AsyncMock(return_value=[
            _v("career.habr.com", "Golang-разработчик", "Авито"),
            _v("career.habr.com", "QA Engineer", "Контур", n=2),
        ])
        with mock.patch("bot.subscriber_collect._fetch_hh", new=AsyncMock(return_value=([], False))), \
             mock.patch("bot.subscriber_collect._fetch_habr", new=habr), \
             mock.patch("bot.subscriber_collect._fetch_geekjob", new=AsyncMock(return_value=[])), \
             mock.patch("bot.subscriber_collect._fetch_getmatch", new=AsyncMock(return_value=[])), \
             shared_feeds():
            go = await collect_for_role(_settings(), get_role("backend_go"))
            qa = await collect_for_role(_settings(), get_role("qa_manual"))
        self.assertEqual(habr.await_count, 1)
        self.assertEqual([v.title for v in go], ["Golang-разработчик"])
        self.assertEqual([v.title for v in qa], ["QA Engineer"])


class CrossSourceDedupeTest(unittest.TestCase):
    def kept(self, *vacancies):
        return dedupe_across_sources(list(vacancies))

    def test_same_vacancy_different_spelling_is_merged_hh_wins(self):
        for a, b in [
            (("Data Analyst", "Сбер Банк"), ("Data Analyst", "Сбер")),
            (("Менеджер продукта по развитию голосовых и медиасервисов", "МегаФон"),
             ("Менеджер продукта по развитию голосовых и медиа сервисов", "МегаФон")),
            (("Data Engineer", "RWB (Wildberries & Russ)"), ("Data Engineer", "RWB")),
            (("Java-разработчик", "Банк ВТБ (ПАО)"), ("Java-разработчик", "Банк ВТБ")),
            (("Frontend-разработчик", "2ГИС"), ("Frontend-разработчик", "2GIS")),
            (("Go-разработчик", "«UZUM TECHNOLOGIES»"), ("Go разработчик", "UZUM")),
        ]:
            with self.subTest(a=a, b=b):
                kept = self.kept(_v("getmatch.ru", *b, n=1), _v("hh.ru", *a, n=2),
                                 _v("career.habr.com", *b, n=3))
                self.assertEqual([v.source for v in kept], ["hh.ru"])

    def test_different_vacancies_of_one_company_stay(self):
        for a, b in [
            (("ML Engineer в Поиск", "RWB"), ("ML инженер в Финтех", "RWB (Wildberries & Russ)")),
            (("Младший инженер по тестированию", "ЛАНИТ"), ("Старший инженер по тестированию", "ЛАНИТ")),
            (("ML-инженер", "ГНИВЦ"), ("ML-инженер senior", "ГНИВЦ")),  # грейд не выкидываем
            (("Product Manager", "MTS Web Services"), ("Product Manager", "МТС Банк")),
        ]:
            with self.subTest(a=a, b=b):
                self.assertEqual(len(self.kept(_v("hh.ru", *a, n=1), _v("career.habr.com", *b, n=2))), 2)

    def test_merge_key_ignores_case_quotes_legal_form(self):
        self.assertEqual(merge_key("Python Developer", 'ООО "Ромашка"'),
                         merge_key("python developer", "Ромашка"))


class SentHistoryAcrossSourcesTest(unittest.TestCase):
    def setUp(self):
        self.db_path = Path(tempfile.mkdtemp()) / "test.db"
        self.db = VacancyDatabase(self.db_path)

    def test_yesterdays_hh_vacancy_does_not_come_back_from_habr(self):
        self.db.mark_sent_to_subscriber(10, _v("hh.ru", "Data Engineer", "RWB (Wildberries & Russ)"))
        today = [_v("career.habr.com", "Data Engineer", "RWB", n=7),
                 _v("career.habr.com", "ML Engineer в Поиск", "RWB", n=8)]
        self.assertEqual([v.title for v in self.db.unsent_to_subscriber(10, today)],
                         ["ML Engineer в Поиск"])
        # Другому подписчику — приходит.
        self.assertEqual(len(self.db.unsent_to_subscriber(11, today)), 2)

    def test_old_database_gets_merge_key_column(self):
        path = Path(tempfile.mkdtemp()) / "old.db"
        conn = sqlite3.connect(path)
        conn.execute("""CREATE TABLE subscriber_sent (user_id INTEGER NOT NULL, vacancy_uid TEXT NOT NULL,
                        dedup_key TEXT, sent_at TEXT NOT NULL, PRIMARY KEY (user_id, vacancy_uid))""")
        conn.execute("INSERT INTO subscriber_sent VALUES (10, 'hh.ru:hh.ru-1', 'x y', '2026-10-23')")
        conn.commit()
        conn.close()

        db = VacancyDatabase(path)
        columns = {row[1] for row in sqlite3.connect(path).execute("PRAGMA table_info(subscriber_sent)")}
        self.assertIn("merge_key", columns)
        # Старая строка без merge_key по-прежнему защищает от повтора по id.
        self.assertEqual(db.unsent_to_subscriber(10, [_v("hh.ru", "X", "Y", n=1)]), [])


if __name__ == "__main__":
    unittest.main()
