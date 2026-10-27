"""Скрипт цифр рынка за неделю (scripts/market_week.py)."""

from __future__ import annotations

import importlib.util
import unittest
from datetime import datetime, timezone
from pathlib import Path

from bot.models import Vacancy

_spec = importlib.util.spec_from_file_location(
    "market_week", Path(__file__).resolve().parent.parent / "scripts" / "market_week.py"
)
mw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mw)


def _v(n, title, company="Ozon", salary=None, work_format=None, source="hh.ru"):
    return Vacancy(source=source, external_id=str(n), title=title, company=company, url=f"https://x/{n}",
                   salary=salary, work_format=work_format, published_at=datetime.now(timezone.utc))


class SalaryTest(unittest.TestCase):
    def test_formats_of_our_sources(self):
        self.assertEqual(mw.salary_rub("от 250 000 ₽"), 250_000)
        self.assertEqual(mw.salary_rub("до 300 000 ₽"), 300_000)
        self.assertEqual(mw.salary_rub("200 000 — 300 000 ₽"), 250_000)
        self.assertEqual(mw.salary_rub("от 200 000 до 300 000 ₽"), 250_000)
        self.assertEqual(mw.salary_rub("150 000 — 250 000 руб. на руки"), 200_000)

    def test_not_rubles_or_weird_is_ignored(self):
        for text in (None, "", "от 3 000 $", "2 000 — 3 000 €", "от 1 500 ₽ в час", "от 5 ₽", "по договорённости"):
            self.assertIsNone(mw.salary_rub(text), text)


class PostTest(unittest.TestCase):
    def test_post_has_numbers_and_link(self):
        by_role = {
            "product_designer": [
                _v(i, f"Продуктовый дизайнер {i}", company=c, salary=f"от {200 + i * 10} 000 ₽",
                   work_format="Удалённо" if i % 2 else None)
                for i, c in enumerate(["Ozon", "Ozon", "VK", "Авито", "Т-Банк", "Ozon"])
            ],
            "devops": [_v(100, "DevOps Engineer", company="VK")],
        }
        post = mw.build_post(by_role, [], datetime(2026, 10, 27))
        self.assertIn("за неделю 20.10–27.10: 7 вакансий", post)
        self.assertIn("• Дизайн — 6 (удалённо 50%)", post)
        self.assertIn("UX/UI | Продуктовый дизайнер — 225 тыс ₽", post)
        self.assertIn("Больше всех нанимают: Ozon (3), VK (2)", post)
        self.assertIn(mw.BOT_LINK, post)
        self.assertNotIn("не публиковать", post)

    def test_incomplete_roles_marked_as_private_note(self):
        post = mw.build_post({"devops": [_v(1, "DevOps")]}, ["devops"], datetime(2026, 10, 27))
        self.assertIn("[для себя, не публиковать]", post)
