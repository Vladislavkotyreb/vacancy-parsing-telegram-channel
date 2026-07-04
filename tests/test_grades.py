import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from bot.database import VacancyDatabase
from bot.dates import parse_iso_datetime
from bot.grades import extract_grade, grade_from_hh_experience, resolve_grade
from bot.formatters import CHANNEL_FOOTER, format_combined_digest, format_vacancy
from bot.models import Vacancy
from bot.stats import format_admin_stats
from bot.subscriber_formatters import format_subscriber_digest


class ExtractGradeTests(unittest.TestCase):
    def test_intern_russian(self):
        self.assertEqual(extract_grade("Стажер UX/UI Дизайнер"), "Стажёр")

    def test_middle_in_parentheses(self):
        self.assertEqual(
            extract_grade("Продуктовый UI/UX Дизайнер GameDev (Middle)"),
            "Middle",
        )

    def test_senior_english(self):
        self.assertEqual(extract_grade("Senior Product Designer"), "Senior")

    def test_lead(self):
        self.assertEqual(extract_grade("Lead Product Designer"), "Lead")

    def test_junior_russian(self):
        self.assertEqual(extract_grade("Младший продуктовый дизайнер"), "Junior")

    def test_beginner_russian(self):
        self.assertEqual(extract_grade("Начинающий UX/UI-Designer"), "Junior")

    def test_no_grade(self):
        self.assertIsNone(extract_grade("Продуктовый дизайнер"))

    def test_head_of(self):
        self.assertEqual(extract_grade("Head of Product Design"), "Head")


class HhExperienceGradeTests(unittest.TestCase):
    def test_middle_experience(self):
        self.assertEqual(grade_from_hh_experience("between3And6"), "Middle")

    def test_title_has_priority(self):
        self.assertEqual(
            resolve_grade("Junior Product Designer", "moreThan6"),
            "Junior",
        )

    def test_fallback_to_experience(self):
        self.assertEqual(
            resolve_grade("Product Designer", "between3And6"),
            "Middle",
        )


class HhDateParsingTests(unittest.TestCase):
    def test_hh_timezone_without_colon(self):
        parsed = parse_iso_datetime("2026-07-02T15:28:41+0300")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.isoformat(), "2026-07-02T12:28:41+00:00")


class FormatVacancyGradeTests(unittest.TestCase):
    def test_grade_on_separate_line(self):
        vacancy = Vacancy(
            source="hh.ru",
            external_id="1",
            title="Senior Product Designer",
            company="Acme",
            url="https://example.com",
        )
        text = format_vacancy(vacancy)
        lines = text.split("\n")
        self.assertIn("🎨 <b>Senior Product Designer</b>", lines[0])
        self.assertEqual(lines[1], "📊 Senior")
        self.assertEqual(lines[2], "🏢 Acme")

    def test_grade_from_vacancy_field(self):
        vacancy = Vacancy(
            source="hh.ru",
            external_id="2",
            title="Продуктовый дизайнер",
            company="Acme",
            url="https://example.com",
            grade="Middle",
        )
        text = format_vacancy(vacancy)
        self.assertIn("📊 Middle", text)

    def test_no_grade_line_when_missing(self):
        vacancy = Vacancy(
            source="hh.ru",
            external_id="3",
            title="Продуктовый дизайнер",
            company="Acme",
            url="https://example.com",
        )
        text = format_vacancy(vacancy)
        self.assertNotIn("📊", text)


class DigestFooterTests(unittest.TestCase):
    def _sample(self) -> Vacancy:
        return Vacancy(
            source="hh.ru",
            external_id="1",
            title="Senior Product Designer",
            company="Acme",
            url="https://example.com",
            published_at=datetime.now(),
        )

    def test_channel_digest_has_footer(self):
        messages, _ = format_combined_digest([self._sample()], 1)
        self.assertIn(CHANNEL_FOOTER, messages[-1])

    def test_subscriber_digest_has_no_footer(self):
        messages, _ = format_subscriber_digest("продуктового дизайнера", [self._sample()], 1)
        self.assertNotIn("prdsvac", messages[-1])
        self.assertNotIn(CHANNEL_FOOTER, messages[-1])


class AdminStatsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = VacancyDatabase(Path(self.tmp.name) / "test.db")
        now = datetime.now(timezone.utc).isoformat()
        with self.db._connect() as conn:
            conn.execute(
                "INSERT INTO subscribers (user_id, role, subscribed_at, active) VALUES (1, 'product_designer', ?, 1)",
                (now,),
            )
            conn.execute(
                "INSERT INTO subscribers (user_id, role, subscribed_at, active) VALUES (2, 'backend_python', ?, 1)",
                (now,),
            )
            conn.execute(
                "INSERT INTO subscriber_roles (user_id, role) VALUES (1, 'product_designer')"
            )
            conn.execute(
                "INSERT INTO subscriber_roles (user_id, role) VALUES (2, 'backend_python')"
            )
            conn.execute(
                """
                INSERT INTO subscriber_sent (user_id, vacancy_uid, dedup_key, sent_at)
                VALUES (1, 'hh.ru:1', 'key1', ?)
                """,
                (now,),
            )
            conn.execute(
                """
                INSERT INTO run_log (started_at, finished_at, found_total, posted_new, status)
                VALUES (?, ?, 10, 3, 'ok')
                """,
                (now, now),
            )

    def test_stats_contains_key_sections(self):
        text = format_admin_stats(self.db, "Europe/Moscow")
        self.assertIn("Активных: <b>2</b>", text)
        self.assertIn("Продуктовый дизайнер", text)
        self.assertIn("Канал @prdsvac", text)
        self.assertIn("Статистика за всё время", text)

    def tearDown(self) -> None:
        self.tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
