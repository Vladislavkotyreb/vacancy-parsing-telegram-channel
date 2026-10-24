"""Старт бота при обрыве сети и сообщение админу из серверных скриптов."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock
from unittest.mock import AsyncMock, MagicMock

from aiogram.exceptions import TelegramNetworkError, TelegramUnauthorizedError

from bot import admin_notify
from bot.chat_main import _wait_for_telegram
from bot.config import Settings


def _net_error() -> TelegramNetworkError:
    return TelegramNetworkError(method=MagicMock(), message="Request timeout error")


def _settings(admin_id=1) -> Settings:
    return Settings(
        telegram_bot_token="1:test", telegram_chat_id=-100123, hh_user_agent="test/1.0",
        hh_access_token="", timezone="Europe/Moscow", max_vacancy_age_hours=72,
        db_path=Path("/tmp/unused.db"), telegram_admin_id=admin_id,
    )


class WaitForTelegramTest(unittest.IsolatedAsyncioTestCase):
    async def test_retries_network_errors_then_starts(self):
        bot = MagicMock()
        bot.get_me = AsyncMock(side_effect=[_net_error(), _net_error(), MagicMock()])
        await _wait_for_telegram(bot, delays=(0, 0, 0))
        self.assertEqual(bot.get_me.await_count, 3)

    async def test_gives_up_after_all_retries(self):
        bot = MagicMock()
        bot.get_me = AsyncMock(side_effect=_net_error())
        with self.assertRaises(TelegramNetworkError):
            await _wait_for_telegram(bot, delays=(0, 0))
        self.assertEqual(bot.get_me.await_count, 3)  # две попытки с паузой + последняя

    async def test_wrong_token_is_not_retried(self):
        bot = MagicMock()
        bot.get_me = AsyncMock(side_effect=TelegramUnauthorizedError(method=MagicMock(), message="Unauthorized"))
        with self.assertRaises(TelegramUnauthorizedError):
            await _wait_for_telegram(bot, delays=(0, 0))
        self.assertEqual(bot.get_me.await_count, 1)


class AdminNotifyTest(unittest.IsolatedAsyncioTestCase):
    def fake_bot(self, side_effect=None):
        bot = MagicMock()
        bot.send_message = AsyncMock(side_effect=side_effect)
        bot.session.close = AsyncMock()
        return bot

    async def test_sends_to_admin_and_retries_network(self):
        bot = self.fake_bot(side_effect=[_net_error(), None])
        with mock.patch("bot.admin_notify.Bot", return_value=bot):
            self.assertTrue(await admin_notify.notify("✅ Выкатил abc", _settings(), pause=0))
        self.assertEqual(bot.send_message.await_args.args, (1, "✅ Выкатил abc"))
        bot.session.close.assert_awaited()

    async def test_reports_failure_after_attempts(self):
        bot = self.fake_bot(side_effect=_net_error())
        with mock.patch("bot.admin_notify.Bot", return_value=bot):
            self.assertFalse(await admin_notify.notify("текст", _settings(), pause=0))
        self.assertEqual(bot.send_message.await_count, admin_notify.ATTEMPTS)

    async def test_no_admin_is_a_quiet_success(self):
        with mock.patch("bot.admin_notify.Bot") as bot_cls:
            self.assertTrue(await admin_notify.notify("текст", _settings(admin_id=None)))
        bot_cls.assert_not_called()


if __name__ == "__main__":
    unittest.main()
