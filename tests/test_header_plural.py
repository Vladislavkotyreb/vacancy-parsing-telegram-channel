"""Шапка подборки склоняется по числу: «1 новая вакансия», «3 новых вакансии», «5 новых вакансий»."""

import unittest

from bot.subscriber_formatters import format_subscriber_header


class HeaderPluralTest(unittest.TestCase):
    def test_forms(self):
        cases = {
            1: "1 новая вакансия", 2: "2 новых вакансии", 4: "4 новых вакансии", 5: "5 новых вакансий",
            11: "11 новых вакансий", 14: "14 новых вакансий", 21: "21 новая вакансия", 22: "22 новых вакансии",
            30: "30 новых вакансий", 101: "101 новая вакансия",
        }
        for n, expected in cases.items():
            header = format_subscriber_header("продуктового дизайнера", n, n)
            self.assertIn(f"<b>{expected}</b>", header, n)


if __name__ == "__main__":
    unittest.main()
