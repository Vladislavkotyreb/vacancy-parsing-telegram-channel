"""Кнопка «🔎 Вакансии сейчас»: живой поиск по ролям подписчика и подборка непросмотренного."""

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
        self.assertEqual([c.args[0] for c in msg.answer.await_args_list], [chat_main.NOW_SEARCHING_TEXT])
        await chat_main.btn_now(msg, self.db, self.settings, self.bot)
        self.assertEqual(msg.answer.await_args.args[0], chat_main.NOW_COOLDOWN_TEXT)

    async def test_button_handler_explains_nothing_new(self):
        self.db.save_role_cache({"backend_python": []}, [])
        self.db.set_subscriber_roles(10, ["backend_python"])
        msg = SimpleNamespace(text=BTN_NOW, from_user=SimpleNamespace(id=10), answer=AsyncMock())
        await chat_main.btn_now(msg, self.db, self.settings, self.bot)
        self.assertIn("Новых вакансий пока нет", msg.answer.await_args.args[0])

    async def test_button_without_roles_does_not_search(self):
        msg = SimpleNamespace(text=BTN_NOW, from_user=SimpleNamespace(id=55), answer=AsyncMock())
        with mock.patch("bot.subscriber_service.collect_for_role", side_effect=AssertionError("не должен искать")):
            await chat_main.btn_now(msg, self.db, self.settings, self.bot)
        self.assertIn("Сначала выбери роли", msg.answer.await_args.args[0])

    def test_menu_has_button_first(self):
        self.assertEqual(main_menu_keyboard(True).keyboard[0][0].text, BTN_NOW)

    def test_button_is_routed_before_fallback(self):
        names = [h.callback.__name__ for h in chat_main.router.message.handlers]
        self.assertLess(names.index("btn_now"), names.index("fallback"))


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


def _age_cache(db, role, minutes):
    """Сделать сбор роли «старым» — как будто его собрали minutes минут назад."""
    old = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    with db._connect() as conn:
        conn.execute("UPDATE role_cache SET collected_at = ? WHERE role = ?", (old, role))


class LiveSearchTest(VacanciesNowTest):
    """По кнопке бот ищет новые вакансии сам, а не только раздаёт утренний сбор."""

    async def press(self, user_id=10):
        msg = SimpleNamespace(text=BTN_NOW, from_user=SimpleNamespace(id=user_id), answer=AsyncMock())
        await chat_main.btn_now(msg, self.db, self.settings, self.bot)
        return msg

    def sent_text(self):
        return " ".join(t for _, t, _ in self.bot.calls)

    async def test_old_cache_is_searched_again_and_new_vacancy_arrives(self):
        self.db.save_role_cache({"backend_python": [_v(1)]}, [])
        self.db.mark_sent_to_subscriber(10, _v(1))  # утреннее уже получил
        _age_cache(self.db, "backend_python", 90)
        self.db.set_subscriber_roles(10, ["backend_python"])
        collect = AsyncMock(return_value=[_v(1), _v(2)])
        with mock.patch("bot.subscriber_service.collect_for_role", collect):
            await self.press()
        collect.assert_awaited_once()
        self.assertIn("Python-разработчик 2", self.sent_text())
        self.assertNotIn("Python-разработчик 1 ", self.sent_text() + " ")

    async def test_recent_search_is_reused(self):
        self.db.save_role_cache({"backend_python": [_v(1)]}, [])  # только что
        self.db.set_subscriber_roles(10, ["backend_python"])
        with mock.patch("bot.subscriber_service.collect_for_role", side_effect=AssertionError("не должен искать")):
            await self.press()
        self.assertIn("Python-разработчик 1", self.sent_text())

    async def test_never_collected_role_is_searched(self):
        self.db.set_subscriber_roles(10, ["backend_python"])
        with mock.patch("bot.subscriber_service.collect_for_role", AsyncMock(return_value=[_v(7)])):
            await self.press()
        self.assertIn("Python-разработчик 7", self.sent_text())

    async def test_failed_search_falls_back_to_previous_collection(self):
        self.db.save_role_cache({"backend_python": [_v(1)]}, [])
        _age_cache(self.db, "backend_python", 90)
        self.db.set_subscriber_roles(10, ["backend_python"])
        with mock.patch("bot.subscriber_service.collect_for_role", AsyncMock(side_effect=RuntimeError("HH лежит"))):
            await self.press()
        self.assertIn("Python-разработчик 1", self.sent_text())

    async def test_failed_search_without_any_collection_says_try_later(self):
        self.db.set_subscriber_roles(10, ["backend_python"])
        with mock.patch("bot.subscriber_service.collect_for_role", AsyncMock(side_effect=RuntimeError("HH лежит"))):
            msg = await self.press()
        self.assertIn("не отвечают", msg.answer.await_args.args[0])

    async def test_partial_search_keeps_previous_vacancies(self):
        from bot.subscriber_collect import SourceLimited
        self.db.save_role_cache({"backend_python": [_v(1)]}, [])
        _age_cache(self.db, "backend_python", 90)
        self.db.set_subscriber_roles(10, ["backend_python"])
        with mock.patch("bot.subscriber_service.collect_for_role",
                        AsyncMock(side_effect=SourceLimited("hh.ru", [_v(2)]))):
            await self.press()
        text = self.sent_text()
        self.assertIn("Python-разработчик 1", text)
        self.assertIn("Python-разработчик 2", text)

    async def test_stale_vacancies_are_dropped_from_collection(self):
        self.db.set_subscriber_roles(10, ["backend_python"])
        with mock.patch("bot.subscriber_service.collect_for_role",
                        AsyncMock(return_value=[_v(1), _v(2, hours_ago=100)])):
            await self.press()
        kept = [v.uid for v in self.db.load_role_cache(["backend_python"])["backend_python"]]
        self.assertEqual(kept, ["hh.ru:1"])

    async def test_two_users_same_role_search_once(self):
        import asyncio
        self.db.set_subscriber_roles(10, ["backend_python"])
        self.db.set_subscriber_roles(11, ["backend_python"])
        release = asyncio.Event()
        calls = 0

        async def collect(settings, role):
            nonlocal calls
            calls += 1
            await release.wait()
            return [_v(1)]
        with mock.patch("bot.subscriber_service.collect_for_role", side_effect=collect):
            first = asyncio.ensure_future(self.press(10))
            second = asyncio.ensure_future(self.press(11))
            # asyncio.sleep в этих тестах заглушен — уступаем циклу через executor,
            # пока оба нажатия не дойдут до поиска (первое ищет, второе ждёт замок).
            loop = asyncio.get_running_loop()
            for _ in range(20):
                await loop.run_in_executor(None, lambda: None)
            release.set()
            await asyncio.gather(first, second)
        self.assertEqual(calls, 1)
        self.assertEqual({c for c, _, _ in self.bot.calls}, {10, 11})

    async def test_digest_started_during_search_is_not_duplicated(self):
        self.db.set_subscriber_roles(10, ["backend_python"])
        states = iter([False, True])
        with mock.patch.object(chat_main, "_digest_running", side_effect=lambda: next(states)), \
             mock.patch("bot.subscriber_service.collect_for_role", AsyncMock(return_value=[_v(1)])):
            msg = await self.press()
        self.assertEqual(self.bot.calls, [])
        self.assertIn("рассылка идёт прямо сейчас", msg.answer.await_args.args[0])

    async def test_search_timeout_falls_back(self):
        import asyncio
        from bot import subscriber_service
        self.db.save_role_cache({"backend_python": [_v(1)]}, [])
        _age_cache(self.db, "backend_python", 90)
        self.db.set_subscriber_roles(10, ["backend_python"])

        async def hang(settings, role):
            await asyncio.Event().wait()
        with mock.patch.object(subscriber_service, "NOW_COLLECT_TIMEOUT_SEC", 0.05), \
             mock.patch("bot.subscriber_service.collect_for_role", side_effect=hang):
            await self.press()
        self.assertIn("Python-разработчик 1", self.sent_text())


if __name__ == "__main__":
    unittest.main()
