"""Фильтры ролей: попадания, промахи и взаимные исключения между ролями."""

from __future__ import annotations

import unittest

from bot.role_filters import (
    is_product_manager_vacancy,
    is_product_owner_vacancy,
    is_python_developer_vacancy,
    is_qa_automation_vacancy,
    is_qa_manual_vacancy,
    is_react_developer_vacancy,
)
from bot.filters import is_product_designer_vacancy


class ProductManagerTests(unittest.TestCase):
    def test_matches(self):
        for title in (
            "Product Manager",
            "Senior Product Manager",
            "Продакт-менеджер",
            "Продуктовый менеджер",
            "Менеджер продукта",
        ):
            self.assertTrue(is_product_manager_vacancy(title), title)

    def test_matches_real_hh_titles(self):
        for title in (
            "Менеджер по продукту",
            "Менеджер по продуктам",
            "Product Manager / Продукт-менеджер",
        ):
            self.assertTrue(is_product_manager_vacancy(title), title)

    def test_rejects(self):
        for title in (
            "Project Manager",
            "Проджект-менеджер",
            "Product Designer",
            "Продуктовый аналитик",
            "QA Engineer",
        ):
            self.assertFalse(is_product_manager_vacancy(title), title)

    def test_rejects_non_it_domains(self):
        """Реальный шум из выдачи HH: те же слова, другая профессия."""
        for title in (
            "Product Manager | Менеджер продукта (медицинские изделия, стоматология)",
            "Категорийный менеджер / Продакт-менеджер товарного направления",
            "Старший менеджер продукта (бренд For me)",
            "Тренинг-менеджер по продукту (премиальный бренд ASKO)",
        ):
            self.assertFalse(is_product_manager_vacancy(title), title)


class ProductOwnerTests(unittest.TestCase):
    def test_matches(self):
        for title in ("Product Owner", "Senior Product Owner", "Владелец продукта"):
            self.assertTrue(is_product_owner_vacancy(title), title)

    def test_rejects(self):
        for title in ("Product Manager", "Product Designer", "Project Manager"):
            self.assertFalse(is_product_owner_vacancy(title), title)


class QaManualTests(unittest.TestCase):
    def test_matches(self):
        for title in (
            "QA Engineer",
            "Тестировщик",
            "Инженер по тестированию",
            "QA Manual",
            "Специалист по ручному тестированию",
        ):
            self.assertTrue(is_qa_manual_vacancy(title), title)

    def test_rejects_automation(self):
        for title in (
            "QA Automation Engineer",
            "AQA Engineer",
            "SDET",
            "Автоматизатор тестирования",
            "Инженер по автоматизации тестирования",
            "Автотестировщик (Python)",
            "Тестировщик-автоматизатор",
            "AQA/Тестировщик -автоматизатор (web, mobile)",
            "QA Lead (Manual + Automation)",
        ):
            self.assertFalse(is_qa_manual_vacancy(title), title)

    def test_rejects_other_roles(self):
        for title in ("Python Developer", "Product Manager", "Product Designer"):
            self.assertFalse(is_qa_manual_vacancy(title), title)


class QaAutomationTests(unittest.TestCase):
    def test_matches(self):
        for title in (
            "QA Automation Engineer",
            "AQA Engineer",
            "SDET",
            "Автоматизатор тестирования",
            "Инженер по автоматизации тестирования",
            "Test Automation Engineer",
        ):
            self.assertTrue(is_qa_automation_vacancy(title), title)

    def test_matches_real_hh_titles(self):
        """Эти формы живая выдача HH показала как пропущенные."""
        for title in (
            "Автотестировщик (Python)",
            "Автотестировщик 1С (Vanessa)",
            "Автотестировщик (TypeScript, JavaScript и Playwright)",
            "Тестировщик-автоматизатор",
            "AQA/Тестировщик -автоматизатор (web, mobile)",
            "QA Lead (Manual + Automation)",
            "Senior QA Automation Engineer (Java, back)",
        ):
            self.assertTrue(is_qa_automation_vacancy(title), title)

    def test_rejects(self):
        for title in (
            "QA Engineer",
            "Тестировщик",
            "Python Developer",
            "Product Manager",
        ):
            self.assertFalse(is_qa_automation_vacancy(title), title)


class MutualExclusionTests(unittest.TestCase):
    """Одна вакансия не должна попадать сразу в две роли."""

    def test_qa_roles_are_disjoint(self):
        for title in (
            "QA Engineer",
            "QA Automation Engineer",
            "Тестировщик",
            "SDET",
            "AQA Engineer",
        ):
            both = is_qa_manual_vacancy(title) and is_qa_automation_vacancy(title)
            self.assertFalse(both, f"{title} попал сразу в обе QA-роли")

    def test_manager_roles_are_disjoint(self):
        for title in (
            "Product Manager",
            "Product Owner",
            "Продуктовый менеджер",
            "Менеджер продукта",
        ):
            hits = [
                is_product_manager_vacancy(title),
                is_product_owner_vacancy(title),
            ]
            self.assertLessEqual(sum(hits), 1, f"{title} попал в несколько ролей: {hits}")

    def test_existing_roles_still_reject_pm_and_qa(self):
        """Дизайн и разработка не должны воровать новые вакансии."""
        for title in (
            "Product Manager",
            "Product Owner",
            "QA Engineer",
            "QA Automation Engineer",
            "Тестировщик",
        ):
            self.assertFalse(is_product_designer_vacancy(title), title)
            self.assertFalse(is_react_developer_vacancy(title), title)
            self.assertFalse(is_python_developer_vacancy(title), title)

    def test_pm_and_qa_reject_design_and_dev(self):
        for title in ("Product Designer", "React Developer", "Python Developer"):
            self.assertFalse(is_product_manager_vacancy(title), title)
            self.assertFalse(is_product_owner_vacancy(title), title)
            self.assertFalse(is_qa_manual_vacancy(title), title)
            self.assertFalse(is_qa_automation_vacancy(title), title)


if __name__ == "__main__":
    unittest.main()
