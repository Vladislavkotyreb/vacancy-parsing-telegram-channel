"""Счётчики /stats: только нынешние подписчики, без админа, без двойного счёта."""

from __future__ import annotations

import re
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from bot.database import VacancyDatabase
from bot.stats import format_admin_stats

ADMIN = 1


class AdminCountsTest(unittest.TestCase):
    """Сценарий из аудита: трое подписаны (с админом), у одного две роли, один
    отписался, один заблокировал бота; всем что-то уже доставлялось."""

    def setUp(self) -> None:
        path = Path(tempfile.mkdtemp()) / "test.db"
        self.db = VacancyDatabase(path)
        self.db.set_subscriber_roles(ADMIN, ["product_designer"])
        self.db.set_subscriber_roles(10, ["product_designer"])
        self.db.set_subscriber_roles(11, ["product_designer", "qa_manual"])
        self.db.set_subscriber_roles(12, ["product_designer"])
        self.db.deactivate_subscriber(12)
        self.db.set_subscriber_roles(13, ["backend_go"])
        self.db.deactivate_subscriber(13, reason="blocked")
        conn = sqlite3.connect(path)
        now = datetime.now(timezone.utc).isoformat()
        for user_id, count in ((10, 5), (11, 4), (12, 3), (13, 2)):
            for i in range(count):
                conn.execute(
                    "INSERT INTO subscriber_sent (user_id, vacancy_uid, dedup_key, sent_at) VALUES (?, ?, '', ?)",
                    (user_id, f"v{user_id}-{i}", now),
                )
        conn.commit()
        conn.close()
        self.text = re.sub(r"<[^>]+>", "", format_admin_stats(self.db, "Europe/Moscow", exclude_user_id=ADMIN))

    def test_active_excludes_admin(self):
        self.assertIn("• Активных: 2", self.text)

    def test_roles_count_only_current_subscribers(self):
        self.assertIn("UX/UI | Продуктовый дизайнер: 2 · 2", self.text)
        self.assertIn("QA | Ручное тестирование: 1 · 1", self.text)
        # Роль есть только у заблокировавшего бота — её не показываем.
        self.assertNotIn("Backend | Go", self.text)

    def test_legacy_roles_are_marked(self):
        """Старые frontend/backend не путаются с разделами меню."""
        path = Path(tempfile.mkdtemp()) / "legacy.db"
        db = VacancyDatabase(path)
        db.set_subscriber_roles(20, ["frontend", "frontend_react"])
        db.set_subscriber_roles(21, ["backend"])
        text = re.sub(r"<[^>]+>", "", format_admin_stats(db, "Europe/Moscow"))
        self.assertIn("Frontend (старая роль, весь фронтенд): 1 · 0", text)
        self.assertIn("Backend (старая роль, весь бэкенд): 1 · 0", text)
        self.assertIn("Frontend | React: 1 · 0", text)

    def test_reach_never_exceeds_subscribers(self):
        self.assertIn("Получили хотя бы 1 вакансию: 2 из 2 (100%)", self.text)
        for pct in re.findall(r"\((\d+)%\)", self.text):
            self.assertLessEqual(int(pct), 100)

    def test_total_sent_is_full_history(self):
        self.assertIn("Вакансий отправлено: 14", self.text)

    def test_no_double_counting_by_role(self):
        """Раньше вакансии человека с двумя ролями засчитывались в обе."""
        self.assertNotIn("По ролям (всего)", self.text)

    def test_admin_exclusion_is_stated_once_for_whole_screen(self):
        self.assertEqual(self.text.count("Админ в подсчётах не учитывается"), 1)


if __name__ == "__main__":
    unittest.main()
