"""Штатное меню Telegram и совместимость со старой клавиатурой, без сети."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

from aiogram import Bot
from aiogram.methods import SendMessage
from aiogram.types import Chat, Message, ReplyKeyboardRemove, User

from bot.chat_main import _now_pressed_at, router
from bot.config import Settings
from bot.database import VacancyDatabase
from bot.menu import (
    BTN_CHOOSE_ROLES,
    BTN_NOW,
)


class MenuVisibilityTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.db = VacancyDatabase(Path(directory.name) / "test.db")
        self.user_id = 999001
        self.session = AsyncMock()
        self.bot = Bot(token="1:test", session=self.session)
        self.settings = Settings(
            telegram_bot_token="1:test", telegram_chat_id=-1, hh_user_agent="test/1.0",
            hh_access_token="", timezone="Europe/Moscow", max_vacancy_age_hours=72,
            db_path=self.db.db_path, telegram_admin_id=None,
        )
        _now_pressed_at.clear()

    async def command(self, text):
        self.session.reset_mock()
        message = Message(
            message_id=1,
            date=datetime.now(timezone.utc),
            chat=Chat(id=self.user_id, type="private"),
            from_user=User(id=self.user_id, is_bot=False, first_name="А"),
            text=text,
        ).as_(self.bot)
        await router.propagate_event(
            "message", message, db=self.db, bot=self.bot, settings=self.settings,
        )
        self.session.assert_awaited_once()
        request = self.session.await_args.args[1]
        self.assertIsInstance(request, SendMessage)
        self.assertEqual(request.chat_id, self.user_id)
        return request

    async def test_legacy_hide_removes_keyboard_and_points_to_native_menu(self):
        request = await self.command("/hide")
        self.assertIsInstance(request.reply_markup, ReplyKeyboardRemove)
        self.assertEqual(request.reply_markup.model_dump(exclude_none=True), {"remove_keyboard": True})
        self.assertIn("«Меню» рядом с полем ввода", request.text)
        self.assertIn("продолжают работать", request.text)

    async def test_legacy_menu_does_not_restore_the_old_keyboard(self):
        self.db.set_subscriber_roles(self.user_id, ["backend_python"])
        request = await self.command("/menu")
        self.assertIsInstance(request.reply_markup, ReplyKeyboardRemove)
        self.assertIn("«Меню» рядом с полем ввода", request.text)

    async def test_native_roles_action_opens_region_selection(self):
        request = await self.command("/roles")
        callbacks = [button.callback_data for row in request.reply_markup.inline_keyboard for button in row]
        self.assertIn("s0:reg:cis", callbacks)
        self.assertIsNone(self.db.get_subscriber(self.user_id))

    async def test_native_myrole_action_removes_old_keyboard(self):
        self.db.set_subscriber_roles(self.user_id, ["backend_python"])
        request = await self.command("/myrole")
        self.assertIn("Текущая подписка", request.text)
        self.assertIsInstance(request.reply_markup, ReplyKeyboardRemove)

    async def test_native_stop_action_still_requires_confirmation(self):
        self.db.set_subscriber_roles(self.user_id, ["backend_python"])
        request = await self.command("/stop")
        self.assertIn("Точно отписаться?", request.text)
        self.assertEqual(request.reply_markup.inline_keyboard[0][0].callback_data, "u:yes")
        self.assertEqual(self.db.get_subscriber_roles(self.user_id), ["backend_python"])

    async def test_native_vacancies_action_is_routed_before_fallback(self):
        request = await self.command("/vacancies")
        self.assertIn("Сначала выбери роли", request.text)
        self.assertIsInstance(request.reply_markup, ReplyKeyboardRemove)

    async def test_old_vacancies_button_still_works(self):
        request = await self.command(BTN_NOW)
        self.assertIn("Сначала выбери роли", request.text)
        self.assertIsInstance(request.reply_markup, ReplyKeyboardRemove)

    async def test_old_choose_roles_button_still_works(self):
        request = await self.command(BTN_CHOOSE_ROLES)
        self.assertIn("Шаг 1 из 3", request.text)

    async def test_unknown_text_points_to_native_menu_and_clears_old_panel(self):
        request = await self.command("Привет")
        self.assertIn("«Меню» рядом с полем ввода", request.text)
        self.assertIsInstance(request.reply_markup, ReplyKeyboardRemove)

    async def test_menu_without_subscription_does_not_subscribe(self):
        request = await self.command("/menu")
        self.assertIsInstance(request.reply_markup, ReplyKeyboardRemove)
        self.assertIsNone(self.db.get_subscriber(self.user_id))

    async def test_hide_and_restore_preserve_roles_and_region(self):
        self.db.set_subscriber_roles(self.user_id, ["backend_python", "backend_go"])
        self.db.set_region(self.user_id, "both")
        before = self.db.get_subscriber(self.user_id)
        for command in ("/hide", "/hide", "/menu", "/menu"):
            await self.command(command)
            self.assertEqual(self.db.get_subscriber(self.user_id), before)
            self.assertEqual(self.db.get_region(self.user_id), "both")

    async def test_menu_after_unsubscribe_does_not_resubscribe(self):
        self.db.set_subscriber_roles(self.user_id, ["backend_python"])
        self.db.deactivate_subscriber(self.user_id)
        await self.command("/hide")
        request = await self.command("/menu")
        self.assertIsInstance(request.reply_markup, ReplyKeyboardRemove)
        self.assertEqual(self.db.list_active_subscribers(), [])
