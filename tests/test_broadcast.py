"""Разовая рассылка: аудитория, превью, повторный запуск без дублей, блокировки."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from aiogram.exceptions import TelegramForbiddenError

from bot.broadcast import load_broadcast, run_broadcast, send_preview
from bot.database import VacancyDatabase

BROADCAST = "2026-10-new-roles"


class BroadcastTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = VacancyDatabase(Path(tempfile.mkdtemp()) / "test.db")
        self.bot = AsyncMock()
        self.db.set_subscriber_roles(1, ["product_designer"])
        self.db.set_subscriber_roles(2, ["qa_manual"])
        self.db.set_subscriber_roles(3, ["backend_go"])
        self.db.deactivate_subscriber(3)                                  # отписался
        self.db.record_activity(4, None, "Гость", None, day="2026-10-23")  # /start без подписки

    def recipients(self) -> list:
        return sorted(c.kwargs["chat_id"] for c in self.bot.send_message.await_args_list)

    def test_audience_excludes_unsubscribed(self):
        self.assertEqual(self.db.broadcast_audience(), [1, 2])
        self.assertEqual(self.db.broadcast_audience(include_starters=True), [1, 2, 4])

    async def test_sends_to_everyone_once(self):
        stats = await run_broadcast(self.bot, self.db, BROADCAST, "текст", [1, 2])
        self.assertEqual(self.recipients(), [1, 2])
        self.assertEqual((stats.sent, stats.already_sent), (2, 0))

    async def test_rerun_does_not_duplicate(self):
        """Сеть на хостинге рвётся — перезапуск должен продолжить, а не начать заново."""
        await run_broadcast(self.bot, self.db, BROADCAST, "текст", [1, 2])
        self.bot.send_message.reset_mock()

        stats = await run_broadcast(self.bot, self.db, BROADCAST, "текст", [1, 2])
        self.bot.send_message.assert_not_awaited()
        self.assertEqual(stats.already_sent, 2)

    async def test_failed_delivery_is_retried_on_rerun(self):
        def flaky(chat_id, **kwargs):
            if chat_id == 2:
                raise RuntimeError("сеть оборвалась")
        self.bot.send_message.side_effect = lambda **kw: flaky(**kw)

        stats = await run_broadcast(self.bot, self.db, BROADCAST, "текст", [1, 2])
        self.assertEqual((stats.sent, stats.failed), (1, 1))
        self.assertFalse(self.db.was_broadcast_sent(BROADCAST, 2))

        self.bot.send_message.side_effect = None
        self.bot.send_message.reset_mock()
        await run_broadcast(self.bot, self.db, BROADCAST, "текст", [1, 2])
        self.assertEqual(self.recipients(), [2])

    async def test_blocked_user_is_unsubscribed(self):
        def blocked(chat_id, **kwargs):
            if chat_id == 1:
                raise TelegramForbiddenError(method=MagicMock(), message="bot was blocked by the user")
        self.bot.send_message.side_effect = lambda **kw: blocked(**kw)

        stats = await run_broadcast(self.bot, self.db, BROADCAST, "текст", [1, 2])
        self.assertEqual(stats.blocked, 1)
        self.assertEqual(self.db.broadcast_audience(), [2])

    async def test_another_broadcast_is_separate(self):
        await run_broadcast(self.bot, self.db, BROADCAST, "текст", [1])
        self.bot.send_message.reset_mock()
        await run_broadcast(self.bot, self.db, "2026-12-next", "другой текст", [1])
        self.assertEqual(self.recipients(), [1])

    async def test_preview_goes_only_to_admin_and_marks_nothing(self):
        await send_preview(self.bot, 999, "текст")
        self.assertEqual(self.recipients(), [999])
        self.assertFalse(self.db.was_broadcast_sent(BROADCAST, 1))

    def test_load_broadcast_uses_file_name_as_id(self):
        path = Path(tempfile.mkdtemp()) / f"{BROADCAST}.html"
        path.write_text("<b>Привет</b>\n", encoding="utf-8")
        self.assertEqual(load_broadcast(path), (BROADCAST, "<b>Привет</b>"))

    def test_empty_file_is_rejected(self):
        path = Path(tempfile.mkdtemp()) / "empty.html"
        path.write_text("  \n", encoding="utf-8")
        with self.assertRaises(ValueError):
            load_broadcast(path)


class ChangelogFileTest(unittest.TestCase):
    """Текст ченжлога, который уйдёт пользователям."""

    PATH = Path(__file__).resolve().parent.parent / "broadcasts" / f"{BROADCAST}.html"

    def test_is_valid_telegram_html(self):
        import re
        text = self.PATH.read_text(encoding="utf-8")
        tags = re.findall(r"</?([a-z]+)", text)
        self.assertTrue(set(tags) <= {"b", "i", "a", "code"}, tags)
        self.assertEqual(text.count("<b>"), text.count("</b>"))
        self.assertLess(len(text), 4096)

    def test_names_every_new_category_and_a_working_entry_point(self):
        from bot.role_categories import CATEGORIES
        text = self.PATH.read_text(encoding="utf-8").replace("\u00a0", " ")
        for category_id in ("data", "product", "qa", "leaders"):
            self.assertIn(CATEGORIES[category_id].title, text)
        self.assertIn("арт-директор", text)
        # Рассылка идёт и тем, кто не подписан: у них кнопка «Выбрать роли», а не
        # «…заново». /start одинаково работает у всех и подписки не сбрасывает.
        self.assertIn("/start", text)
        self.assertNotIn("заново", text)

if __name__ == "__main__":
    unittest.main()
