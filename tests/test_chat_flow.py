"""Флоу подписки без состояния: клавиатуры, черновик из галочек, сохранение."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.chat_main import (
    S1_CAT,
    S2_BACK,
    S2_ROLE,
    S2_SAVE,
    _draft_from_keyboard,
    _saved_roles_for_category,
    _show_vacancy_step,
    s1_pick_specialty,
    s2_back,
    s2_save,
    s2_toggle_vacancy,
    specialty_keyboard,
    vacancy_keyboard,
)
from bot.database import VacancyDatabase
from bot.role_categories import CATEGORY_IDS


def _callback_data(keyboard) -> list[str]:
    return [btn.callback_data for row in keyboard.inline_keyboard for btn in row]


class KeyboardStructureTest(unittest.TestCase):
    def test_step1_lists_every_category(self):
        data = _callback_data(specialty_keyboard())
        self.assertEqual(data, [f"{S1_CAT}{cid}" for cid in CATEGORY_IDS])
        self.assertNotIn("Продолжить", str(data))

    def test_role_callbacks_carry_category(self):
        data = _callback_data(vacancy_keyboard("design", set()))
        self.assertIn(f"{S2_ROLE}design:product_designer", data)
        self.assertIn(f"{S2_ROLE}design:graphic_designer", data)

    def test_save_callback_carries_category(self):
        data = _callback_data(vacancy_keyboard("frontend", set()))
        self.assertIn(f"{S2_SAVE}frontend", data)
        self.assertIn(S2_BACK, data)

    def test_callback_data_fits_telegram_limit(self):
        for category_id in CATEGORY_IDS:
            for data in _callback_data(vacancy_keyboard(category_id, set())):
                self.assertLessEqual(len(data.encode()), 64, data)

    def test_unknown_category_gives_empty_keyboard(self):
        self.assertEqual(vacancy_keyboard("nope", set()).inline_keyboard, [])


class DraftFromKeyboardTest(unittest.TestCase):
    def test_reads_marked_roles(self):
        keyboard = vacancy_keyboard("design", {"product_designer", "graphic_designer"})
        self.assertEqual(
            _draft_from_keyboard(keyboard),
            {"product_designer", "graphic_designer"},
        )

    def test_empty_when_nothing_marked(self):
        self.assertEqual(_draft_from_keyboard(vacancy_keyboard("design", set())), set())

    def test_empty_when_no_markup(self):
        self.assertEqual(_draft_from_keyboard(None), set())

    def test_ignores_back_and_continue(self):
        keyboard = vacancy_keyboard("frontend", {"frontend_react"})
        self.assertEqual(_draft_from_keyboard(keyboard), {"frontend_react"})


class FlowSimulationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db_path = Path(tempfile.mkdtemp()) / "test.db"
        self.db = VacancyDatabase(self.db_path)
        self.user_id = 999001

        self.edited_texts: list[str] = []
        self.edited_keyboards: list = []

        self.message = SimpleNamespace(
            message_id=1,
            chat=SimpleNamespace(id=self.user_id, type="private"),
            reply_markup=None,
            edit_text=AsyncMock(side_effect=self._capture_edit),
            answer=AsyncMock(),
        )

    async def _capture_edit(self, text, **kwargs):
        self.edited_texts.append(text)
        markup = kwargs.get("reply_markup")
        self.edited_keyboards.append(markup)
        # Telegram оставляет клавиатуру на сообщении — именно она и есть состояние.
        self.message.reply_markup = markup

    def _cb(self, data: str, message=None):
        return SimpleNamespace(
            id="cb1",
            data=data,
            from_user=SimpleNamespace(id=self.user_id),
            message=message or self.message,
            answer=AsyncMock(),
        )

    async def test_pick_specialty_opens_step2(self):
        await s1_pick_specialty(self._cb(f"{S1_CAT}frontend"), self.db)
        self.assertIn("Шаг 2 из 2", self.edited_texts[-1])
        self.assertIn(f"{S2_SAVE}frontend", _callback_data(self.edited_keyboards[-1]))

    async def test_toggle_marks_role(self):
        await s1_pick_specialty(self._cb(f"{S1_CAT}design"), self.db)
        await s2_toggle_vacancy(self._cb(f"{S2_ROLE}design:product_designer"), self.db)

        self.assertEqual(_draft_from_keyboard(self.message.reply_markup), {"product_designer"})

    async def test_toggle_twice_unmarks_role(self):
        await s1_pick_specialty(self._cb(f"{S1_CAT}design"), self.db)
        await s2_toggle_vacancy(self._cb(f"{S2_ROLE}design:product_designer"), self.db)
        await s2_toggle_vacancy(self._cb(f"{S2_ROLE}design:product_designer"), self.db)

        self.assertEqual(_draft_from_keyboard(self.message.reply_markup), set())

    async def test_save_persists_selected_roles(self):
        await s1_pick_specialty(self._cb(f"{S1_CAT}backend"), self.db)
        await s2_toggle_vacancy(self._cb(f"{S2_ROLE}backend:backend_go"), self.db)
        await s2_toggle_vacancy(self._cb(f"{S2_ROLE}backend:backend_python"), self.db)
        await s2_save(self._cb(f"{S2_SAVE}backend"), self.db)

        self.assertEqual(
            self.db.get_subscriber_roles(self.user_id),
            ["backend_go", "backend_python"],
        )
        self.assertIn("✅ Готово", self.edited_texts[-1])

    async def test_save_keeps_roles_of_other_categories(self):
        self.db.set_subscriber_roles(self.user_id, ["product_designer"])

        await s1_pick_specialty(self._cb(f"{S1_CAT}frontend"), self.db)
        await s2_toggle_vacancy(self._cb(f"{S2_ROLE}frontend:frontend_vue"), self.db)
        await s2_save(self._cb(f"{S2_SAVE}frontend"), self.db)

        self.assertEqual(
            self.db.get_subscriber_roles(self.user_id),
            ["frontend_vue", "product_designer"],
        )

    async def test_back_discards_unsaved_draft(self):
        self.db.set_subscriber_roles(self.user_id, ["product_designer"])

        await s1_pick_specialty(self._cb(f"{S1_CAT}design"), self.db)
        await s2_toggle_vacancy(self._cb(f"{S2_ROLE}design:graphic_designer"), self.db)
        self.assertEqual(
            _draft_from_keyboard(self.message.reply_markup),
            {"product_designer", "graphic_designer"},
        )

        await s2_back(self._cb(S2_BACK))
        self.assertIn("Шаг 1 из 2", self.edited_texts[-1])

        await s1_pick_specialty(self._cb(f"{S1_CAT}design"), self.db)
        self.assertEqual(_draft_from_keyboard(self.message.reply_markup), {"product_designer"})
        self.assertEqual(self.db.get_subscriber_roles(self.user_id), ["product_designer"])

    async def test_empty_continue_clears_category_and_returns_to_step1(self):
        self.db.set_subscriber_roles(self.user_id, ["product_designer", "frontend_react"])

        await s1_pick_specialty(self._cb(f"{S1_CAT}frontend"), self.db)
        await s2_toggle_vacancy(self._cb(f"{S2_ROLE}frontend:frontend_react"), self.db)
        await s2_save(self._cb(f"{S2_SAVE}frontend"), self.db)

        self.assertEqual(self.db.get_subscriber_roles(self.user_id), ["product_designer"])
        self.assertIn("Шаг 1 из 2", self.edited_texts[-1])

    async def test_empty_continue_without_saved_deactivates(self):
        await s1_pick_specialty(self._cb(f"{S1_CAT}design"), self.db)
        await s2_save(self._cb(f"{S2_SAVE}design"), self.db)

        self.assertEqual(self.db.get_subscriber_roles(self.user_id), [])
        self.assertIn("Шаг 1 из 2", self.edited_texts[-1])

    async def test_keyboard_still_works_after_restart(self):
        """Главное: рестарт процесса не должен ломать уже показанную клавиатуру."""
        await _show_vacancy_step(self.message, "design", {"product_designer"}, [])
        keyboard_before = self.message.reply_markup

        # Перезапуск: в памяти не осталось ничего от прошлого взаимодействия.
        # У пользователя в чате есть только сообщение с этой клавиатурой.
        self.edited_keyboards.clear()
        restarted_message = SimpleNamespace(
            message_id=1,
            chat=SimpleNamespace(id=self.user_id, type="private"),
            reply_markup=keyboard_before,
            edit_text=AsyncMock(side_effect=self._capture_edit),
            answer=AsyncMock(),
        )

        await s2_toggle_vacancy(
            self._cb(f"{S2_ROLE}design:graphic_designer", message=restarted_message),
            self.db,
        )

        self.assertEqual(
            _draft_from_keyboard(self.edited_keyboards[-1]),
            {"product_designer", "graphic_designer"},
        )

    async def test_toggle_without_markup_adds_role(self):
        self.message.reply_markup = None
        await s2_toggle_vacancy(self._cb(f"{S2_ROLE}design:product_designer"), self.db)
        self.assertEqual(_draft_from_keyboard(self.message.reply_markup), {"product_designer"})

    async def test_unknown_category_shows_alert(self):
        callback = self._cb(f"{S2_ROLE}nope:product_designer")
        await s2_toggle_vacancy(callback, self.db)
        callback.answer.assert_awaited_once()
        self.assertEqual(self.edited_texts, [])


class ProductAndQaCategoriesTest(unittest.TestCase):
    def test_step1_offers_product_and_qa(self):
        labels = [
            btn.text
            for row in specialty_keyboard().inline_keyboard
            for btn in row
        ]
        self.assertIn("Продукт", labels)
        self.assertIn("QA", labels)

    def test_product_category_roles(self):
        data = _callback_data(vacancy_keyboard("product", set()))
        self.assertIn(f"{S2_ROLE}product:product_manager", data)
        self.assertIn(f"{S2_ROLE}product:product_owner", data)
        self.assertIn(f"{S2_SAVE}product", data)

    def test_qa_category_roles(self):
        data = _callback_data(vacancy_keyboard("qa", set()))
        self.assertIn(f"{S2_ROLE}qa:qa_manual", data)
        self.assertIn(f"{S2_ROLE}qa:qa_automation", data)

    def test_design_category_offers_art_director(self):
        keyboard = vacancy_keyboard("design", set())
        self.assertIn(f"{S2_ROLE}design:art_director", _callback_data(keyboard))
        labels = [btn.text for row in keyboard.inline_keyboard for btn in row]
        self.assertIn("Арт-директор", labels)

    def test_data_category(self):
        labels = [btn.text for row in specialty_keyboard().inline_keyboard for btn in row]
        self.assertIn("Data", labels)
        data = _callback_data(vacancy_keyboard("data", set()))
        for role_id in ("data_scientist", "ml_engineer", "data_engineer", "data_analyst", "product_analyst"):
            self.assertIn(f"{S2_ROLE}data:{role_id}", data)

    def test_draft_reads_new_categories(self):
        keyboard = vacancy_keyboard("qa", {"qa_automation"})
        self.assertEqual(_draft_from_keyboard(keyboard), {"qa_automation"})


class SavedRolesForCategoryTest(unittest.TestCase):
    def test_filters_to_category(self):
        saved = ["product_designer", "frontend_react", "backend_go"]
        self.assertEqual(_saved_roles_for_category(saved, "design"), ["product_designer"])
        self.assertEqual(_saved_roles_for_category(saved, "frontend"), ["frontend_react"])

    def test_unknown_category_is_empty(self):
        self.assertEqual(_saved_roles_for_category(["product_designer"], "nope"), [])


if __name__ == "__main__":
    unittest.main()
