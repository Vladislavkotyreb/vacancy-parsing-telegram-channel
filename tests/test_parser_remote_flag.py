"""Каждая площадка должна отдавать is_remote, а не терять формат работы."""

from __future__ import annotations

import unittest
from pathlib import Path

from bot.config import Settings
from bot.parsers.geekjob import GeekJobParser
from bot.parsers.getmatch import GetMatchParser
from bot.parsers.hh import HHParser


def _settings() -> Settings:
    return Settings(
        telegram_bot_token="x",
        telegram_chat_id=-1,
        hh_user_agent="test",
        hh_access_token="",
        timezone="Europe/Moscow",
        max_vacancy_age_hours=72,
        db_path=Path("/tmp/unused.db"),
        telegram_admin_id=None,
    )


class HHRemoteFlagTest(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = HHParser(_settings())

    def _item(self, schedule):
        item = {
            "id": "1",
            "name": "Product Designer",
            "alternate_url": "https://hh.ru/vacancy/1",
            "employer": {"name": "Яндекс"},
        }
        if schedule is not None:
            item["schedule"] = schedule
        return item

    def test_remote_schedule(self):
        vacancy = self.parser._parse_item(self._item({"id": "remote"}))
        self.assertIs(vacancy.is_remote, True)
        self.assertEqual(vacancy.work_format, "Удалённо")

    def test_office_schedule_is_known_not_remote(self):
        vacancy = self.parser._parse_item(self._item({"id": "fullDay"}))
        self.assertIs(vacancy.is_remote, False)

    def test_missing_schedule_is_unknown(self):
        vacancy = self.parser._parse_item(self._item(None))
        self.assertIsNone(vacancy.is_remote)

    def test_null_schedule_is_unknown(self):
        item = self._item(None)
        item["schedule"] = None
        vacancy = self.parser._parse_item(item)
        self.assertIsNone(vacancy.is_remote)


class GeekJobRemoteFlagTest(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = GeekJobParser()

    def _item(self, job_format):
        item = {"id": "7", "position": "UX Designer", "company": {"name": "Ozon"}}
        if job_format is not None:
            item["jobFormat"] = job_format
        return item

    def test_remote_flag(self):
        vacancy = self.parser._parse_item(self._item({"remote": True, "inhouse": False}))
        self.assertIs(vacancy.is_remote, True)

    def test_inhouse_only_is_known_not_remote(self):
        vacancy = self.parser._parse_item(self._item({"remote": False, "inhouse": True}))
        self.assertIs(vacancy.is_remote, False)

    def test_missing_job_format_is_unknown(self):
        vacancy = self.parser._parse_item(self._item(None))
        self.assertIsNone(vacancy.is_remote)


class GetMatchRemoteFlagTest(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = GetMatchParser()

    def _offer(self, location_requirements):
        offer = {"id": "42", "position": "Product Designer", "url": "/vacancies/42"}
        if location_requirements is not None:
            offer["location_requirements"] = location_requirements
        return offer

    def test_remote_format(self):
        vacancy = self.parser._parse_item(
            self._offer([{"country": "Россия", "format": "remote"}])
        )
        self.assertIs(vacancy.is_remote, True)

    def test_remote_among_several_locations(self):
        vacancy = self.parser._parse_item(
            self._offer(
                [
                    {"country": "Россия", "format": "office"},
                    {"country": "Грузия", "format": "remote"},
                ]
            )
        )
        self.assertIs(vacancy.is_remote, True)

    def test_office_only_is_known_not_remote(self):
        vacancy = self.parser._parse_item(
            self._offer([{"country": "Россия", "format": "office"}])
        )
        self.assertIs(vacancy.is_remote, False)

    def test_missing_locations_is_unknown(self):
        vacancy = self.parser._parse_item(self._offer(None))
        self.assertIsNone(vacancy.is_remote)


if __name__ == "__main__":
    unittest.main()
