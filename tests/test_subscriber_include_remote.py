"""Хранение персонального фильтра «только удалёнка»."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from bot.database import VacancyDatabase
from bot.models import Vacancy


class IncludeRemoteStorageTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db = VacancyDatabase(Path(self._tmp.name) / "test.db")
        self.user_id = 555001

    def test_default_is_off(self):
        self.db.set_subscriber_roles(self.user_id, ["product_designer"])
        self.assertFalse(self.db.get_include_remote(self.user_id))

    def test_unknown_user_is_off(self):
        self.assertFalse(self.db.get_include_remote(999999))

    def test_set_and_read_back(self):
        self.db.set_subscriber_roles(self.user_id, ["product_designer"])
        self.db.set_include_remote(self.user_id, True)
        self.assertTrue(self.db.get_include_remote(self.user_id))
        self.db.set_include_remote(self.user_id, False)
        self.assertFalse(self.db.get_include_remote(self.user_id))

    def test_set_before_subscribing_persists(self):
        """Фильтр можно включить до выбора ролей — настройка не должна теряться."""
        self.db.set_include_remote(self.user_id, True)
        self.assertTrue(self.db.get_include_remote(self.user_id))

        self.db.set_subscriber_roles(self.user_id, ["backend_go"])
        self.assertTrue(self.db.get_include_remote(self.user_id))

    def test_setting_filter_does_not_activate_subscription(self):
        self.db.set_include_remote(self.user_id, True)
        self.assertEqual(self.db.list_active_subscribers(), [])

    def test_survives_role_change(self):
        self.db.set_subscriber_roles(self.user_id, ["product_designer"])
        self.db.set_include_remote(self.user_id, True)
        self.db.set_subscriber_roles(self.user_id, ["backend_python"])
        self.assertTrue(self.db.get_include_remote(self.user_id))

    def test_changing_filter_keeps_sent_history(self):
        """В отличие от смены ролей — иначе сужение фильтра вызовет повтор рассылки."""
        self.db.set_subscriber_roles(self.user_id, ["product_designer"])
        vacancy = Vacancy(
            source="hh.ru",
            external_id="1",
            title="Product Designer",
            company="Яндекс",
            url="https://hh.ru/vacancy/1",
            published_at=datetime.now(timezone.utc),
        )
        self.db.mark_sent_to_subscriber(self.user_id, vacancy)

        self.db.set_include_remote(self.user_id, True)

        self.assertTrue(self.db.is_sent_to_subscriber(self.user_id, vacancy.uid))

    def test_listed_for_active_subscribers(self):
        self.db.set_subscriber_roles(self.user_id, ["product_designer"])
        self.db.set_include_remote(self.user_id, True)
        rows = self.db.list_active_subscribers()
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["include_remote"])


class IncludeRemoteMigrationTest(unittest.TestCase):
    def test_column_added_to_existing_database(self):
        """Боевая база создана до фичи — колонки там нет."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db_path = Path(tmp.name) / "legacy.db"

        conn = sqlite3.connect(db_path)
        conn.executescript(
            """
            CREATE TABLE subscribers (
                user_id INTEGER PRIMARY KEY,
                role TEXT NOT NULL,
                subscribed_at TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            );
            INSERT INTO subscribers (user_id, role, subscribed_at, active)
            VALUES (777, 'product_designer', '2026-01-01T00:00:00+00:00', 1);
            """
        )
        conn.commit()
        conn.close()

        db = VacancyDatabase(db_path)

        self.assertFalse(db.get_include_remote(777))
        rows = db.list_active_subscribers()
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["include_remote"])

        db.set_include_remote(777, True)
        self.assertTrue(db.get_include_remote(777))


if __name__ == "__main__":
    unittest.main()
