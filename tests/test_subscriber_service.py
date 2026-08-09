"""Рассылка подписчикам: сбор один раз на роль, раздача из кэша, устойчивость к сбоям."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock
from unittest.mock import AsyncMock

from bot.config import Settings
from bot.database import VacancyDatabase
from bot.models import Vacancy
from bot.subscriber_service import SubscriberService


def _settings(db_path: Path) -> Settings:
    """Напрямую, а не через from_env — тест не должен зависеть от .env."""
    return Settings(
        telegram_bot_token="test:token",
        telegram_chat_id=-100123,
        hh_user_agent="test/1.0",
        hh_access_token="",
        timezone="Europe/Moscow",
        max_vacancy_age_hours=72,
        db_path=db_path,
        telegram_admin_id=None,
    )


def _vacancy(role_id: str, n: int) -> Vacancy:
    return Vacancy(
        source="hh.ru",
        external_id=f"{role_id}-{n}",
        title=f"Вакансия {role_id} {n}",
        company=f"Компания {n}",
        url=f"https://hh.ru/vacancy/{role_id}-{n}",
        published_at=datetime.now(timezone.utc),
    )


class SubscriberServiceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db_path = Path(tempfile.mkdtemp()) / "test.db"
        self.db = VacancyDatabase(self.db_path)
        self.settings = _settings(self.db_path)
        self.bot = AsyncMock()
        self.service = SubscriberService(self.settings, self.db, self.bot)

        self.calls: list[str] = []

    async def _fake_collect(self, settings, role):
        self.calls.append(role.id)
        return [_vacancy(role.id, 1), _vacancy(role.id, 2)]

    def _patch_collect(self, side_effect=None):
        return mock.patch(
            "bot.subscriber_service.collect_for_role",
            side_effect=side_effect or self._fake_collect,
        )

    def _sent_texts(self) -> list[str]:
        return [c.kwargs["text"] for c in self.bot.send_message.await_args_list]

    async def test_collects_once_per_role_not_per_subscriber(self):
        """Главное: трое подписчиков, две различные роли — два сбора, не четыре."""
        self.db.set_subscriber_roles(1001, ["product_designer"])
        self.db.set_subscriber_roles(1002, ["product_designer"])
        self.db.set_subscriber_roles(1003, ["product_designer", "qa_manual"])

        with self._patch_collect():
            stats = await self.service.run_daily_digests()

        self.assertEqual(sorted(self.calls), ["product_designer", "qa_manual"])
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(stats.subscribers, 3)
        self.assertEqual(stats.roles_collected, 2)
        self.assertEqual(stats.failed_roles, [])

    async def test_every_subscriber_still_gets_their_roles(self):
        """Раздача из кэша не должна терять роли: у кого две — получает обе."""
        self.db.set_subscriber_roles(1001, ["product_designer"])
        self.db.set_subscriber_roles(1002, ["product_designer", "qa_manual"])

        with self._patch_collect():
            await self.service.run_daily_digests()

        by_user: dict[int, str] = {}
        for call in self.bot.send_message.await_args_list:
            chat_id = call.kwargs["chat_id"]
            by_user[chat_id] = by_user.get(chat_id, "") + call.kwargs["text"]

        self.assertIn("product_designer", by_user[1001])
        self.assertNotIn("qa_manual", by_user[1001])
        self.assertIn("product_designer", by_user[1002])
        self.assertIn("qa_manual", by_user[1002])

    async def test_failed_role_does_not_abort_the_run(self):
        async def flaky(settings, role):
            self.calls.append(role.id)
            if role.id == "qa_manual":
                raise RuntimeError("HH недоступен")
            return [_vacancy(role.id, 1)]

        self.db.set_subscriber_roles(1001, ["qa_manual"])
        self.db.set_subscriber_roles(1002, ["product_designer"])

        with self._patch_collect(side_effect=flaky):
            stats = await self.service.run_daily_digests()

        self.assertEqual(stats.failed_roles, ["qa_manual"])
        # Подписчик на исправной роли всё равно получил дайджест.
        texts = " ".join(self._sent_texts())
        self.assertIn("product_designer", texts)
        self.assertNotIn("qa_manual", texts)

    async def test_no_new_vacancies_sends_nothing(self):
        self.db.set_subscriber_roles(1001, ["product_designer"])

        with self._patch_collect():
            await self.service.run_daily_digests()
        first_batch = self.bot.send_message.await_count
        self.assertGreater(first_batch, 0)

        # Повтор: всё уже в subscriber_sent, новых нет — DM не уходит.
        with self._patch_collect():
            stats = await self.service.run_daily_digests()

        self.assertEqual(self.bot.send_message.await_count, first_batch)
        self.assertEqual(stats.messages, 0)

    async def test_stale_vacancies_are_filtered(self):
        old = Vacancy(
            source="hh.ru",
            external_id="old-1",
            title="Старая вакансия",
            company="Компания",
            url="https://hh.ru/vacancy/old-1",
            published_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )

        async def only_old(settings, role):
            self.calls.append(role.id)
            return [old]

        self.db.set_subscriber_roles(1001, ["product_designer"])
        with self._patch_collect(side_effect=only_old):
            stats = await self.service.run_daily_digests()

        self.bot.send_message.assert_not_awaited()
        self.assertEqual(stats.messages, 0)

    async def test_no_subscribers_skips_collection_entirely(self):
        with self._patch_collect():
            stats = await self.service.run_daily_digests()

        self.assertEqual(self.calls, [])
        self.assertEqual(stats.subscribers, 0)
        self.assertEqual(stats.roles_collected, 0)

    async def test_preview_collects_once_per_role_and_sends_nothing(self):
        self.db.set_subscriber_roles(1001, ["product_designer"])
        self.db.set_subscriber_roles(1002, ["product_designer"])

        with self._patch_collect():
            await self.service.preview_digests()

        self.assertEqual(self.calls, ["product_designer"])
        self.bot.send_message.assert_not_awaited()

    async def test_unknown_role_is_skipped_without_crashing(self):
        self.db.set_subscriber_roles(1001, ["no_such_role"])

        with self._patch_collect():
            stats = await self.service.run_daily_digests()

        self.assertEqual(self.calls, [])
        self.assertEqual(stats.roles_collected, 0)
        self.bot.send_message.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
