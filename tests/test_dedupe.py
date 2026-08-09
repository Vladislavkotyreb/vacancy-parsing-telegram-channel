import unittest
from datetime import datetime, timezone

from bot.dates import dedupe_by_title_company, dedupe_key
from bot.models import Vacancy


class DedupePriorityTests(unittest.TestCase):
    def test_hh_wins_over_geekjob_even_if_older(self):
        hh = Vacancy(
            source="hh.ru",
            external_id="1",
            title="Product Designer",
            company="Яндекс",
            url="https://hh.ru/vacancy/1",
            published_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )
        geekjob = Vacancy(
            source="geekjob.ru",
            external_id="2",
            title="Product Designer",
            company="Яндекс",
            url="https://geekjob.ru/vacancy/2",
            published_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
        )
        result = dedupe_by_title_company([geekjob, hh])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].source, "hh.ru")

    def test_hh_listed_first_in_output(self):
        vacancies = dedupe_by_title_company(
            [
                Vacancy(
                    source="geekjob.ru",
                    external_id="a",
                    title="UX Designer",
                    company="Ozon",
                    url="https://geekjob.ru/vacancy/a",
                    published_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
                ),
                Vacancy(
                    source="hh.ru",
                    external_id="b",
                    title="Senior Designer",
                    company="VK",
                    url="https://hh.ru/b",
                    published_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
                ),
            ]
        )
        self.assertEqual(vacancies[0].source, "hh.ru")

    def test_dedupe_key_normalizes_title(self):
        self.assertEqual(
            dedupe_key("Product Designer", "Яндекс"),
            dedupe_key("product designer", "яндекс"),
        )


if __name__ == "__main__":
    unittest.main()
