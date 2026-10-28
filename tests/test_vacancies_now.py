"""Кнопка «🔎 Вакансии сейчас»: подборка из утреннего сбора без нового опроса HH."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from unittest.mock import AsyncMock

from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup

from bot import chat_main
from bot.config import Settings
from bot.database import VacancyDatabase
from bot.menu import BTN_NOW, main_menu_keyboard
from bot.models import Vacancy
from bot.subscriber_service import SubscriberService


def _v(n, title="Python-разработчик", hours_ago=1):
    return Vacancy(source="hh.ru", external_id=str(n), title=f"{title} {n}", company=f"К{n}",
                   url=f"https://hh.ru/vacancy/{n}", published_at=datetime.now(timezone.utc) - timedelta(hours=hours_ago))


class _Bot:
    def __init__(self):
        self.calls = []

    async def send_message(self, chat_id, text, **kw):
        self.calls.append((chat_id, text, kw.get("reply_markup")))
        return SimpleNamespace(chat=SimpleNamespace(type="private", username=None, first_name="И", last_name=None))


class VacanciesNowTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.path = Path(tempfile.mkdtemp()) / "t.db"
        self.db = VacancyDatabase(self.path)
        self.settings = Settings(telegram_bot_token="1:t", telegram_chat_id=-1, hh_user_agent="t/1",
                                 hh_access_token="", timezone="Europe/Moscow", max_vacancy_age_hours=72,
                                 db_path=self.path, telegram_admin_id=None)
        self.bot = _Bot()
        self.service = SubscriberService(self.settings, self.db, self.bot)
        sleep = mock.patch("bot.subscriber_service.asyncio.sleep", new=AsyncMock())
        sleep.start()
        self.addCleanup(sleep.stop)
        chat_main._now_pressed_at.clear()

    async def test_new_subscriber_gets_vacancies_right_away(self):
        self.db.save_role_cache({"backend_python": [_v(1), _v(2)], "backend_go": [_v(3, "Go-разработчик")]}, [])
        self.db.set_subscriber_roles(10, ["backend_python"])
        self.assertEqual(await self.service.send_now(10), "sent")
        text = " ".join(t for _, t, _ in self.bot.calls)
        self.assertIn("Python-разработчик 1", text)
        self.assertNotIn("Go-разработчик", text)
        self.assertTrue(self.db.is_sent_to_subscriber(10, "hh.ru:1"))

    async def test_second_press_has_nothing_new(self):
        self.db.save_role_cache({"backend_python": [_v(1)]}, [])
        self.db.set_subscriber_roles(10, ["backend_python"])
        await self.service.send_now(10)
        self.assertEqual(await self.service.send_now(10), "nothing_new")

    async def test_stale_vacancies_are_not_sent(self):
        self.db.save_role_cache({"backend_python": [_v(1, hours_ago=80)]}, [])
        self.db.set_subscriber_roles(10, ["backend_python"])
        self.assertEqual(await self.service.send_now(10), "nothing_new")

    async def test_no_cache_yet_and_not_subscribed(self):
        self.db.set_subscriber_roles(10, ["backend_python"])
        self.assertEqual(await self.service.send_now(10), "no_cache")
        self.assertEqual(await self.service.send_now(99), "not_subscribed")

    async def test_morning_digest_fills_cache(self):
        self.db.set_subscriber_roles(10, ["backend_python"])

        async def collect(settings, role):
            return [_v(5)]
        with mock.patch("bot.subscriber_service.collect_for_role", side_effect=collect):
            await self.service.run_daily_digests()
        self.assertEqual([v.uid for v in self.db.load_role_cache(["backend_python"])["backend_python"]], ["hh.ru:5"])

    async def test_cache_save_failure_does_not_break_digest(self):
        self.db.set_subscriber_roles(10, ["backend_python"])

        async def collect(settings, role):
            return [_v(5)]
        with mock.patch("bot.subscriber_service.collect_for_role", side_effect=collect), \
             mock.patch.object(self.db, "save_role_cache", side_effect=RuntimeError("disk full")):
            stats = await self.service.run_daily_digests()
        self.assertEqual(stats.failed_users, [])
        self.assertTrue(any(c == 10 for c, _, _ in self.bot.calls))

    async def test_digest_brings_menu_with_the_new_button(self):
        self.db.set_subscriber_roles(10, ["backend_python"])

        async def collect(settings, role):
            return [_v(5)]
        with mock.patch("bot.subscriber_service.collect_for_role", side_effect=collect):
            await self.service.run_daily_digests()
        markup = self.bot.calls[0][2]
        self.assertIsInstance(markup, ReplyKeyboardMarkup)
        self.assertEqual(markup.keyboard[0][0].text, BTN_NOW)

    async def test_overflow_digest_still_has_show_more_button(self):
        self.db.set_subscriber_roles(10, ["backend_python"])

        async def collect(settings, role):
            return [_v(n) for n in range(40)]
        with mock.patch("bot.subscriber_service.collect_for_role", side_effect=collect):
            await self.service.run_daily_digests()
        self.assertTrue(any(isinstance(m, InlineKeyboardMarkup) for _, _, m in self.bot.calls))

    async def test_button_handler_and_cooldown(self):
        self.db.save_role_cache({"backend_python": [_v(1)]}, [])
        self.db.set_subscriber_roles(10, ["backend_python"])
        msg = SimpleNamespace(text=BTN_NOW, from_user=SimpleNamespace(id=10), answer=AsyncMock())
        await chat_main.btn_now(msg, self.db, self.settings, self.bot)
        self.assertTrue(self.bot.calls, "подборка ушла")
        msg.answer.assert_not_awaited()
        await chat_main.btn_now(msg, self.db, self.settings, self.bot)
        self.assertIn("Только что отправил", msg.answer.await_args.args[0])

    async def test_button_handler_explains_nothing_new(self):
        self.db.save_role_cache({"backend_python": []}, [])
        self.db.set_subscriber_roles(10, ["backend_python"])
        msg = SimpleNamespace(text=BTN_NOW, from_user=SimpleNamespace(id=10), answer=AsyncMock())
        await chat_main.btn_now(msg, self.db, self.settings, self.bot)
        self.assertIn("Новых вакансий пока нет", msg.answer.await_args.args[0])

    def test_menu_has_button_first(self):
        self.assertEqual(main_menu_keyboard(True).keyboard[0][0].text, BTN_NOW)

    def test_button_is_routed_before_fallback(self):
        names = [h.callback.__name__ for h in chat_main.router.message.handlers]
        self.assertLess(names.index("btn_now"), names.index("fallback"))


if __name__ == "__main__":
    unittest.main()


class ReviewFixesTest(VacanciesNowTest):
    """Независимое ревью 28.10.2026."""

    async def test_button_waits_while_morning_digest_runs(self):
        import fcntl
        lock_path = Path(tempfile.mkdtemp()) / "digest.lock"
        with mock.patch.object(chat_main, "DIGEST_LOCK", lock_path):
            holder = open(lock_path, "w")
            fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)  # как run_once
            self.db.save_role_cache({"backend_python": [_v(1)]}, [])
            self.db.set_subscriber_roles(10, ["backend_python"])
            msg = SimpleNamespace(text=BTN_NOW, from_user=SimpleNamespace(id=10), answer=AsyncMock())
            await chat_main.btn_now(msg, self.db, self.settings, self.bot)
            self.assertIn("рассылка идёт прямо сейчас", msg.answer.await_args.args[0])
            self.assertEqual(self.bot.calls, [])
            holder.close()
            await chat_main.btn_now(msg, self.db, self.settings, self.bot)
            self.assertTrue(self.bot.calls, "после рассылки кнопка работает")

    async def test_failed_role_keeps_previous_cache(self):
        self.db.save_role_cache({"backend_python": [_v(1)]}, [])
        self.db.set_subscriber_roles(10, ["backend_python"])

        async def collect(settings, role):
            raise RuntimeError("HH лежит")
        with mock.patch("bot.subscriber_service.collect_for_role", side_effect=collect):
            await self.service.run_daily_digests()
        self.assertEqual([v.uid for v in self.db.load_role_cache(["backend_python"])["backend_python"]], ["hh.ru:1"])
