"""The private demo is fail-closed and installed before ordinary fallbacks."""
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram import Router

from bot import chat_main
from bot.config import Settings


class PrivateDemoStartupTest(unittest.IsolatedAsyncioTestCase):
    async def included_routers(self, flag, admin):
        settings = Settings(
            telegram_bot_token="1:test", telegram_chat_id=-100123,
            hh_user_agent="test/1.0", hh_access_token="", timezone="Europe/Moscow",
            max_vacancy_age_hours=72, db_path=Path("/tmp/unused.db"),
            telegram_admin_id=admin,
        )
        dispatcher = MagicMock()
        dispatcher.start_polling = AsyncMock()
        bot = MagicMock()
        bot.session.close = AsyncMock()
        normal_router = Router(name="ordinary_handlers")
        with patch.dict("os.environ", {"APPLICATION_DEMO_ENABLED": flag}), \
                patch.object(chat_main.Settings, "from_env", return_value=settings), \
                patch.object(chat_main, "VacancyDatabase"), \
                patch.object(chat_main, "Bot", return_value=bot), \
                patch.object(chat_main, "Dispatcher", return_value=dispatcher), \
                patch.object(chat_main, "router", normal_router), \
                patch.object(chat_main, "limit_threads"), \
                patch.object(chat_main, "_acquire_single_instance"), \
                patch.object(chat_main, "_release_single_instance"), \
                patch.object(chat_main, "_wait_for_telegram", new_callable=AsyncMock):
            await chat_main.main()
        bot.session.close.assert_awaited_once()
        return [call.args[0].name for call in dispatcher.include_router.call_args_list]

    async def test_disabled_by_default(self):
        self.assertEqual(await self.included_routers("", 123), ["ordinary_handlers"])

    async def test_missing_or_invalid_admin_does_not_enable_demo(self):
        for admin in (None, 0, -123):
            with self.subTest(admin=admin):
                self.assertEqual(await self.included_routers("1", admin), ["ordinary_handlers"])

    async def test_private_demo_precedes_normal_fallback(self):
        self.assertEqual(await self.included_routers("1", 123), ["private_application_demo", "ordinary_handlers"])
