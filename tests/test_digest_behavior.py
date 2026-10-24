"""История доставок не стирается при смене ролей; «новых нет» — только когда это правда."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
from unittest.mock import AsyncMock

from bot.config import Settings
from bot.database import VacancyDatabase
from bot.models import Vacancy
from bot.subscriber_collect import SourceLimited
from bot.subscriber_service import SubscriberService

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]


def _vacancy(n: int) -> Vacancy:
    return Vacancy(source="hh.ru", external_id=str(n), title=f"Product Designer {n}", company=f"К{n}",
                   url=f"https://hh.ru/vacancy/{n}", published_at=datetime.now(timezone.utc))


class DigestBehaviourTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db_path = Path(tempfile.mkdtemp()) / "test.db"
        self.db = VacancyDatabase(self.db_path)
        settings = Settings(
            telegram_bot_token="test:token", telegram_chat_id=-100123, hh_user_agent="test/1.0",
            hh_access_token="", timezone="Europe/Moscow", max_vacancy_age_hours=72,
            db_path=self.db_path, telegram_admin_id=None,
        )
        self.bot = AsyncMock()
        self.service = SubscriberService(settings, self.db, self.bot)
        self.found = {"product_designer": [_vacancy(1), _vacancy(2)], "head_of_design": []}

    async def _collect(self, settings, role):
        return list(self.found.get(role.id, []))

    async def run_digest(self, collect=None):
        with mock.patch("bot.subscriber_service.collect_for_role", side_effect=collect or self._collect):
            return await self.service.run_daily_digests()

    def texts(self) -> list:
        return [c.kwargs["text"] for c in self.bot.send_message.await_args_list]

    # --- история доставок ---

    async def test_adding_a_role_keeps_delivery_history(self):
        self.db.set_subscriber_roles(10, ["product_designer"])
        await self.run_digest()
        self.assertTrue(self.db.is_sent_to_subscriber(10, "hh.ru:1"))

        self.db.set_subscriber_roles(10, ["product_designer", "head_of_design"])
        self.assertTrue(self.db.is_sent_to_subscriber(10, "hh.ru:1"), "история не стирается")

    async def test_no_duplicates_after_role_change(self):
        """Раньше смена ролей стирала историю, и утром приходили уже отправленные вакансии."""
        self.db.set_subscriber_roles(10, ["product_designer"])
        await self.run_digest()
        self.bot.send_message.reset_mock()

        self.db.set_subscriber_roles(10, ["product_designer", "head_of_design"])
        self.found["product_designer"].append(_vacancy(3))
        await self.run_digest()

        sent = " ".join(self.texts())
        self.assertIn("Product Designer 3", sent)
        self.assertNotIn("Product Designer 1", sent)
        self.assertNotIn("Product Designer 2", sent)

    # --- «новых нет» ---

    async def test_empty_notice_when_nothing_new(self):
        self.db.set_subscriber_roles(20, ["head_of_design"])
        stats = await self.run_digest()

        self.assertEqual(stats.empty_notices, 1)
        text = self.texts()[0]
        self.assertIn("Новых вакансий руководителя дизайна нет", text)
        self.assertIn("проверю снова", text)
        self.assertNotIn("Найдено всего", text)

    async def test_empty_notice_for_several_roles_has_no_brackets(self):
        self.found["qa_manual"] = []
        self.db.set_subscriber_roles(20, ["head_of_design", "qa_manual"])
        await self.run_digest()
        text = self.texts()[0]
        self.assertIn("Новых вакансий по выбранным ролям нет", text)
        self.assertNotIn("(", text)

    async def test_empty_notice_again_next_day(self):
        self.db.set_subscriber_roles(20, ["head_of_design"])
        await self.run_digest()
        yesterday = (datetime.now(ZoneInfo("Europe/Moscow")).date() - timedelta(days=1)).isoformat()
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE subscribers SET last_empty_notice_on = ? WHERE user_id = 20", (yesterday,))
        conn.commit()
        conn.close()
        self.bot.send_message.reset_mock()

        stats = await self.run_digest()
        self.assertEqual(stats.empty_notices, 1)

    async def test_failed_role_gets_silence_not_a_false_empty_notice(self):
        async def broken(settings, role):
            raise RuntimeError("HH недоступен")

        self.db.set_subscriber_roles(20, ["head_of_design"])
        stats = await self.run_digest(collect=broken)

        self.bot.send_message.assert_not_awaited()
        self.assertEqual(stats.empty_notices, 0)

    async def test_limited_role_gets_silence_if_nothing_collected(self):
        async def limited(settings, role):
            raise SourceLimited("hh.ru", [])

        self.db.set_subscriber_roles(20, ["head_of_design"])
        stats = await self.run_digest(collect=limited)

        self.bot.send_message.assert_not_awaited()
        self.assertEqual(stats.limited_roles, ["head_of_design"])

    async def test_one_broken_role_of_two_still_blocks_false_notice(self):
        """Вакансий по рабочей роли нет, а вторая не собралась — честно сказать «нет» нельзя."""
        async def half(settings, role):
            if role.id == "head_of_design":
                raise RuntimeError("сбой")
            return []

        self.db.set_subscriber_roles(20, ["product_designer", "head_of_design"])
        await self.run_digest(collect=half)
        self.bot.send_message.assert_not_awaited()

    async def test_unknown_role_gets_silence(self):
        self.db.set_subscriber_roles(20, ["no_such_role"])
        await self.run_digest()
        self.bot.send_message.assert_not_awaited()

    async def test_digest_with_vacancies_is_not_an_empty_notice(self):
        self.db.set_subscriber_roles(10, ["product_designer"])
        stats = await self.run_digest()
        self.assertEqual(stats.empty_notices, 0)
        self.assertIn("2 новых вакансий", self.texts()[0])


if __name__ == "__main__":
    unittest.main()
