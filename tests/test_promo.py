"""Платное размещение вакансий (bot/promo.py, /promo_*, рассылка)."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from unittest.mock import AsyncMock

from bot.chat_main import cmd_promo_add, cmd_promo_list, cmd_promo_stop
from bot.config import Settings
from bot.database import VacancyDatabase
from bot.models import Vacancy
from bot.promo import format_promo, parse_promo
from bot.subscriber_service import SubscriberService

ADMIN = 777
GOOD = """/promo_add
роли: design, devops
дней: 7
должность: Senior Product Designer
компания: Ozon
зарплата: от 300 000 ₽
формат: удалённо
ссылка: https://job.ozon.ru/1
erid: 2SDnjeTEST"""


def _settings(path: Path) -> Settings:
    return Settings(telegram_bot_token="1:t", telegram_chat_id=-1, hh_user_agent="t/1", hh_access_token="",
                    timezone="Europe/Moscow", max_vacancy_age_hours=72, db_path=path, telegram_admin_id=ADMIN)


class ParseTest(unittest.TestCase):
    def test_good_command(self):
        promo, errors = parse_promo(GOOD)
        self.assertEqual(errors, [])
        self.assertIn("product_designer", promo.roles)  # раздел «design» целиком
        self.assertIn("devops", promo.roles)
        self.assertEqual(promo.days, 7)
        self.assertEqual(promo.erid, "2SDnjeTEST")

    def test_errors_are_human(self):
        promo, errors = parse_promo("/promo_add\nроли: designn\nдней: 100\nссылка: ozon.ru")
        self.assertIsNone(promo)
        text = "; ".join(errors)
        for part in ("нет поля «должность»", "нет поля «компания»", "неизвестные роли: designn",
                     "от 1 до 60", "https://"):
            self.assertIn(part, text)

    def test_format_is_marked_as_ad_and_escaped(self):
        promo, _ = parse_promo(GOOD.replace("Ozon", "<Ozon & Co>").replace("/1", '/1"onclick='))
        text = format_promo(promo)
        self.assertTrue(text.startswith("📌 <i>Реклама · Партнёрская вакансия</i>"))
        self.assertIn("&lt;Ozon &amp; Co&gt;", text)
        self.assertIn("erid: 2SDnjeTEST", text)
        self.assertIn('href="https://job.ozon.ru/1&quot;onclick="', text)


class AdminCommandsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.path = Path(tempfile.mkdtemp()) / "t.db"
        self.db = VacancyDatabase(self.path)
        self.settings = _settings(self.path)
        self.db.set_subscriber_roles(1, ["product_designer"])
        self.db.set_subscriber_roles(2, ["devops", "backend_go"])
        self.db.set_subscriber_roles(3, ["backend_go"])

    def _msg(self, text, user=ADMIN):
        return SimpleNamespace(text=text, from_user=SimpleNamespace(id=user), answer=AsyncMock())

    async def test_add_reports_audience_and_preview(self):
        msg = self._msg(GOOD)
        await cmd_promo_add(msg, self.db, self.settings)
        first = msg.answer.await_args_list[0].args[0]
        self.assertIn("Размещение №1", first)
        self.assertIn("<b>2</b>", first)  # дизайнер и devops; go-разработчик — нет
        self.assertIn("Партнёрская вакансия", msg.answer.await_args_list[1].args[0])

    async def test_not_admin_is_refused(self):
        msg = self._msg(GOOD, user=5)
        await cmd_promo_add(msg, self.db, self.settings)
        self.assertEqual(self.db.list_promos(), [])
        self.assertIn("только для администратора", msg.answer.await_args.args[0])

    async def test_bare_command_shows_help(self):
        msg = self._msg("/promo_add")
        await cmd_promo_add(msg, self.db, self.settings)
        self.assertIn("каждое поле с новой строки", msg.answer.await_args.args[0])
        self.assertNotIn("Не получилось", msg.answer.await_args.args[0])

    async def test_list_and_stop(self):
        await cmd_promo_add(self._msg(GOOD), self.db, self.settings)
        lst = self._msg("/promo_list")
        await cmd_promo_list(lst, self.db, self.settings)
        self.assertIn("доставлено <b>0</b> из 2", lst.answer.await_args.args[0])
        stop = self._msg("/promo_stop 1")
        await cmd_promo_stop(stop, self.db, self.settings)
        self.assertIn("снято", stop.answer.await_args.args[0])
        self.assertIsNone(self.db.next_promo_for(1, ["product_designer"]))


class _Bot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text))
        return SimpleNamespace(chat=SimpleNamespace(type="private", username=None, first_name="И", last_name=None))


class DigestPromoTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.path = Path(tempfile.mkdtemp()) / "t.db"
        self.db = VacancyDatabase(self.path)
        self.settings = _settings(self.path)
        self.db.set_subscriber_roles(1, ["product_designer"])
        self.db.set_subscriber_roles(2, ["backend_go"])
        promo, _ = parse_promo(GOOD)
        self.db.add_promo(promo)
        sleep = mock.patch("bot.subscriber_service.asyncio.sleep", new=AsyncMock())
        sleep.start()
        self.addCleanup(sleep.stop)

    async def _run(self):
        bot = _Bot()
        found = [Vacancy(source="hh.ru", external_id="1", title="Продуктовый дизайнер", company="VK",
                         url="https://hh.ru/1", published_at=datetime.now(timezone.utc))]

        async def collect(settings, role):
            return list(found)
        with mock.patch("bot.subscriber_service.collect_for_role", side_effect=collect):
            stats = await SubscriberService(self.settings, self.db, bot).run_daily_digests()
        return bot, stats

    async def test_promo_goes_first_only_to_matching_roles_and_once(self):
        bot, stats = await self._run()
        to_designer = [t for c, t in bot.sent if c == 1]
        self.assertIn("Партнёрская вакансия", to_designer[0])
        self.assertIn("новых вакансий", to_designer[1].lower())
        self.assertFalse(any("Партнёрская" in t for c, t in bot.sent if c == 2))
        self.assertEqual(stats.promos_sent, 1)

        bot, stats = await self._run()  # завтра
        self.assertFalse(any("Партнёрская" in t for c, t in bot.sent))

    async def test_expired_or_stopped_promo_is_not_sent(self):
        self.db.stop_promo(1)
        bot, stats = await self._run()
        self.assertEqual(stats.promos_sent, 0)


class BrokenPromoTest(DigestPromoTest):
    async def test_broken_promo_never_blocks_the_digest(self):
        """Ревью: падение рекламы не должно лишать подборки и останавливать рассылку."""
        with mock.patch("bot.subscriber_service.format_promo", side_effect=RuntimeError("битая реклама")):
            bot, stats = await self._run()
        self.assertTrue(any(c == 1 for c, _ in bot.sent), "дизайнер получил подборку")
        self.assertTrue(any(c == 2 for c, _ in bot.sent), "и остальные тоже")
        self.assertEqual(stats.failed_users, [])
        self.assertEqual(stats.promos_sent, 0)
