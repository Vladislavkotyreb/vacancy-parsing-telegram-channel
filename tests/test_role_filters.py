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


from bot.role_filters import (  # noqa: E402
    is_data_analyst_vacancy,
    is_data_engineer_vacancy,
    is_data_scientist_vacancy,
    is_go_developer_vacancy,
    is_java_developer_vacancy,
    is_ml_engineer_vacancy,
    is_product_analyst_vacancy,
)


class DataRolesTest(unittest.TestCase):
    """Заголовки из живой выдачи HH."""

    def check(self, matcher, yes=(), no=()):
        for title in yes:
            self.assertTrue(matcher(title), f"должно попасть: {title}")
        for title in no:
            self.assertFalse(matcher(title), f"не должно попасть: {title}")

    def test_data_scientist(self):
        self.check(
            is_data_scientist_vacancy,
            yes=("Senior Data Scientist", "Data Scientist (Рекомендательные системы)",
                 "Ведущий Специалист по исследованию данных (Data Science)", "Дата-сайентист"),
            no=("Аналитик данных", "ML Engineer"),
        )

    def test_ml_engineer(self):
        self.check(
            is_ml_engineer_vacancy,
            yes=("ML Engineer / Инженер машинного обучения", "ML-инженер (NLP / LLM)", "MLOps-инженер",
                 "LLM-инженер / Специалист по большим языковым моделям", "AI Engineer", "AI-инженер",
                 "AI Agent Engineer (NLP/LLM)", "Computer Vision engineer",
                 "Ведущий инженер по машинному обучению и компьютерному зрению",
                 "Руководитель команды ML/Lead ML Engineer", "AI Tech Lead / Team Lead (LLM/RAG, Python)",
                 "Промпт-инженер / AI Prompt Engineer", "Middle Agentic Engineer (Перспективный AI)"),
            no=(
                # ML и LLM в скобках у разработчика — предметная область, не должность.
                "Golang-разработчик (домен AI&ML)", "Python-разработчик (ML)",
                "Senior .NET Developer (LLM / RAG)", "Ведущий Java Backend-разработчик AI / LLM Platform",
                "Python-разработчик AI-сервисов (LLM / RAG)",
                # Чужие профессии с ML в названии.
                "Data Scientist (Computer Vision)", "Инженер-тестировщик в ML (middle/middle+)",
                "Technical Product Owner (MLOps) / Руководитель направления",
                "Инженер компьютерного зрения (разметка данных, CVAT)",
                "Сценарист на YouTube-канал (нейросети, llm, ai-агенты)",
            ),
        )

    def test_data_engineer(self):
        self.check(
            is_data_engineer_vacancy,
            yes=("Data Engineer", "Big Data Engineer", "Data Quality Engineer", "Senior Data-инженер",
                 "Ведущий инженер данных", "Разработчик DWH (Корпоративное хранилище данных)",
                 "ETL-разработчик / Data Integration Engineer", "Аналитик-разработчик DWH Oracle (Junior+)",
                 "Team Lead Data Engineering"),
            no=("Аналитик DWH (SQL, ETL)", "Системный аналитик DWH", "Инженер по сетям передачи данных",
                "Инженер дата-центра", "Data Center Engineer", "Database engineer / Разработчик баз данных"),
        )

    def test_data_analyst(self):
        self.check(
            is_data_analyst_vacancy,
            yes=("Аналитик данных", "Data Analyst", "Data-аналитик", "Data аналитик", "BI-аналитик",
                 "BI- разработчик (Senior)", "Разработчик Power BI", "Аналитик DWH", "Аналитик баз данных",
                 "Аналитик баз данных/ SQL аналитик", "Ведущий аналитик больших данных",
                 "Специалист по анализу данных"),
            no=("Backend-разработчик (Python) — BI & AI направление", "JS-разработчик на BI-платформу",
                "Системный аналитик DWH", "Продуктовый аналитик", "Data Scientist",
                "Инженер по тестированию (QA Data Analyst)"),
        )

    def test_product_analyst(self):
        self.check(
            is_product_analyst_vacancy,
            yes=("Продуктовый аналитик", "Product Analyst", "Senior Product Analyst (B2C, mobile)",
                 "Аналитик продукта", "Руководитель продуктовой аналитики (Клиентские продукты)",
                 "Бизнес-аналитик /Product Analyst (Fintech, Digital Lending)"),
            no=("Бизнес-аналитик Продуктовой команды по развитию платежного сервиса СБП",
                "Аналитик маркетплейсов / Продуктовый аналитик (поиск ниш)",
                "Ведущий специалист отдела продуктовой и рыночной аналитики себестоимости",
                "Тренд-аналитик / Продуктолог / Продуктовый аналитик (женская одежда)",
                "Product Manager"),
        )

    def test_data_roles_do_not_overlap_on_plain_titles(self):
        matchers = (is_data_scientist_vacancy, is_ml_engineer_vacancy, is_data_engineer_vacancy,
                    is_data_analyst_vacancy, is_product_analyst_vacancy)
        for title in ("Data Scientist / ML инженер", "Senior Data Scientist / MLE", "Дата-аналитик (Data Quality / ETL)",
                      "Старший продуктовый аналитик данных", "Аналитик DWH", "Data Engineer"):
            hits = [m.__name__ for m in matchers if m(title)]
            self.assertEqual(len(hits), 1, f"{title}: {hits}")


class BackendGivesUpOnlyDataRolesTest(unittest.TestCase):
    def test_data_and_ml_engineers_leave_backend(self):
        for title in ("Data Engineer (Python)", "ML Engineer (Python)", "AI Engineer / AI R&D Developer (Python)"):
            self.assertFalse(is_python_developer_vacancy(title), title)
        self.assertFalse(is_java_developer_vacancy("Data Engineer (Java/Scala)"))
        self.assertFalse(is_go_developer_vacancy("Golang Data Engineer"))

    def test_developers_in_ai_domain_stay(self):
        self.assertTrue(is_go_developer_vacancy("Golang-разработчик (домен AI&ML)"))
        self.assertTrue(is_java_developer_vacancy("Ведущий Java Backend-разработчик AI / LLM Platform"))
        self.assertTrue(is_python_developer_vacancy("Python-разработчик AI-сервисов (LLM / RAG)"))
        self.assertTrue(is_python_developer_vacancy("Senior Python Developer"))

    def test_existing_roles_do_not_take_data_titles(self):
        for title in ("Product Analyst", "Продуктовый аналитик", "Data Scientist"):
            self.assertFalse(is_product_designer_vacancy(title), title)
            self.assertFalse(is_product_manager_vacancy(title), title)
