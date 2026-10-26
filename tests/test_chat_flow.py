"""Флоу подписки без состояния: клавиатуры, черновик из галочек, сохранение."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
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
        self.assertIn("Шаг 3 из 3", self.edited_texts[-1])
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
        self.assertIn("Шаг 2 из 3", self.edited_texts[-1])

        await s1_pick_specialty(self._cb(f"{S1_CAT}design"), self.db)
        self.assertEqual(_draft_from_keyboard(self.message.reply_markup), {"product_designer"})
        self.assertEqual(self.db.get_subscriber_roles(self.user_id), ["product_designer"])

    async def test_empty_continue_clears_category_and_returns_to_step1(self):
        self.db.set_subscriber_roles(self.user_id, ["product_designer", "frontend_react"])

        await s1_pick_specialty(self._cb(f"{S1_CAT}frontend"), self.db)
        await s2_toggle_vacancy(self._cb(f"{S2_ROLE}frontend:frontend_react"), self.db)
        await s2_save(self._cb(f"{S2_SAVE}frontend"), self.db)

        self.assertEqual(self.db.get_subscriber_roles(self.user_id), ["product_designer"])
        self.assertIn("Шаг 2 из 3", self.edited_texts[-1])

    async def test_empty_continue_without_saved_deactivates(self):
        await s1_pick_specialty(self._cb(f"{S1_CAT}design"), self.db)
        await s2_save(self._cb(f"{S2_SAVE}design"), self.db)

        self.assertEqual(self.db.get_subscriber_roles(self.user_id), [])
        self.assertIn("Шаг 2 из 3", self.edited_texts[-1])

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

    def test_leaders_category_and_governance(self):
        labels = [btn.text for row in specialty_keyboard().inline_keyboard for btn in row]
        self.assertIn("Руководители", labels)
        self.assertIn(f"{S2_ROLE}data:data_governance", _callback_data(vacancy_keyboard("data", set())))
        leaders = _callback_data(vacancy_keyboard("leaders", set()))
        for role_id in ("head_of_data", "head_of_ai", "head_of_design", "head_of_product", "head_of_engineering"):
            self.assertIn(f"{S2_ROLE}leaders:{role_id}", leaders)

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


class UnsubscribedUserTest(FlowSimulationTest):
    """Аудит 25.10.2026: отписавшийся молча подписывался обратно."""

    async def test_empty_continue_after_stop_does_not_resubscribe(self):
        self.db.set_subscriber_roles(self.user_id, ["frontend_react", "product_designer"])
        self.db.deactivate_subscriber(self.user_id)
        await s1_pick_specialty(self._cb(f"{S1_CAT}frontend"), self.db)
        self.assertEqual(_draft_from_keyboard(self.message.reply_markup), set(), "старые роли не отмечены")
        await s2_save(self._cb(f"{S2_SAVE}frontend"), self.db)
        self.assertEqual(self.db.get_subscriber_roles(self.user_id), [])
        self.assertEqual(self.db.list_active_subscribers(), [])

    async def test_new_subscription_after_stop_does_not_bring_back_old_roles(self):
        self.db.set_subscriber_roles(self.user_id, ["frontend_react", "product_designer"])
        self.db.deactivate_subscriber(self.user_id)
        await s1_pick_specialty(self._cb(f"{S1_CAT}backend"), self.db)
        await s2_toggle_vacancy(self._cb(f"{S2_ROLE}backend:backend_go"), self.db)
        await s2_save(self._cb(f"{S2_SAVE}backend"), self.db)
        self.assertEqual(self.db.get_subscriber_roles(self.user_id), ["backend_go"])


class CallbackRobustnessTest(FlowSimulationTest):
    """Аудит 25.10.2026: опоздавшие нажатия, кнопки прошлых версий, старые сообщения."""

    async def test_too_old_query_still_shows_confirmation(self):
        from aiogram.exceptions import TelegramBadRequest
        from aiogram.methods import AnswerCallbackQuery

        self.message.reply_markup = vacancy_keyboard("backend", {"backend_go"})
        cb = self._cb(f"{S2_SAVE}backend")
        cb.answer = AsyncMock(side_effect=TelegramBadRequest(AnswerCallbackQuery(callback_query_id="1"), "query is too old"))
        await s2_save(cb, self.db)
        self.assertEqual(self.db.get_subscriber_roles(self.user_id), ["backend_go"])
        self.assertIn("✅ Готово", self.edited_texts[-1])
        self.message.answer.assert_awaited()  # меню тоже ушло

    async def test_old_format_button_gets_an_answer(self):
        from bot.chat_main import STALE_BUTTON_TEXT, stale_button

        cb = self._cb("role:product_designer")
        await stale_button(cb)
        cb.answer.assert_awaited_with(STALE_BUTTON_TEXT, show_alert=True)

    async def test_inaccessible_message_is_answered_not_crashed(self):
        from aiogram.types import CallbackQuery, Chat, InaccessibleMessage, User

        from bot.chat_main import StaleCallbackMiddleware

        event = CallbackQuery(
            id="1", chat_instance="c", data=f"{S2_SAVE}backend",
            from_user=User(id=self.user_id, is_bot=False, first_name="А"),
            message=InaccessibleMessage(chat=Chat(id=self.user_id, type="private"), message_id=5, date=0),
        )
        handler = AsyncMock()
        with mock.patch("bot.chat_main._answer", new=AsyncMock()) as answered:
            await StaleCallbackMiddleware()(handler, event, {})
        handler.assert_not_awaited()
        answered.assert_awaited()


class UnsubscribeConfirmTest(FlowSimulationTest):
    """Отписка — только после подтверждения (просьба подписчика 26.10.2026)."""

    async def test_stop_asks_before_unsubscribing(self):
        from bot.chat_main import UNSUB_NO, UNSUB_YES, unsubscribe_user

        self.db.set_subscriber_roles(self.user_id, ["backend_go"])
        msg = SimpleNamespace(from_user=SimpleNamespace(id=self.user_id), answer=AsyncMock())
        await unsubscribe_user(msg, self.db)
        self.assertEqual(self.db.get_subscriber_roles(self.user_id), ["backend_go"], "ещё подписан")
        text = msg.answer.await_args.args[0]
        self.assertIn("Точно отписаться?", text)
        markup = msg.answer.await_args.kwargs["reply_markup"]
        self.assertEqual(_callback_data(markup), [UNSUB_YES, UNSUB_NO])

    async def test_yes_unsubscribes(self):
        from bot.chat_main import UNSUB_YES, unsub_yes

        self.db.set_subscriber_roles(self.user_id, ["backend_go"])
        await unsub_yes(self._cb(UNSUB_YES), self.db)
        self.assertEqual(self.db.list_active_subscribers(), [])
        self.assertIn("Рассылка остановлена", self.edited_texts[-1])

    async def test_no_keeps_subscription(self):
        from bot.chat_main import UNSUB_NO, unsub_no

        self.db.set_subscriber_roles(self.user_id, ["backend_go"])
        await unsub_no(self._cb(UNSUB_NO), self.db)
        self.assertEqual(self.db.get_subscriber_roles(self.user_id), ["backend_go"])
        self.assertIn("Подписка осталась", self.edited_texts[-1])

    async def test_not_subscribed_gets_no_question(self):
        from bot.chat_main import unsubscribe_user

        msg = SimpleNamespace(from_user=SimpleNamespace(id=self.user_id), answer=AsyncMock())
        await unsubscribe_user(msg, self.db)
        self.assertIn("не подписан", msg.answer.await_args.args[0])

    async def test_buttons_are_not_caught_as_stale(self):
        """Новые кнопки должны доходить до своих обработчиков, а не до «кнопка устарела»."""
        from aiogram import Dispatcher

        from bot.chat_main import UNSUB_NO, UNSUB_YES, router

        handlers = [h.callback.__name__ for h in router.callback_query.handlers]
        self.assertLess(handlers.index("unsub_yes"), handlers.index("stale_button"))
        self.assertLess(handlers.index("unsub_no"), handlers.index("stale_button"))
