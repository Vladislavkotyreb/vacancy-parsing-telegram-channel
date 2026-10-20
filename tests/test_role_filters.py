"""Фильтры ролей: попадания, промахи и взаимные исключения между ролями."""

from __future__ import annotations

import unittest

from bot.role_filters import (
    is_art_director_vacancy,
    is_graphic_designer_vacancy,
    is_product_manager_vacancy,
    is_product_owner_vacancy,
    is_python_developer_vacancy,
    is_qa_automation_vacancy,
    is_qa_manual_vacancy,
    is_react_developer_vacancy,
)
from bot.filters import is_product_designer_vacancy


class ArtDirectorTests(unittest.TestCase):
    def test_matches_real_hh_titles(self):
        """Заголовки из живой выдачи HH."""
        for title in (
            "Art Director",
            "Art Director GameDev",
            "Senior Art Director",
            "Арт директор (CG/мультимедиа)",
            "Арт-директор (digital, motion, branding)",
            "Арт-директор/Дизайнер по упаковке",
            "Арт-Директор/Креативный директор",
            "Арт-директор в Рекламное Агентство",
            "Графический дизайнер / Арт директор в fashion/мерч (digital + полиграфия)",
        ):
            self.assertTrue(is_art_director_vacancy(title), title)

    def test_matches_odd_dashes(self):
        """На HH встречаются пробелы вокруг дефиса и длинное тире."""
        for title in ("Арт - директор", "Бренд директор (арт – директор в девелоперской компании)"):
            self.assertTrue(is_art_director_vacancy(title), title)

    def test_rejects_hospitality_and_events(self):
        """В РФ «арт-директор» — ещё и ведущий программы в баре или клубе."""
        for title in (
            "Арт-директор в гастроособняк Орбита",
            "Концертный менеджер / Арт-директор",
            "Партнер / Арт-директор / Управляющий бьюти-салона с ИИ-управлением",
            "Арт-директор ресторана",
            "Арт-директор ночного клуба",
            "Арт-директор караоке-бара",
            "Арт-директор анимационной команды в отель",
        ):
            self.assertFalse(is_art_director_vacancy(title), title)

    def test_rejects_interior_like_other_design_roles(self):
        self.assertFalse(
            is_art_director_vacancy("Ведущий дизайнер интерьера / тимлид / арт-директор")
        )

    def test_rejects_neighbouring_roles(self):
        """Креативный и дизайн-директор — соседние, но другие роли."""
        for title in (
            "Креативный директор",
            "Креативный директор / Head of Marketing",
            "Дизайн директор",
            "Руководитель дизайн-отдела",
            "Графический дизайнер",
            "Product Designer",
        ):
            self.assertFalse(is_art_director_vacancy(title), title)

    def test_existing_design_roles_unchanged(self):
        """Новая роль не должна менять ленты нынешних подписчиков."""
        for title in ("Art Director", "Арт-директор", "Senior Art Director"):
            self.assertFalse(is_product_designer_vacancy(title), title)
            self.assertFalse(is_graphic_designer_vacancy(title), title)


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
