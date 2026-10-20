"""Фильтр подписчика «только удалёнка»: чистый предикат без I/O."""

from __future__ import annotations

import unittest

from bot.models import Vacancy
from bot.subscriber_filters import apply_remote_filter


def _vacancy(uid: str, is_remote):
    return Vacancy(
        source="hh.ru",
        external_id=uid,
        title="Product Designer",
        company="Яндекс",
        url=f"https://hh.ru/vacancy/{uid}",
        is_remote=is_remote,
    )


class RemoteFilterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.remote = _vacancy("1", True)
        self.onsite = _vacancy("2", False)
        self.unknown = _vacancy("3", None)
        self.all = [self.remote, self.onsite, self.unknown]

    def test_filter_off_keeps_everything(self):
        outcome = apply_remote_filter(self.all, include_remote=False)
        self.assertEqual(outcome.kept, self.all)
        self.assertEqual(outcome.dropped_onsite, 0)
        self.assertEqual(outcome.dropped_unknown, 0)

    def test_filter_on_keeps_only_remote(self):
        outcome = apply_remote_filter(self.all, include_remote=True)
        self.assertEqual(outcome.kept, [self.remote])

    def test_filter_on_counts_reasons_separately(self):
        outcome = apply_remote_filter(self.all, include_remote=True)
        self.assertEqual(outcome.dropped_onsite, 1)
        self.assertEqual(outcome.dropped_unknown, 1)

    def test_unknown_is_not_treated_as_remote(self):
        outcome = apply_remote_filter([self.unknown], include_remote=True)
        self.assertEqual(outcome.kept, [])
        self.assertEqual(outcome.dropped_unknown, 1)

    def test_empty_input(self):
        outcome = apply_remote_filter([], include_remote=True)
        self.assertEqual(outcome.kept, [])
        self.assertEqual(outcome.dropped_onsite, 0)
        self.assertEqual(outcome.dropped_unknown, 0)

    def test_order_is_preserved(self):
        many = [_vacancy(str(i), True) for i in range(5)]
        outcome = apply_remote_filter(many, include_remote=True)
        self.assertEqual([v.external_id for v in outcome.kept], ["0", "1", "2", "3", "4"])


if __name__ == "__main__":
    unittest.main()
