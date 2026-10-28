"""Кнопка «Показать остальные»: остаток урезанной подборки по нажатию, один раз."""

from __future__ import annotations

import asyncio
import re
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from unittest.mock import AsyncMock

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]

from bot.chat_main import cb_digest_more
from bot.config import Settings
from bot.database import VacancyDatabase
from bot.digest_more import DIGEST_MORE, format_more_header
from bot.models import Vacancy
from bot.russian import plural_ru
from bot.subscriber_service import SubscriberService

NOW = datetime.now(timezone.utc)
USER = 10


def _vacancy(n: int, hours_ago: float) -> Vacancy:
    return Vacancy(
        source="hh.ru",
        external_id=str(n),
        title=f"Product Manager {n}",
        company=f"Компания {n}",
        url=f"https://hh.ru/vacancy/{n}",
        published_at=NOW - timedelta(hours=hours_ago),
    )


def _numbers(texts) -> set:
    return {int(n) for n in re.findall(r"Product Manager (\d+)", " ".join(texts))}


class DigestMoreTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        path = Path(tempfile.mkdtemp()) / "test.db"
        self.db = VacancyDatabase(path)
        self.settings = Settings(
            telegram_bot_token="test:token", telegram_chat_id=-100123, hh_user_agent="test/1.0",
            hh_access_token="", timezone="Europe/Moscow", max_vacancy_age_hours=72,
            db_path=path, telegram_admin_id=None,
        )
        self.bot = AsyncMock()
        self.service = SubscriberService(self.settings, self.db, self.bot)
        self.db.set_subscriber_roles(USER, ["product_manager"])
        # 45 новых: в подборку уходят №0–29, остаток — №30–44.
        self.found = [_vacancy(n, hours_ago=1 + n) for n in range(45)]
        self.today = datetime.now(ZoneInfo("Europe/Moscow")).date().isoformat()

    async def run_digest(self):
        async def collect(settings, role):
            return list(self.found)
        with mock.patch("bot.subscriber_service.collect_for_role", side_effect=collect):
            return await self.service.run_daily_digests()

    def calls(self):
        return self.bot.send_message.await_args_list

    def texts(self) -> list:
        return [c.kwargs["text"] for c in self.calls()]

    def press(self, day=None, user_id=USER):
        callback = SimpleNamespace(
            data=f"{DIGEST_MORE}{day or self.today}",
            from_user=SimpleNamespace(id=user_id),
            message=SimpleNamespace(edit_reply_markup=AsyncMock()),
            answer=AsyncMock(),
        )
        return callback

    async def press_and_reset(self, day=None):
        self.bot.send_message.reset_mock()
        callback = self.press(day)
        await cb_digest_more(callback, self.db, self.settings, self.bot)
        return callback

    # --- рассылка ставит кнопку ---

    async def test_capped_digest_gets_button_on_last_message(self):
        await self.run_digest()
        markups = [c.kwargs.get("reply_markup") for c in self.calls()]
        self.assertIsNotNone(markups[-1])
        self.assertTrue(all(m is None for m in markups[:-1]))

        button = markups[-1].inline_keyboard[0][0]
        self.assertEqual(button.text, "Показать остальные 15")
        self.assertEqual(button.callback_data, f"{DIGEST_MORE}{self.today}")
        self.assertLessEqual(len(button.callback_data.encode()), 64)

    async def test_small_digest_has_no_button(self):
        self.found = self.found[:5]
        await self.run_digest()
        from aiogram.types import InlineKeyboardMarkup
        # Кнопки «Показать остальные» нет; нижнее меню (ReplyKeyboard) — есть, это нормально.
        self.assertFalse(any(isinstance(c.kwargs.get("reply_markup"), InlineKeyboardMarkup) for c in self.calls()))

    async def test_overflow_is_not_marked_sent_by_digest(self):
        await self.run_digest()
        self.assertFalse(self.db.is_sent_to_subscriber(USER, "hh.ru:30"))

    # --- нажатие ---

    async def test_press_sends_the_rest_once_and_marks_it(self):
        await self.run_digest()
        callback = await self.press_and_reset()

        self.assertEqual(_numbers(self.texts()), set(range(30, 45)))
        self.assertIn(format_more_header(15), self.texts()[0])
        self.assertTrue(self.db.is_sent_to_subscriber(USER, "hh.ru:44"))
        callback.answer.assert_awaited()
        callback.message.edit_reply_markup.assert_awaited_with(reply_markup=None)

    async def test_second_press_sends_nothing(self):
        await self.run_digest()
        await self.press_and_reset()

        callback = await self.press_and_reset()
        self.bot.send_message.assert_not_awaited()
        self.assertIn("Больше вакансий из этой подборки нет", callback.answer.await_args.args[0])

    async def test_double_tap_at_the_same_time_sends_once(self):
        await self.run_digest()
        self.bot.send_message.reset_mock()

        async def slow_send(**kwargs):
            # Как в жизни: пока идёт запрос к Телеграму, второе нажатие уже обрабатывается.
            await asyncio.sleep(0.01)
        self.bot.send_message.side_effect = slow_send

        first, second = self.press(), self.press()
        await asyncio.gather(
            cb_digest_more(first, self.db, self.settings, self.bot),
            cb_digest_more(second, self.db, self.settings, self.bot),
        )
        numbers = re.findall(r"Product Manager (\d+)", " ".join(self.texts()))
        self.assertEqual(sorted(int(n) for n in numbers), list(range(30, 45)))

    async def test_button_from_another_day_does_nothing(self):
        await self.run_digest()
        callback = await self.press_and_reset(day="2020-01-01")
        self.bot.send_message.assert_not_awaited()
        self.assertIn("Больше вакансий из этой подборки нет", callback.answer.await_args.args[0])
        # Остаток сегодняшней подборки не тронут — кнопка из сегодняшнего дайджеста работает.
        await self.press_and_reset()
        self.assertEqual(_numbers(self.texts()), set(range(30, 45)))

    async def test_someone_elses_button_does_not_leak_overflow(self):
        await self.run_digest()
        self.bot.send_message.reset_mock()
        stranger = self.press(user_id=999)
        await cb_digest_more(stranger, self.db, self.settings, self.bot)
        self.bot.send_message.assert_not_awaited()

    async def test_already_sent_vacancies_are_skipped(self):
        await self.run_digest()
        self.db.mark_sent_to_subscriber(USER, self.found[30])
        await self.press_and_reset()

        self.assertEqual(_numbers(self.texts()), set(range(31, 45)))
        self.assertIn(format_more_header(14), self.texts()[0])

    async def test_next_digest_does_not_repeat_what_button_showed(self):
        await self.run_digest()
        await self.press_and_reset()
        self.bot.send_message.reset_mock()

        stats = await self.run_digest()
        self.assertEqual(_numbers(self.texts()), set())
        self.assertEqual(stats.empty_notices, 1)

    async def test_rerun_without_overflow_disarms_old_button(self):
        await self.run_digest()
        # Повторный прогон в тот же день: остаток ушёл обычной подборкой.
        self.bot.send_message.reset_mock()
        await self.run_digest()
        self.assertEqual(_numbers(self.texts()), set(range(30, 45)))

        await self.press_and_reset()
        self.bot.send_message.assert_not_awaited()

    async def test_failed_send_keeps_button_working(self):
        await self.run_digest()
        self.bot.send_message.reset_mock()
        self.bot.send_message.side_effect = RuntimeError("сеть")
        with self.assertRaises(RuntimeError):
            await cb_digest_more(self.press(), self.db, self.settings, self.bot)
        self.assertFalse(self.db.is_sent_to_subscriber(USER, "hh.ru:30"))

        self.bot.send_message.side_effect = None
        await self.press_and_reset()
        self.assertEqual(_numbers(self.texts()), set(range(30, 45)))


class PluralTest(unittest.TestCase):
    def test_forms(self):
        forms = ("вакансия", "вакансии", "вакансий")
        cases = {1: "вакансия", 2: "вакансии", 4: "вакансии", 5: "вакансий", 11: "вакансий",
                 12: "вакансий", 14: "вакансий", 21: "вакансия", 22: "вакансии", 111: "вакансий"}
        for n, expected in cases.items():
            self.assertEqual(plural_ru(n, *forms), expected, n)

    def test_header(self):
        self.assertEqual(format_more_header(1), "<b>Ещё 1 вакансия из подборки</b>")
        self.assertEqual(format_more_header(15), "<b>Ещё 15 вакансий из подборки</b>")


if __name__ == "__main__":
    unittest.main()
