"""Сбои при утренней рассылке (аудит 25.10.2026): каждый тест — найденная дыра."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from unittest.mock import AsyncMock

from aiogram.exceptions import ClientDecodeError, TelegramForbiddenError, TelegramServerError
from aiogram.methods import SendMessage

from bot import run_once
from bot.config import Settings
from bot.database import VacancyDatabase
from bot.models import Vacancy
from bot.subscriber_service import SubscriberService

METHOD = SendMessage(chat_id=1, text="x")


def _vacancy(n: int, long: bool = False) -> Vacancy:
    title = f"Python-разработчик {n}" + (" " + "о" * 150 if long else "")
    return Vacancy(source="hh.ru", external_id=str(n), title=title, company=f"К{n}",
                   url=f"https://hh.ru/vacancy/{n}", published_at=datetime.now(timezone.utc) - timedelta(minutes=n))


class _Bot:
    """send_message по сценарию: значения — исключение или None (успех)."""

    def __init__(self, script=None) -> None:
        self.script = list(script or [])
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id, text, **kw):
        if self.script:
            outcome = self.script.pop(0)
            if outcome is not None:
                raise outcome
        self.sent.append((chat_id, text))
        return SimpleNamespace(chat=SimpleNamespace(type="private", username=None, first_name="И", last_name=None))


class DigestResilienceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.path = Path(tempfile.mkdtemp()) / "t.db"
        self.db = VacancyDatabase(self.path)
        self.settings = Settings(
            telegram_bot_token="1:t", telegram_chat_id=-1, hh_user_agent="t/1", hh_access_token="",
            timezone="Europe/Moscow", max_vacancy_age_hours=72, db_path=self.path, telegram_admin_id=None,
        )
        self.found = [_vacancy(n) for n in range(1, 4)]
        for patcher in (
            mock.patch("bot.subscriber_service.asyncio.sleep", new=AsyncMock()),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    async def _run(self, bot):
        async def collect(settings, role):
            return list(self.found)
        with mock.patch("bot.subscriber_service.collect_for_role", side_effect=collect):
            return await SubscriberService(self.settings, self.db, bot).run_daily_digests()

    async def test_telegram_502_is_retried(self):
        self.db.set_subscriber_roles(1, ["backend_python"])
        bot = _Bot([TelegramServerError(METHOD, "Bad Gateway"), ClientDecodeError("502 html", ValueError(), "<html>")])
        stats = await self._run(bot)
        self.assertEqual(len(bot.sent), 1)
        self.assertEqual(stats.failed_users, [])

    async def test_second_pass_delivers_after_long_outage(self):
        self.db.set_subscriber_roles(1, ["backend_python"])
        bot = _Bot([TelegramServerError(METHOD, "Bad Gateway")] * 4)  # 1 + 3 повтора
        stats = await self._run(bot)
        self.assertEqual(len(bot.sent), 1, "дошло вторым проходом")
        self.assertEqual(stats.failed_users, [])

    async def test_undelivered_is_reported(self):
        self.db.set_subscriber_roles(1, ["backend_python"])
        bot = _Bot([TelegramServerError(METHOD, "Bad Gateway")] * 8)
        stats = await self._run(bot)
        self.assertEqual(stats.failed_users, [1])
        self.assertFalse(self.db.is_sent_to_subscriber(1, "hh.ru:1"))

    async def test_part_two_failure_does_not_resend_part_one(self):
        self.found = [_vacancy(n, long=True) for n in range(1, 31)]  # 30 длинных — два сообщения
        self.db.set_subscriber_roles(1, ["backend_python"])
        bot = _Bot([None] + [TelegramServerError(METHOD, "Bad Gateway")] * 8)
        await self._run(bot)
        self.assertEqual(len(bot.sent), 1)
        first = bot.sent[0][1]
        marked = [v for v in self.found if self.db.is_sent_to_subscriber(1, v.uid)]
        self.assertTrue(marked, "вакансии первого сообщения отмечены")
        self.assertTrue(all(v.title in first for v in marked))
        self.assertLess(len(marked), 30)

    async def test_db_error_on_blocked_user_does_not_stop_others(self):
        self.db.set_subscriber_roles(1, ["backend_python"])
        self.db.set_subscriber_roles(2, ["backend_python"])
        bot = _Bot([TelegramForbiddenError(METHOD, "blocked")])
        with mock.patch.object(self.db, "deactivate_subscriber", side_effect=RuntimeError("database is locked")):
            stats = await self._run(bot)
        self.assertEqual([chat for chat, _ in bot.sent], [2])
        self.assertEqual(stats.blocked, 1)


class TelegramOutageTest(DigestResilienceTest):
    async def test_outage_stops_pass_instead_of_running_all_day(self):
        for user_id in range(1, 21):
            self.db.set_subscriber_roles(user_id, ["backend_python"])
        bot = _Bot([TelegramServerError(METHOD, "Bad Gateway")] * 10_000)
        stats = await self._run(bot)
        self.assertEqual(len(stats.failed_users), 20)
        # Два прохода × 5 подписчиков подряд × 4 попытки — а не 20 × 4 × 2.
        self.assertEqual(10_000 - len(bot.script), 2 * 5 * 4)


class DigestLockTest(unittest.TestCase):
    def test_second_lock_is_refused_and_released_on_close(self):
        with mock.patch.object(run_once, "DIGEST_LOG", Path(tempfile.mkdtemp()) / "digest.log"):
            first = run_once._digest_lock()
            self.assertIsNotNone(first)
            self.assertIsNone(run_once._digest_lock())
            first.close()
            again = run_once._digest_lock()
            self.assertIsNotNone(again)
            again.close()


if __name__ == "__main__":
    unittest.main()
