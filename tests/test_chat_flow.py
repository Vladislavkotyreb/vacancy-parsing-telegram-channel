"""Проверка флоу подписки: клавиатуры, FSM, сброс при «Назад»."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

from bot.chat_main import (
    S1_CAT,
    S2_BACK,
    S2_ROLE,
    S2_SAVE,
    SubscribeFlow,
    _saved_roles_for_category,
    _show_specialty_step,
    _show_vacancy_step,
    s1_pick_specialty,
    s2_back,
    s2_save,
    s2_toggle_vacancy,
    specialty_keyboard,
    vacancy_keyboard,
)
from bot.database import VacancyDatabase


def _callback_data(keyboard) -> list[str]:
    result = []
    for row in keyboard.inline_keyboard:
        for btn in row:
            result.append(btn.callback_data)
    return result


class KeyboardStructureTest(unittest.TestCase):
    def test_step1_no_continue(self):
        data = _callback_data(specialty_keyboard())
        self.assertEqual(len(data), 3)
        self.assertTrue(all(d.startswith(S1_CAT) for d in data))
        self.assertNotIn("Продолжить", str(data))

    def test_step2_has_back_and_continue(self):
        data = _callback_data(vacancy_keyboard("design", set()))
        self.assertIn(S2_BACK, data)
        self.assertIn(S2_SAVE, data)
        self.assertEqual(data[-2:], [S2_BACK, S2_SAVE])

    def test_step2_toggle_prefixes(self):
        data = _callback_data(vacancy_keyboard("design", set()))
        role_callbacks = [d for d in data if d.startswith(S2_ROLE)]
        self.assertEqual(len(role_callbacks), 3)


class FlowSimulationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db_path = Path(tempfile.mkdtemp()) / "test.db"
        self.db = VacancyDatabase(self.db_path)
        self.storage = MemoryStorage()
        self.user_id = 999001
        self.bot = MagicMock()
        self.bot.id = 1

        self.edited_texts: list[str] = []
        self.edited_keyboards: list = []
        self.answers: list[str] = []

        self.message = SimpleNamespace(
            message_id=1,
            chat=SimpleNamespace(id=self.user_id, type="private"),
            edit_text=AsyncMock(side_effect=self._capture_edit),
            answer=AsyncMock(side_effect=self._capture_answer),
        )

    async def _capture_edit(self, text, **kwargs):
        self.edited_texts.append(text)
        self.edited_keyboards.append(kwargs.get("reply_markup"))

    async def _capture_answer(self, text, **kwargs):
        self.answers.append(text)

    def _ctx(self) -> FSMContext:
        return FSMContext(
            storage=self.storage,
            key=MagicMock(user_id=self.user_id, chat_id=self.user_id, bot_id=1),
        )

    def _cb(self, data: str):
        return SimpleNamespace(
            id="cb1",
            data=data,
            from_user=SimpleNamespace(id=self.user_id),
            message=self.message,
            answer=AsyncMock(),
        )

    async def test_back_discards_unsaved_draft(self):
        state = self._ctx()
        saved = ["product_designer"]
        self.db.set_subscriber_roles(self.user_id, saved)

        await _show_vacancy_step(
            self.message, state, "design", {"product_designer", "communication_designer"}, saved
        )
        data = await state.get_data()
        self.assertIn("communication_designer", data["draft_roles"])

        await s2_back(self._cb(S2_BACK), state, self.db)

        data = await state.get_data()
        self.assertEqual(data.get("category_id"), None)
        self.assertEqual(data.get("draft_roles"), [])
        self.assertEqual(await state.get_state(), SubscribeFlow.specialty.state)

        kb = self.edited_keyboards[-1]
        self.assertEqual(_callback_data(kb), [f"{S1_CAT}design", f"{S1_CAT}frontend", f"{S1_CAT}backend"])

        await s1_pick_specialty(self._cb(f"{S1_CAT}design"), state, self.db)
        data = await state.get_data()
        self.assertEqual(data["draft_roles"], ["product_designer"])
        self.assertNotIn("communication_designer", data["draft_roles"])

    async def test_save_persists_roles(self):
        state = self._ctx()
        await _show_vacancy_step(
            self.message, state, "design", {"graphic_designer"}, []
        )
        await s2_save(self._cb(S2_SAVE), state, self.db)
        roles = self.db.get_subscriber_roles(self.user_id)
        self.assertEqual(roles, ["graphic_designer"])

    async def test_toggle_updates_draft(self):
        state = self._ctx()
        await _show_vacancy_step(self.message, state, "frontend", set(), [])
        await s2_toggle_vacancy(self._cb(f"{S2_ROLE}frontend_react"), state, self.db)
        data = await state.get_data()
        self.assertEqual(data["draft_roles"], ["frontend_react"])
        self.assertIn("Сейчас отмечено", self.edited_texts[-1])
        self.assertIn("React", self.edited_texts[-1])

    async def test_s1_goes_directly_to_step2(self):
        state = self._ctx()
        await _show_specialty_step(self.message, state)
        await s1_pick_specialty(self._cb(f"{S1_CAT}backend"), state, self.db)
        self.assertEqual(await state.get_state(), SubscribeFlow.vacancy.state)
        data = await state.get_data()
        self.assertEqual(data["category_id"], "backend")
        kb = self.edited_keyboards[-1]
        self.assertIn(S2_BACK, _callback_data(kb))

    async def test_clear_category_roles_with_empty_save(self):
        state = self._ctx()
        self.db.set_subscriber_roles(
            self.user_id,
            ["product_designer", "backend_python", "backend_java", "backend_go"],
        )
        await _show_vacancy_step(
            self.message,
            state,
            "backend",
            set(),
            self.db.get_subscriber_roles(self.user_id),
        )
        await s2_save(self._cb(S2_SAVE), state, self.db)
        roles = self.db.get_subscriber_roles(self.user_id)
        self.assertEqual(roles, ["product_designer"])
        self.assertNotIn("backend_python", roles)


if __name__ == "__main__":
    unittest.main()
