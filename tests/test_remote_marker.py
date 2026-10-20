"""Пометка удалёнки в карточке — только в личных дайджестах, канал не трогаем."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from bot.formatters import format_combined_digest, format_vacancy
from bot.models import Vacancy
from bot.subscriber_formatters import format_subscriber_digest


def _vacancy(location, is_remote, work_format=None):
    return Vacancy(
        source="hh.ru",
        external_id="1",
        title="Product Designer",
        company="Яндекс",
        url="https://hh.ru/vacancy/1",
        location=location,
        work_format=work_format,
        is_remote=is_remote,
        published_at=datetime.now(timezone.utc),
    )


class VacancyCardTest(unittest.TestCase):
    def test_channel_card_unchanged_for_remote(self):
        """Канал должен выглядеть ровно как раньше."""
        card = format_vacancy(_vacancy("Москва", True))
        self.assertIn("📍 Москва", card)
        self.assertNotIn("удалённо", card)

    def test_subscriber_card_marks_remote(self):
        card = format_vacancy(_vacancy("Москва", True), show_remote=True)
        self.assertIn("Москва", card)
        self.assertIn("удалённо", card)

    def test_no_marker_when_not_remote(self):
        card = format_vacancy(_vacancy("Москва", False), show_remote=True)
        self.assertNotIn("удалённо", card)

    def test_no_marker_when_unknown(self):
        card = format_vacancy(_vacancy("Москва", None), show_remote=True)
        self.assertNotIn("удалённо", card)

    def test_no_duplicate_when_location_already_says_remote(self):
        card = format_vacancy(_vacancy("Удалённо", True), show_remote=True)
        self.assertEqual(card.lower().count("удалённо"), 1)

    def test_remote_without_location(self):
        card = format_vacancy(_vacancy(None, True), show_remote=True)
        self.assertIn("Удалённо", card)


class DigestWiringTest(unittest.TestCase):
    def test_subscriber_digest_marks_remote(self):
        messages, _ = format_subscriber_digest(
            "продуктового дизайнера", [_vacancy("Москва", True)], 1
        )
        self.assertIn("удалённо", messages[0])

    def test_channel_digest_does_not_mark_remote(self):
        messages, _ = format_combined_digest([_vacancy("Москва", True)], 1)
        self.assertNotIn("удалённо", messages[0])


if __name__ == "__main__":
    unittest.main()
