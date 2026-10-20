"""Экран «Фильтры»: один тумблер, состояние берётся из БД, без черновика."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.chat_main import (
    BTN_FILTERS,
    F_DONE,
    F_REMOTE,
    MARK,
    btn_filters,
    cb_filters_done,
    cb_toggle_remote,
    filters_keyboard,
    main_menu_keyboard,
    send_subscription_info,
)
from bot.database import VacancyDatabase


def _buttons(keyboard):
    return [btn for row in keyboard.inline_keyboard for btn in row]


class FiltersKeyboardTest(unittest.TestCase):
    def test_menu_has_filters_button(self):
        labels = [
            btn.text
            for row in main_menu_keyboard(subscribed=True).keyboard
            for btn in row
        ]
        self.assertIn(BTN_FILTERS, labels)

    def test_off_state_offers_to_turn_on(self):
        toggle = _buttons(filters_keyboard(include_remote=False))[0]
        self.assertFalse(toggle.text.startswith(MARK))
        self.assertEqual(toggle.callback_data, f"{F_REMOTE}on")

    def test_on_state_is_marked_and_offers_to_turn_off(self):
        toggle = _buttons(filters_keyboard(include_remote=True))[0]
        self.assertTrue(toggle.text.startswith(MARK))
        self.assertEqual(toggle.callback_data, f"{F_REMOTE}off")

    def test_has_done_button(self):
        data = [btn.callback_data for btn in _buttons(filters_keyboard(False))]
        self.assertIn(F_DONE, data)

    def test_callback_data_fits_telegram_limit(self):
        for include_remote in (True, False):
            for btn in _buttons(filters_keyboard(include_remote)):
                self.assertLessEqual(len(btn.callback_data.encode()), 64)


class FiltersHandlersTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db = VacancyDatabase(Path(self._tmp.name) / "test.db")
        self.user_id = 4242

        self.edited: list[str] = []
        self.answered: list[str] = []
        self.message = SimpleNamespace(
            from_user=SimpleNamespace(id=self.user_id),
            edit_text=AsyncMock(side_effect=self._capture_edit),
            answer=AsyncMock(side_effect=self._capture_answer),
        )

    async def _capture_edit(self, text, **kwargs):
        self.edited.append(text)
        self.last_markup = kwargs.get("reply_markup")

    async def _capture_answer(self, text, **kwargs):
        self.answered.append(text)
        self.last_markup = kwargs.get("reply_markup")

    def _cb(self, data: str):
        return SimpleNamespace(
            id="cb",
            data=data,
            from_user=SimpleNamespace(id=self.user_id),
            message=self.message,
            answer=AsyncMock(),
        )

    async def test_toggle_on_persists(self):
        await cb_toggle_remote(self._cb(f"{F_REMOTE}on"), self.db)
        self.assertTrue(self.db.get_include_remote(self.user_id))

    async def test_toggle_off_persists(self):
        self.db.set_include_remote(self.user_id, True)
        await cb_toggle_remote(self._cb(f"{F_REMOTE}off"), self.db)
        self.assertFalse(self.db.get_include_remote(self.user_id))

    async def test_toggle_rerenders_new_state(self):
        await cb_toggle_remote(self._cb(f"{F_REMOTE}on"), self.db)
        toggle = _buttons(self.last_markup)[0]
        self.assertEqual(toggle.callback_data, f"{F_REMOTE}off")

    async def test_screen_shows_state_from_db(self):
        self.db.set_include_remote(self.user_id, True)
        await btn_filters(self.message, self.db)
        toggle = _buttons(self.last_markup)[0]
        self.assertTrue(toggle.text.startswith(MARK))

    async def test_warns_about_silence_when_on(self):
        await cb_toggle_remote(self._cb(f"{F_REMOTE}on"), self.db)
        self.assertIn("не будет", self.edited[-1])

    async def test_done_drops_keyboard(self):
        await cb_filters_done(self._cb(F_DONE), self.db)
        self.assertIsNone(self.last_markup)

    async def test_subscription_info_mentions_filter(self):
        self.db.set_subscriber_roles(self.user_id, ["product_designer"])
        self.db.set_include_remote(self.user_id, True)
        await send_subscription_info(self.message, self.db)
        self.assertIn("удал", self.answered[-1].lower())


if __name__ == "__main__":
    unittest.main()
