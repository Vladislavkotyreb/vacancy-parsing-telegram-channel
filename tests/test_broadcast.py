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




class BroadcastVideoTest(unittest.IsolatedAsyncioTestCase):
    """Рассылка с видео: файл грузится один раз, дальше — по file_id; меню приходит сразу."""

    async def asyncSetUp(self) -> None:
        from types import SimpleNamespace
        self.dir = Path(tempfile.mkdtemp())
        self.db = VacancyDatabase(self.dir / "test.db")
        self.db.set_subscriber_roles(1, ["product_designer"])
        self.db.set_subscriber_roles(2, ["qa_manual"])
        self.bot = AsyncMock()
        self.bot.send_animation.return_value = SimpleNamespace(animation=SimpleNamespace(file_id="FILE123"))
        (self.dir / "2026-10-29-now.html").write_text("<b>Кнопка</b>\n\nТекст", encoding="utf-8")
        (self.dir / "2026-10-29-now.mp4").write_bytes(b"fake")

    def load(self):
        from bot.broadcast import find_video
        path = self.dir / "2026-10-29-now.html"
        broadcast_id, text = load_broadcast(path)
        return broadcast_id, text, find_video(path, text)

    async def test_video_uploaded_once_then_sent_by_file_id(self):
        from aiogram.types import FSInputFile
        broadcast_id, text, video = self.load()
        stats = await run_broadcast(self.bot, self.db, broadcast_id, text, [1, 2], video)
        self.assertEqual(stats.sent, 2)
        calls = self.bot.send_animation.await_args_list
        self.assertIsInstance(calls[0].kwargs["animation"], FSInputFile)
        self.assertEqual(calls[1].kwargs["animation"], "FILE123")
        self.assertEqual(calls[0].kwargs["caption"], text)
        self.bot.send_message.assert_not_awaited()

    async def test_menu_with_new_button_is_attached(self):
        from aiogram.types import ReplyKeyboardMarkup
        from bot.menu import BTN_NOW
        broadcast_id, text, video = self.load()
        await run_broadcast(self.bot, self.db, broadcast_id, text, [1], video)
        markup = self.bot.send_animation.await_args.kwargs["reply_markup"]
        self.assertIsInstance(markup, ReplyKeyboardMarkup)
        self.assertEqual(markup.keyboard[0][0].text, BTN_NOW)

    async def test_preview_sends_video_to_admin_only(self):
        broadcast_id, text, video = self.load()
        await send_preview(self.bot, 999, text, video)
        self.assertEqual(self.bot.send_animation.await_args.kwargs["chat_id"], 999)
        self.assertFalse(self.db.was_broadcast_sent(broadcast_id, 999))

    async def test_no_video_file_means_text_message(self):
        (self.dir / "2026-10-29-now.mp4").unlink()
        broadcast_id, text, video = self.load()
        self.assertIsNone(video)
        await run_broadcast(self.bot, self.db, broadcast_id, text, [1], video)
        self.bot.send_animation.assert_not_awaited()
        self.bot.send_message.assert_awaited_once()

    def test_video_size_is_read_from_file(self):
        from bot.broadcast import mp4_size
        for path in Path("broadcasts").glob("*.mp4"):
            width, height = mp4_size(path)
            self.assertTrue(width and height, path)
            self.assertLessEqual(height / width, 1.25 + 1e-6, f"{path}: выше 4:5 — Телеграм обрежет в чате")
        self.assertEqual(mp4_size(self.dir / "2026-10-29-now.mp4"), (None, None))  # не mp4 — без размера

    def test_too_long_caption_is_rejected(self):
        from bot.broadcast import find_video
        path = self.dir / "2026-10-29-now.html"
        with self.assertRaises(ValueError):
            find_video(path, "а" * 1025)

    def test_real_broadcast_files_are_valid(self):
        """Файлы в broadcasts/: текст не пуст, подпись к видео влезает в лимит Телеграма."""
        from bot.broadcast import find_video
        for path in sorted(Path("broadcasts").glob("*.html")):
            _, text = load_broadcast(path)
            find_video(path, text)



class SafeTimeTest(unittest.IsolatedAsyncioTestCase):
    """Рассылка всем — только днём: не будим людей и не мешаем утренней подборке."""

    def test_window(self):
        from bot.broadcast import is_safe_time
        cases = {(1, 30): False, (9, 0): False, (10, 15): False, (11, 59): False, (12, 0): True,
                 (13, 0): True, (19, 59): True, (20, 0): False, (23, 0): False}
        for (h, m), expected in cases.items():
            self.assertEqual(is_safe_time(h, m), expected, (h, m))

    async def run_send_at(self, hour):
        import argparse
        from datetime import datetime as real_dt
        from unittest import mock
        from bot import run_once
        folder = Path(tempfile.mkdtemp())
        db = VacancyDatabase(folder / "t.db")
        db.set_subscriber_roles(1, ["product_designer"])
        (folder / "b.html").write_text("<b>Текст</b>", encoding="utf-8")
        bot = AsyncMock()
        fake = mock.MagicMock(wraps=real_dt)
        fake.now.return_value = real_dt(2026, 10, 29, hour, 0)
        args = argparse.Namespace(file=str(folder / "b.html"), send=True, include_starters=False)
        with mock.patch.object(run_once, "datetime", fake):
            code = await run_once._broadcast(bot, db, args, "999")
        to_users = [c for c in bot.send_message.await_args_list if c.kwargs.get("chat_id") == 1]
        return code, to_users, bot

    async def test_night_send_is_refused_and_admin_told(self):
        code, to_users, bot = await self.run_send_at(1)
        self.assertEqual(code, 1)
        self.assertEqual(to_users, [])
        self.assertIn("не отправлена", bot.send_message.await_args.kwargs["text"])

    async def test_day_send_goes_out(self):
        code, to_users, _ = await self.run_send_at(13)
        self.assertEqual(code, 0)
        self.assertEqual(len(to_users), 1)


if __name__ == "__main__":
    unittest.main()
