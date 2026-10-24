"""Лимит дайджеста: не больше 30 самых свежих, остальные — в следующие дни."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
from unittest.mock import AsyncMock

from bot.config import Settings
from bot.database import VacancyDatabase
from bot.models import Vacancy
from bot.subscriber_service import MAX_VACANCIES_PER_DIGEST, SubscriberService

NOW = datetime.now(timezone.utc)


def _vacancy(n: int, hours_ago: float) -> Vacancy:
    return Vacancy(source="hh.ru", external_id=str(n), title=f"Product Manager {n}", company=f"Компания {n}",
                   url=f"https://hh.ru/vacancy/{n}", published_at=NOW - timedelta(hours=hours_ago))


class DigestLimitTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        path = Path(tempfile.mkdtemp()) / "test.db"
        self.db = VacancyDatabase(path)
        settings = Settings(
            telegram_bot_token="test:token", telegram_chat_id=-100123, hh_user_agent="test/1.0",
            hh_access_token="", timezone="Europe/Moscow", max_vacancy_age_hours=72,
            db_path=path, telegram_admin_id=None,
        )
        self.bot = AsyncMock()
        self.service = SubscriberService(settings, self.db, self.bot)
        self.db.set_subscriber_roles(10, ["product_manager"])
        # 45 новых: №0 самая свежая, №44 — самая старая (но всё ещё моложе 72 ч).
        self.found = [_vacancy(n, hours_ago=1 + n) for n in range(45)]

    async def run_digest(self):
        async def collect(settings, role):
            return list(self.found)
        with mock.patch("bot.subscriber_service.collect_for_role", side_effect=collect):
            return await self.service.run_daily_digests()

    def sent_text(self) -> str:
        return " ".join(c.kwargs["text"] for c in self.bot.send_message.await_args_list)

    def sent_numbers(self) -> set:
        import re
        return {int(n) for n in re.findall(r"Product Manager (\d+)", self.sent_text())}

    async def test_sends_only_the_freshest_thirty(self):
        self.assertEqual(MAX_VACANCIES_PER_DIGEST, 30)
        await self.run_digest()
        self.assertEqual(self.sent_numbers(), set(range(30)))

    async def test_header_says_how_many_were_new(self):
        await self.run_digest()
        text = self.sent_text()
        self.assertIn("30 новых вакансий", text)
        self.assertIn("Показаны 30 самых свежих из 45", text)

    async def test_only_sent_ones_are_marked(self):
        await self.run_digest()
        self.assertTrue(self.db.is_sent_to_subscriber(10, "hh.ru:0"))
        self.assertFalse(self.db.is_sent_to_subscriber(10, "hh.ru:44"))

    async def test_rest_arrives_next_time_without_duplicates(self):
        await self.run_digest()
        self.bot.send_message.reset_mock()

        await self.run_digest()
        self.assertEqual(self.sent_numbers(), set(range(30, 45)))
        self.assertNotIn("Показаны", self.sent_text())

    async def test_small_digest_has_no_limit_line(self):
        self.found = self.found[:5]
        await self.run_digest()
        self.assertNotIn("Показаны", self.sent_text())
        self.assertIn("5 новых вакансий", self.sent_text())

    async def test_thirty_fit_in_a_few_messages(self):
        """Раньше у новичка с 240 вакансиями выходило ~20 сообщений подряд."""
        self.found = [_vacancy(n, hours_ago=1 + n * 0.2) for n in range(240)]
        await self.run_digest()
        self.assertLessEqual(self.bot.send_message.await_count, 4)


if __name__ == "__main__":
    unittest.main()
