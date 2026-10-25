"""Фильтр по уровню (bot/grade_filter.py), выбор уровня в боте и ссылка «переслать коллеге»."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from unittest.mock import AsyncMock

from bot.chat_main import (
    G_SAVE,
    G_TOGGLE,
    _levels_from_keyboard,
    cmd_start,
    g_save,
    g_toggle,
    level_keyboard,
)
from bot.config import Settings
from bot.database import VacancyDatabase, _vacancy_from_json, _vacancy_to_json
from bot.grade_filter import filter_by_levels, levels_phrase, normalize_levels, vacancy_levels
from bot.models import Vacancy
from bot.stats import format_admin_stats
from bot.subscriber_formatters import format_subscriber_digest
from bot.subscriber_service import SubscriberService


def _v(title: str, n: int = 1, source: str = "getmatch.ru", **kw) -> Vacancy:
    return Vacancy(source=source, external_id=str(n), title=title, company=f"К{n}",
                   url=f"https://x/{n}", published_at=datetime.now(timezone.utc), **kw)


class VacancyLevelsTest(unittest.TestCase):
    def test_title_grade(self):
        self.assertEqual(vacancy_levels(_v("Senior Python Developer")), {"senior"})
        self.assertEqual(vacancy_levels(_v("Junior QA")), {"junior"})
        self.assertEqual(vacancy_levels(_v("Стажёр-аналитик")), {"junior"})
        self.assertEqual(vacancy_levels(_v("Team Lead C# (.net)")), {"lead"})
        self.assertEqual(vacancy_levels(_v("Head of Design")), {"lead"})

    def test_russian_titles_missing_in_grades_module(self):
        self.assertEqual(vacancy_levels(_v("Ведущий разработчик C#")), {"senior"})
        self.assertEqual(vacancy_levels(_v("Руководитель направления Frontend")), {"lead"})
        self.assertEqual(vacancy_levels(_v("Тимлид backend")), {"lead"})

    def test_hh_experience_is_a_range(self):
        v = _v("Python-разработчик", source="hh.ru", grade="Junior", experience="between1And3")
        self.assertEqual(vacancy_levels(v), {"junior", "middle"})
        v = _v("Python-разработчик", source="hh.ru", grade="Senior", experience="moreThan6")
        self.assertEqual(vacancy_levels(v), {"senior", "lead"})

    def test_title_beats_hh_experience(self):
        v = _v("Senior Go developer", source="hh.ru", experience="between1And3")
        self.assertEqual(vacancy_levels(v), {"senior"})

    def test_habr_qualification(self):
        self.assertEqual(vacancy_levels(_v("Go-разработчик", source="career.habr.com", grade="Middle")), {"middle"})

    def test_unknown(self):
        self.assertIsNone(vacancy_levels(_v("C#/.NET-разработчик")))


class FilterByLevelsTest(unittest.TestCase):
    def setUp(self):
        self.senior = _v("Senior Java Developer", 1)
        self.junior = _v("Junior Java Developer", 2)
        self.unknown = _v("Java-разработчик", 3)
        self.hh_1_3 = _v("Java-разработчик", 4, source="hh.ru", grade="Junior", experience="between1And3")
        self.all = [self.senior, self.junior, self.unknown, self.hh_1_3]

    def test_no_choice_keeps_everything(self):
        self.assertEqual(filter_by_levels(self.all, []), self.all)

    def test_all_four_is_same_as_no_choice(self):
        self.assertEqual(normalize_levels(["lead", "junior", "senior", "middle"]), [])
        self.assertEqual(filter_by_levels(self.all, ["junior", "middle", "senior", "lead"]), self.all)

    def test_unknown_level_is_never_dropped(self):
        for levels in (["junior"], ["middle"], ["senior"], ["lead"]):
            self.assertIn(self.unknown, filter_by_levels(self.all, levels), levels)

    def test_senior_drops_junior(self):
        result = filter_by_levels(self.all, ["senior"])
        self.assertIn(self.senior, result)
        self.assertNotIn(self.junior, result)
        self.assertNotIn(self.hh_1_3, result)

    def test_middle_keeps_hh_one_to_three_years(self):
        self.assertIn(self.hh_1_3, filter_by_levels(self.all, ["middle"]))

    def test_phrase(self):
        self.assertEqual(levels_phrase([]), "все уровни")
        self.assertEqual(levels_phrase(["senior", "middle"]), "Middle, Senior")


class GradeStorageTest(unittest.TestCase):
    def setUp(self):
        self.db = VacancyDatabase(Path(tempfile.mkdtemp()) / "t.db")

    def test_default_is_all(self):
        self.assertEqual(self.db.get_grades(1), [])

    def test_roundtrip_normalized(self):
        self.db.set_grades(1, ["senior", "junior", "junk"])
        self.assertEqual(self.db.get_grades(1), ["junior", "senior"])
        self.db.set_grades(1, [])
        self.assertEqual(self.db.get_grades(1), [])

    def test_overflow_json_tolerates_unknown_fields(self):
        raw = _vacancy_to_json(_v("X", experience="between1And3")).replace('"experience"', '"future_field"')
        self.assertEqual(_vacancy_from_json(raw).title, "X")


class CameFromTest(unittest.TestCase):
    def setUp(self):
        self.db = VacancyDatabase(Path(tempfile.mkdtemp()) / "t.db")

    def _seen(self, user_id):
        self.db.record_activity(user_id, None, "Имя", None, day="2026-10-25")

    def test_new_user_is_counted_once(self):
        self._seen(1)
        self.db.remember_came_from(1, "share")
        self.db.remember_came_from(1, "other")
        self.assertEqual(self.db.came_from_stats("share"), (1, 0))
        self.db.set_subscriber_roles(1, ["backend_go"])
        self.assertEqual(self.db.came_from_stats("share"), (1, 1))

    def test_existing_subscriber_is_not_counted(self):
        self.db.set_subscriber_roles(2, ["backend_go"])
        self._seen(2)
        self.db.remember_came_from(2, "share")
        self.assertEqual(self.db.came_from_stats("share"), (0, 0))

    def test_stats_line(self):
        self._seen(1)
        self.db.remember_came_from(1, "share")
        self.assertIn("Пришли по ссылке из подборки: 1, из них подписаны 0",
                      format_admin_stats(self.db, "Europe/Moscow"))


class LevelPickerFlowTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = VacancyDatabase(Path(tempfile.mkdtemp()) / "t.db")
        self.user_id = 5
        self.message = SimpleNamespace(
            reply_markup=level_keyboard(set()),
            edit_reply_markup=AsyncMock(side_effect=self._capture_markup),
            edit_text=AsyncMock(),
            answer=AsyncMock(),
        )

    async def _capture_markup(self, reply_markup=None, **kw):
        self.message.reply_markup = reply_markup

    def _cb(self, data):
        return SimpleNamespace(data=data, from_user=SimpleNamespace(id=self.user_id),
                               message=self.message, answer=AsyncMock())

    async def test_toggle_and_save(self):
        await g_toggle(self._cb(f"{G_TOGGLE}senior"))
        await g_toggle(self._cb(f"{G_TOGGLE}lead"))
        await g_toggle(self._cb(f"{G_TOGGLE}lead"))
        self.assertEqual(_levels_from_keyboard(self.message.reply_markup), {"senior"})
        await g_save(self._cb(G_SAVE), self.db)
        self.assertEqual(self.db.get_grades(self.user_id), ["senior"])
        self.assertIn("Senior", self.message.edit_text.await_args.args[0])

    async def test_save_nothing_means_all(self):
        self.db.set_grades(self.user_id, ["junior"])
        await g_save(self._cb(G_SAVE), self.db)
        self.assertEqual(self.db.get_grades(self.user_id), [])

    async def test_unknown_level_rejected(self):
        cb = self._cb(f"{G_TOGGLE}cto")
        await g_toggle(cb)
        self.assertTrue(cb.answer.await_args.kwargs.get("show_alert"))

    def test_callbacks_fit_telegram_limit(self):
        for row in level_keyboard(set()).inline_keyboard:
            for button in row:
                self.assertLessEqual(len(button.callback_data.encode()), 64)


class StartPayloadTest(unittest.IsolatedAsyncioTestCase):
    async def test_start_share_records_source(self):
        db = VacancyDatabase(Path(tempfile.mkdtemp()) / "t.db")
        db.record_activity(7, None, "Имя", None, day="2026-10-25")
        message = SimpleNamespace(text="/start share", from_user=SimpleNamespace(id=7), answer=AsyncMock())
        await cmd_start(message, db)
        self.assertEqual(db.came_from_stats("share"), (1, 0))

    async def test_plain_start_records_nothing(self):
        db = VacancyDatabase(Path(tempfile.mkdtemp()) / "t.db")
        db.record_activity(7, None, "Имя", None, day="2026-10-25")
        message = SimpleNamespace(text="/start", from_user=SimpleNamespace(id=7), answer=AsyncMock())
        await cmd_start(message, db)
        self.assertEqual(db.came_from_stats("share"), (0, 0))


class ShareFooterTest(unittest.TestCase):
    def test_footer_on_last_message(self):
        messages, _ = format_subscriber_digest("Go", [_v("Go dev")], 1, share_url="https://t.me/bot?start=share")
        self.assertIn('href="https://t.me/bot?start=share"', messages[-1])

    def test_no_footer_without_url(self):
        messages, _ = format_subscriber_digest("Go", [_v("Go dev")], 1)
        self.assertNotIn("t.me/", messages[-1])

    def test_footer_never_overflows_telegram_limit(self):
        many = [_v("Go dev " + "x" * 200, n) for n in range(40)]
        messages, _ = format_subscriber_digest("Go", many, 40, share_url="https://t.me/bot?start=share")
        self.assertTrue(all(len(m) <= 4096 for m in messages))


class DigestUsesLevelsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        path = Path(tempfile.mkdtemp()) / "t.db"
        self.db = VacancyDatabase(path)
        settings = Settings(
            telegram_bot_token="test:token", telegram_chat_id=-100123, hh_user_agent="test/1.0",
            hh_access_token="", timezone="Europe/Moscow", max_vacancy_age_hours=72,
            db_path=path, telegram_admin_id=None,
        )
        self.bot = AsyncMock()
        self.bot.get_me.return_value = SimpleNamespace(username="it_vac_bot")
        self.service = SubscriberService(settings, self.db, self.bot)
        self.found = [_v("Senior Go developer", 1), _v("Junior Go developer", 2), _v("Go-разработчик", 3)]

    async def _run(self):
        async def collect(settings, role):
            return list(self.found)
        with mock.patch("bot.subscriber_service.collect_for_role", side_effect=collect):
            await self.service.run_daily_digests()
        return " ".join(c.kwargs["text"] for c in self.bot.send_message.await_args_list)

    async def test_senior_subscriber_gets_senior_and_unknown(self):
        self.db.set_subscriber_roles(10, ["backend_go"])
        self.db.set_grades(10, ["senior"])
        text = await self._run()
        self.assertIn("Senior Go developer", text)
        self.assertIn("Go-разработчик", text)
        self.assertNotIn("Junior Go developer", text)
        self.assertIn("https://t.me/it_vac_bot?start=share", text)

    async def test_without_levels_everything_arrives(self):
        self.db.set_subscriber_roles(10, ["backend_go"])
        text = await self._run()
        for v in self.found:
            self.assertIn(v.title, text)


if __name__ == "__main__":
    unittest.main()
