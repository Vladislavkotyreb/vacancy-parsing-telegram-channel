"""Админка: учёт активности, DAU/MAU, охват, отток, список пользователей."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from unittest.mock import AsyncMock, MagicMock

from aiogram.exceptions import TelegramForbiddenError

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]

from bot.chat_main import (
    ADMIN_USERS_PAGE,
    TrackActivityMiddleware,
    cb_users_page,
    cmd_users,
    users_keyboard,
)
from bot.config import Settings
from bot.database import VacancyDatabase
from bot.models import Vacancy
from bot.stats import format_admin_stats, format_users_page
from bot.subscriber_service import SubscriberService

TZ = "Europe/Moscow"
ADMIN = 1


def _settings(db_path: Path, admin_id=ADMIN) -> Settings:
    return Settings(
        telegram_bot_token="test:token",
        telegram_chat_id=-100123,
        hh_user_agent="test/1.0",
        hh_access_token="",
        timezone=TZ,
        max_vacancy_age_hours=72,
        db_path=db_path,
        telegram_admin_id=admin_id,
    )


class DbTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db_path = Path(tempfile.mkdtemp()) / "test.db"
        self.db = VacancyDatabase(self.db_path)
        # Полдень по Москве — далеко от границы суток в обе стороны.
        self.now = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)

    def sql(self, query: str, *params) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute(query, params)
        conn.commit()
        conn.close()

    def active_on(self, user_id: int, days_ago: int) -> None:
        day = (self.now.date() - timedelta(days=days_ago)).isoformat()
        self.sql("INSERT OR IGNORE INTO user_activity (user_id, day) VALUES (?, ?)", user_id, day)

    def stats(self, **kwargs) -> dict:
        return self.db.audience_stats(TZ, now=self.now, **kwargs)


class ActivityTest(DbTestCase):
    def test_repeat_actions_same_day_count_once(self):
        for _ in range(3):
            self.db.record_activity(10, "ivan", "Иван", None, day=self.now.date().isoformat())
        self.db.record_activity(11, None, "Пётр", None, day=self.now.date().isoformat())

        self.assertEqual(self.stats()["dau"], 2)

    def test_mau_window_is_30_days_including_today(self):
        self.active_on(10, 0)
        self.active_on(11, 29)   # ещё в окне
        self.active_on(12, 30)   # уже нет

        stats = self.stats()
        self.assertEqual(stats["dau"], 1)
        self.assertEqual(stats["mau"], 2)

    def test_one_user_active_many_days_is_one_in_mau(self):
        for days_ago in range(10):
            self.active_on(10, days_ago)
        self.assertEqual(self.stats()["mau"], 1)

    def test_admin_is_excluded(self):
        self.active_on(ADMIN, 0)
        self.active_on(10, 0)

        self.assertEqual(self.stats(exclude_user_id=ADMIN)["dau"], 1)
        self.assertEqual(self.stats()["dau"], 2)

    def test_tracking_since_is_first_recorded_day(self):
        self.assertIsNone(self.stats()["tracking_since"])
        self.active_on(10, 5)
        self.active_on(11, 2)
        expected = (self.now.date() - timedelta(days=5)).isoformat()
        self.assertEqual(self.stats()["tracking_since"], expected)

    def test_profile_keeps_first_seen_and_updates_names(self):
        self.db.upsert_user_profile(10, None, "Иван", None)
        user = self.db.list_users()[0]
        self.assertIsNone(user["first_seen_at"], "профиль из рассылки — не активность")

        self.db.record_activity(10, "ivan", "Иван", "Петров", day="2026-10-20")
        first = self.db.list_users()[0]["first_seen_at"]
        self.db.record_activity(10, "ivan_new", "Иван", "Петров", day="2026-10-21")
        user = self.db.list_users()[0]

        self.assertEqual(user["first_seen_at"], first)
        self.assertEqual(user["username"], "ivan_new")
        self.assertIsNotNone(user["last_seen_at"])


class ReachAndChurnTest(DbTestCase):
    def sent(self, user_id: int, when: datetime, uid: str) -> None:
        self.sql(
            "INSERT INTO subscriber_sent (user_id, vacancy_uid, dedup_key, sent_at) VALUES (?, ?, '', ?)",
            user_id, uid, when.isoformat(),
        )

    def test_reach_counts_distinct_recipients(self):
        self.sent(10, self.now, "a")
        self.sent(10, self.now, "b")          # тот же человек
        self.sent(11, self.now - timedelta(days=10), "c")
        self.sent(12, self.now - timedelta(days=40), "d")

        stats = self.stats()
        self.assertEqual(stats["reach_today"], 1)
        self.assertEqual(stats["reach_month"], 2)

    def test_new_subscriptions_by_period(self):
        for user_id, days_ago in ((10, 0), (11, 3), (12, 20), (13, 45)):
            self.db.set_subscriber_roles(user_id, ["product_designer"])
            when = (self.now - timedelta(days=days_ago)).isoformat()
            self.sql("UPDATE subscribers SET subscribed_at = ? WHERE user_id = ?", when, user_id)

        stats = self.stats()
        self.assertEqual((stats["new_today"], stats["new_week"], stats["new_month"]), (1, 2, 3))

    def test_deactivate_records_date_and_reason(self):
        self.db.set_subscriber_roles(10, ["qa_manual"])
        self.db.deactivate_subscriber(10, reason="blocked")

        user = self.db.list_users()[0]
        self.assertFalse(user["active"])
        self.assertEqual(user["unsubscribe_reason"], "blocked")
        self.assertIsNotNone(user["unsubscribed_at"])

    def test_repeat_deactivate_keeps_original_date(self):
        self.db.set_subscriber_roles(10, ["qa_manual"])
        self.db.deactivate_subscriber(10)
        self.sql("UPDATE subscribers SET unsubscribed_at = '2026-01-01T00:00:00+00:00' WHERE user_id = 10")
        self.db.deactivate_subscriber(10, reason="blocked")

        user = self.db.list_users()[0]
        self.assertEqual(user["unsubscribed_at"], "2026-01-01T00:00:00+00:00")
        self.assertEqual(user["unsubscribe_reason"], "stop")

    def test_resubscribe_clears_unsubscribe(self):
        self.db.set_subscriber_roles(10, ["qa_manual"])
        self.db.deactivate_subscriber(10)
        self.db.set_subscriber_roles(10, ["qa_manual"])

        user = self.db.list_users()[0]
        self.assertTrue(user["active"])
        self.assertIsNone(user["unsubscribed_at"])

    def test_churn_counts_by_period_and_reason(self):
        for user_id, days_ago, reason in ((10, 1, "stop"), (11, 2, "blocked"), (12, 15, "blocked"), (13, 60, "stop")):
            self.db.set_subscriber_roles(user_id, ["qa_manual"])
            self.db.deactivate_subscriber(user_id, reason=reason)
            when = (self.now - timedelta(days=days_ago)).isoformat()
            self.sql("UPDATE subscribers SET unsubscribed_at = ? WHERE user_id = ?", when, user_id)

        stats = self.stats()
        self.assertEqual(stats["left_week"], 2)
        self.assertEqual(stats["left_month"], 3)
        self.assertEqual(stats["blocked_month"], 2)


class ListUsersTest(DbTestCase):
    def test_merges_profiles_and_subscriptions(self):
        self.db.record_activity(10, "visitor", "Гость", None, day="2026-10-21")   # не подписан
        self.db.set_subscriber_roles(11, ["qa_manual", "art_director"])           # без профиля
        self.db.set_subscriber_roles(12, ["product_owner"])
        self.db.record_activity(12, "po", "Ольга", None, day="2026-10-21")

        users = {u["user_id"]: u for u in self.db.list_users()}

        self.assertIsNone(users[10]["active"])
        self.assertEqual(users[11]["roles"], ["art_director", "qa_manual"])
        self.assertIsNone(users[11]["first_name"])
        self.assertTrue(users[12]["active"])
        self.assertEqual(users[12]["first_name"], "Ольга")

    def test_recently_active_first(self):
        self.db.set_subscriber_roles(10, ["qa_manual"])
        self.db.record_activity(11, None, "Старый", None, day="2026-10-01")
        self.sql("UPDATE users SET last_seen_at = '2026-10-01T10:00:00+00:00' WHERE user_id = 11")
        self.db.record_activity(12, None, "Свежий", None, day="2026-10-21")

        order = [u["user_id"] for u in self.db.list_users()]
        self.assertEqual(order, [12, 11, 10])


def _update(kind: str = "message"):
    fields = {"message": None, "callback_query": None, "my_chat_member": None}
    fields[kind] = object()
    return SimpleNamespace(**fields)


def _tg_user(user_id: int = 10, is_bot: bool = False):
    return SimpleNamespace(id=user_id, is_bot=is_bot, username="ivan", first_name="Иван", last_name=None)


class MiddlewareTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = VacancyDatabase(Path(tempfile.mkdtemp()) / "test.db")
        self.mw = TrackActivityMiddleware(self.db, TZ)
        self.handler = AsyncMock(return_value="ответ")

    async def test_message_and_button_count(self):
        await self.mw(self.handler, _update("message"), {"event_from_user": _tg_user(10)})
        await self.mw(self.handler, _update("callback_query"), {"event_from_user": _tg_user(11)})
        self.assertEqual(self.db.audience_stats(TZ)["dau"], 2)

    async def test_service_updates_do_not_count(self):
        """Блокировка бота приходит как my_chat_member — это не использование."""
        await self.mw(self.handler, _update("my_chat_member"), {"event_from_user": _tg_user()})
        self.assertEqual(self.db.audience_stats(TZ)["dau"], 0)
        self.handler.assert_awaited_once()

    async def test_bots_and_anonymous_do_not_count(self):
        await self.mw(self.handler, _update(), {"event_from_user": _tg_user(is_bot=True)})
        await self.mw(self.handler, _update(), {})
        self.assertEqual(self.db.audience_stats(TZ)["dau"], 0)

    async def test_db_failure_does_not_block_reply(self):
        with mock.patch.object(self.db, "record_activity", side_effect=sqlite3.OperationalError("locked")):
            result = await self.mw(self.handler, _update(), {"event_from_user": _tg_user()})
        self.assertEqual(result, "ответ")
        self.handler.assert_awaited_once()


class FormattingTest(DbTestCase):
    def test_stats_show_audience_block(self):
        self.db.record_activity(10, None, "Иван", None, day=datetime.now(ZoneInfo(TZ)).date().isoformat())
        text = format_admin_stats(self.db, TZ, exclude_user_id=ADMIN)
        self.assertIn("DAU", text)
        self.assertIn("MAU", text)
        self.assertIn("учёт ведётся с", text)
        self.assertIn("Админ в подсчёт не входит", text)

    def test_stats_explain_empty_history(self):
        self.assertIn("ещё не записана", format_admin_stats(self.db, TZ))

    def test_users_page_escapes_and_marks(self):
        now = datetime.now(timezone.utc).isoformat()
        users = [
            dict(user_id=ADMIN, username="me", first_name="Влад", last_name=None, first_seen_at=now,
                 last_seen_at=now, subscribed_at=now, active=True, unsubscribed_at=None,
                 unsubscribe_reason=None, roles=["product_designer"]),
            dict(user_id=20, username=None, first_name="<b>Хакер</b>", last_name=None, first_seen_at=None,
                 last_seen_at=None, subscribed_at=now, active=False, unsubscribed_at=now,
                 unsubscribe_reason="blocked", roles=[]),
            dict(user_id=30, username=None, first_name=None, last_name=None, first_seen_at=now,
                 last_seen_at=now, subscribed_at=None, active=None, unsubscribed_at=None,
                 unsubscribe_reason=None, roles=[]),
        ]
        text = format_users_page(users, 1, TZ, admin_id=ADMIN)

        self.assertIn("(вы)", text)
        self.assertIn("@me", text)
        self.assertIn("UX/UI | Продуктовый дизайнер", text)
        self.assertIn("&lt;b&gt;Хакер&lt;/b&gt;", text)
        self.assertNotIn("<b>Хакер</b>", text)
        self.assertIn("заблокировал бота сегодня", text)
        self.assertIn("id 30", text)
        self.assertIn("не подписан", text)
        self.assertIn("был сегодня", text)
        self.assertIn('href="tg://user?id=20"', text)

    def test_users_page_clamps_and_paginates(self):
        users = [
            dict(user_id=i, username=None, first_name=f"U{i}", last_name=None, first_seen_at=None,
                 last_seen_at=None, subscribed_at=None, active=None, unsubscribed_at=None,
                 unsubscribe_reason=None, roles=[])
            for i in range(45)
        ]
        self.assertIn("Страница 3 из 3", format_users_page(users, 99, TZ))
        self.assertIn("Страница 1 из 3", format_users_page(users, -5, TZ))

    def test_empty_list(self):
        self.assertIn("Пока никого", format_users_page([], 1, TZ))


class UsersKeyboardTest(unittest.TestCase):
    def test_single_page_has_no_buttons(self):
        self.assertIsNone(users_keyboard(1, 1))

    def test_edges_and_limit(self):
        first = [b.callback_data for b in users_keyboard(1, 5).inline_keyboard[0]]
        middle = [b.callback_data for b in users_keyboard(3, 5).inline_keyboard[0]]
        last = [b.callback_data for b in users_keyboard(5, 5).inline_keyboard[0]]

        self.assertEqual(first, [f"{ADMIN_USERS_PAGE}2"])
        self.assertEqual(middle, [f"{ADMIN_USERS_PAGE}2", f"{ADMIN_USERS_PAGE}4"])
        self.assertEqual(last, [f"{ADMIN_USERS_PAGE}4"])
        self.assertLessEqual(len(f"{ADMIN_USERS_PAGE}99999".encode()), 64)


class AdminAccessTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db_path = Path(tempfile.mkdtemp()) / "test.db"
        self.db = VacancyDatabase(self.db_path)
        self.settings = _settings(self.db_path)

    async def test_users_command_is_admin_only(self):
        stranger = SimpleNamespace(from_user=SimpleNamespace(id=999), answer=AsyncMock())
        await cmd_users(stranger, self.db, self.settings)
        self.assertIn("только для администратора", stranger.answer.await_args.args[0])

        admin = SimpleNamespace(from_user=SimpleNamespace(id=ADMIN), answer=AsyncMock())
        await cmd_users(admin, self.db, self.settings)
        self.assertIn("Пользователи", admin.answer.await_args.args[0])

    async def test_users_paging_is_admin_only(self):
        message = SimpleNamespace(edit_text=AsyncMock())
        stranger = SimpleNamespace(data=f"{ADMIN_USERS_PAGE}2", message=message,
                                   from_user=SimpleNamespace(id=999), answer=AsyncMock())
        await cb_users_page(stranger, self.db, self.settings)
        message.edit_text.assert_not_awaited()
        self.assertTrue(stranger.answer.await_args.kwargs.get("show_alert"))

    async def test_no_admin_configured_means_nobody(self):
        settings = _settings(self.db_path, admin_id=None)
        anyone = SimpleNamespace(from_user=SimpleNamespace(id=ADMIN), answer=AsyncMock())
        await cmd_users(anyone, self.db, settings)
        self.assertIn("только для администратора", anyone.answer.await_args.args[0])


class DigestSideEffectsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db_path = Path(tempfile.mkdtemp()) / "test.db"
        self.db = VacancyDatabase(self.db_path)
        self.bot = AsyncMock()
        self.service = SubscriberService(_settings(self.db_path), self.db, self.bot)

    @staticmethod
    async def _one_vacancy(settings, role):
        return [Vacancy(source="hh.ru", external_id="1", title="Арт-директор", company="Студия",
                        url="https://hh.ru/vacancy/1", published_at=datetime.now(timezone.utc))]

    async def test_block_is_recorded_with_reason(self):
        self.db.set_subscriber_roles(10, ["art_director"])
        self.bot.send_message.side_effect = TelegramForbiddenError(
            method=MagicMock(), message="Forbidden: bot was blocked by the user"
        )
        with mock.patch("bot.subscriber_service.collect_for_role", side_effect=self._one_vacancy):
            await self.service.run_daily_digests()

        user = self.db.list_users()[0]
        self.assertFalse(user["active"])
        self.assertEqual(user["unsubscribe_reason"], "blocked")

    async def test_names_come_from_digest_delivery(self):
        """Подписчик, который ничего не нажимает, всё равно получает имя в /users."""
        self.db.set_subscriber_roles(10, ["art_director"])
        self.bot.send_message.return_value = SimpleNamespace(
            chat=SimpleNamespace(type="private", username="silent", first_name="Молчун", last_name=None)
        )
        with mock.patch("bot.subscriber_service.collect_for_role", side_effect=self._one_vacancy):
            await self.service.run_daily_digests()

        user = self.db.list_users()[0]
        self.assertEqual((user["first_name"], user["username"]), ("Молчун", "silent"))
        self.assertIsNone(user["last_seen_at"], "получить дайджест — не активность")
        self.assertEqual(self.db.audience_stats(TZ)["dau"], 0)


if __name__ == "__main__":
    unittest.main()
