import unittest
from datetime import datetime

from bot.grades import extract_grade
from bot.formatters import CHANNEL_FOOTER, format_combined_digest, format_vacancy
from bot.models import Vacancy
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

    def test_no_grade(self):
        self.assertIsNone(extract_grade("Продуктовый дизайнер"))

    def test_head_of(self):
        self.assertEqual(extract_grade("Head of Product Design"), "Head")


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

    def test_no_grade_line_when_missing(self):
        vacancy = Vacancy(
            source="hh.ru",
            external_id="2",
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


if __name__ == "__main__":
    unittest.main()
