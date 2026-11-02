"""Скрытие и возврат меню через настоящую маршрутизацию aiogram, без сети."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

from aiogram import Bot
from aiogram.methods import SendMessage
from aiogram.types import Chat, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove, User

from bot.chat_main import router
from bot.database import VacancyDatabase
from bot.menu import (
    BTN_CHOOSE_ROLES,
    BTN_CHOOSE_ROLES_AGAIN,
    BTN_MY_SUBSCRIPTION,
    BTN_NOW,
    BTN_UNSUBSCRIBE,
)


class MenuVisibilityTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.db = VacancyDatabase(Path(directory.name) / "test.db")
        self.user_id = 999001
        self.session = AsyncMock()
        self.bot = Bot(token="1:test", session=self.session)

    async def command(self, text):
        self.session.reset_mock()
        message = Message(
            message_id=1,
            date=datetime.now(timezone.utc),
            chat=Chat(id=self.user_id, type="private"),
            from_user=User(id=self.user_id, is_bot=False, first_name="А"),
            text=text,
        ).as_(self.bot)
        await router.propagate_event("message", message, db=self.db, bot=self.bot)
        self.session.assert_awaited_once()
        request = self.session.await_args.args[1]
        self.assertIsInstance(request, SendMessage)
        self.assertEqual(request.chat_id, self.user_id)
        return request

    async def test_hide_removes_keyboard_and_explains_how_to_restore_it(self):
        request = await self.command("/hide")
        self.assertIsInstance(request.reply_markup, ReplyKeyboardRemove)
        self.assertEqual(request.reply_markup.model_dump(exclude_none=True), {"remove_keyboard": True})
        self.assertIn("/menu", request.text)
        self.assertIn("продолжают работать", request.text)

    async def test_menu_restores_all_actions_for_subscriber(self):
        self.db.set_subscriber_roles(self.user_id, ["backend_python"])
        request = await self.command("/menu")
        self.assertIsInstance(request.reply_markup, ReplyKeyboardMarkup)
        self.assertEqual(
            [button.text for row in request.reply_markup.keyboard for button in row],
            [BTN_NOW, BTN_MY_SUBSCRIPTION, BTN_UNSUBSCRIBE, BTN_CHOOSE_ROLES_AGAIN],
        )
        self.assertIs(request.reply_markup.model_dump(exclude_none=True)["is_persistent"], False)
        self.assertIn("/hide", request.text)

    async def test_menu_without_subscription_offers_initial_role_selection(self):
        request = await self.command("/menu")
        self.assertEqual(request.reply_markup.keyboard[-1][0].text, BTN_CHOOSE_ROLES)
        self.assertIs(request.reply_markup.is_persistent, False)
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
        self.assertEqual(request.reply_markup.keyboard[-1][0].text, BTN_CHOOSE_ROLES)
        self.assertEqual(self.db.list_active_subscribers(), [])
