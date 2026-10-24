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


from bot.role_filters import (  # noqa: E402
    is_data_governance_vacancy,
    is_head_of_ai_vacancy,
    is_head_of_data_vacancy,
    is_head_of_design_vacancy,
    is_head_of_engineering_vacancy,
    is_head_of_product_vacancy,
)


class GovernanceAndLeadersTest(unittest.TestCase):
    """Заголовки из живой выдачи HH за 30 дней."""

    def check(self, matcher, yes=(), no=()):
        for title in yes:
            self.assertTrue(matcher(title), f"должно попасть: {title}")
        for title in no:
            self.assertFalse(matcher(title), f"не должно попасть: {title}")

    def test_data_governance(self):
        self.check(
            is_data_governance_vacancy,
            yes=("Data Steward (Ozon Банк)", "Методолог Data Governance (Банк)", "Аналитик качества данных",
                 "Аналитик качества данных (Глоссарий/Дата-каталог)", "Senior MDM Specialist",
                 "Руководитель отдела управления данными", "Директор по управлению данными (г. Баку)"),
            no=("Специалист ИБ (DLP, антивирус, MDM)", "Менеджер по работе с клиентами (ERP, MDM, Datareon)",
                "Специалист по управлению НСИ и обеспечению качества данных (1С, Excel)",
                "Старший специалист 1 разряда отдела управления качеством данных",
                "Инженер технической поддержки по управлению данными"),
        )

    def test_head_of_data(self):
        self.check(
            is_head_of_data_vacancy,
            yes=("Chief Data Officer", "Chief Data Officer / Директор по данным", "Head of Data", "Head of Analytics",
                 "Head of Data Science (fintech)", "Руководитель аналитики данных (e-com, delivery, A/B)",
                 "Руководитель отдела аналитики данных", "Технический руководитель по данным (Платформа обслуживания)",
                 "Руководитель направления продуктовой аналитики", "Директор по искусственному интеллекту и данным",
                 "Руководитель отдела аналитики (Python)", "Руководитель отдела аналитики данных (метрики)"),
            no=("Директор по цифровой трансформации / Chief Digital Officer (CDO)",
                "Руководитель направления финансовой аналитики корпоративно-инвестиционного бизнеса",
                "Руководитель отдела аналитики продаж", "Директор департамента аналитики (взыскание задолженности)",
                "Директор по аналитике (Fashion)", "Руководитель группы аналитики данных (последняя миля)",
                "Помощник руководителя — аналитик данных", "Руководитель веб-аналитики (e-commerce)",
                "Руководитель направления аналитики Животноводство (молочное, мясное)",
                "Руководитель отдела аналитики и аудита", "Руководитель направления аналитики и доходности"),
        )

    def test_head_of_ai(self):
        self.check(
            is_head_of_ai_vacancy,
            yes=("Head of AI / Руководитель AI-направления", "Head of AI Engineering (ИТ Лидер Кластера)",
                 "Head of ML Infrastructure & Platform", "Руководитель ML/AI-платформы", "Руководитель ИИ-направления",
                 "Руководитель дирекции по искусственному интеллекту (AI)", "Руководитель направления по внедрению ИИ",
                 "Директор по искусственному интеллекту и данным"),
            no=("Руководитель отдела продаж (B2B, ИИ-решения)", "Head of Marketing (HealthTech AI-продукт)",
                "Руководитель AI Контент-завода", "Руководитель ИИ-проектов", "Руководитель проектов ИИ",
                "Ассистент руководителя (ИИ и автоматизация)", "Head of ML-SEO / SEO Lead (Senior+)",
                'Руководитель отдела информационной безопасности ("MWS AI")',
                "Руководитель направления ИИ и цифрового образования (LMS/СДО)",
                "Руководитель команды генеративного искусственного интеллекта"),
        )

    def test_head_of_design(self):
        self.check(
            is_head_of_design_vacancy,
            yes=("Head of Design", "Design Director", "Дизайн директор", "Руководитель отдела дизайна",
                 "Руководитель UX/UI-дизайна", "Руководитель направления продуктового дизайна",
                 "Руководитель дизайна APP / Art lead Gamedev", "Арт-директор / Head of Design"),
            no=("Руководитель направления организационного дизайна",
                "Ведущий дизайнер интерьера /Руководитель отдела дизайна интерьера",
                "Руководитель отдела дизайна (машинная вышивка)", "Руководитель проектов по дизайну интерьеров",
                "Руководитель отдела продаж (ландшафтный дизайн, благоустройство)", "Руководитель дизайн-проектов",
                "Заведующий кафедрой Дизайна в Университет МФЮА", "Арт-директор"),
        )

    def test_head_of_product(self):
        self.check(
            is_head_of_product_vacancy,
            yes=("Chief Product Officer (CPO)", "CPO / Head of Product (FinTech)", "Head of Product - Platform B2B/B2C",
                 "Директор по продукту", "Директор по продуктам (CPO)", "Директор продуктового департамента / CPO",
                 "Руководитель IT продуктов", "Head of Product / Руководитель продуктового направления"),
            no=("Директор по продажам (продукты питания)", "Head of Product Marketing",
                "Руководитель направления продуктового маркетинга (PMM)", "Head of Product (одежда)",
                "Продуктолог (Head of Product), категория «Одежда» (Wildberries и маркетплейсы)",
                "Директор по продукту (жилая недвижимость)", "Бизнес-ассистент для Руководителя производства (CPO)",
                'Руководитель продуктового направления "Системы электрообогрева"',
                "Art Director / Head of Visual Product Function (GameDev)",
                "Руководитель направления продуктового дизайна", "Руководитель направления продуктовой аналитики"),
        )

    def test_head_of_engineering(self):
        self.check(
            is_head_of_engineering_vacancy,
            yes=("CTO / CPTO / Chief Technology Officer / Технический директор", "Технический директор (CTO)",
                 "DS/ AI Lead (технический директор)", "Engineering Manager (Сollection/Uzum Nasiya)",
                 "Lead C# .Net /Engineering Manager (Antifraud | Fintech)", "Head of Engineering",
                 "Руководитель разработки", "Руководитель отдела разработки 1С",
                 "Руководитель направления фронтенд-разработки (Head of Frontend Development)"),
            no=(
                # «Технический директор» без IT-признака — стройка и заводы.
                "Технический директор (ЖКХ)", "Главный инженер/технический директор",
                "Производственный директор / Технический директор",
                # Девелопмент и Business Development по запросу «директор по разработке».
                "Директор по девелопменту", "Business Development Director / BDD / Директор по развитию бизнеса",
                "Директор по разработке электротехнической продукции в Ярославль",
                "Руководитель направления по разработке и внедрению СМК",
                "Руководитель технологических процессов сортировочного центра / Head of Sortation Engineering",
                # Тимлиды — уровень команды, их ловят профильные роли.
                "Team Lead .NET", "Руководитель группы разработки", "Руководитель команды разработки (Go)",
                # Разработка продукта в банке — продуктовая роль.
                "Директор по разработке розничных продуктов",
            ),
        )

    def test_leaders_skip_team_level(self):
        for matcher in (is_head_of_data_vacancy, is_head_of_ai_vacancy, is_head_of_design_vacancy,
                        is_head_of_product_vacancy, is_head_of_engineering_vacancy):
            for title in ("Team Lead Product Analytics / Руководитель группы продуктовой аналитики",
                          "Руководитель группы разработки ИИ-агентов (ERP)", "Руководитель команды аналитиков"):
                self.assertFalse(matcher(title), f"{matcher.__name__}: {title}")

    def test_existing_feeds_unchanged_by_leaders(self):
        """Лидерские роли добавляют вакансии, а не забирают их у профильных."""
        self.assertTrue(is_product_designer_vacancy("Lead Product Designer"))
        self.assertTrue(is_qa_manual_vacancy("Head of QA"))
        self.assertTrue(is_data_scientist_vacancy("Head of Data Science (fintech)"))


class LeadersQaFindingsTest(unittest.TestCase):
    """Находки независимой проверки на живой выдаче HH и каверзные заголовки к ним."""

    E = staticmethod(is_head_of_engineering_vacancy)
    D = staticmethod(is_head_of_data_vacancy)
    A = staticmethod(is_head_of_ai_vacancy)
    G = staticmethod(is_data_governance_vacancy)
    P = staticmethod(is_head_of_product_vacancy)
    DS = staticmethod(is_head_of_design_vacancy)

    def cases(self):
        E, D, A, G, P, DS = self.E, self.D, self.A, self.G, self.P, self.DS
        return [
            # Кириллическое «СТО» — тоже CTO; «AI-ассистенты» — продукт, а не помощник.
            (E, "СТО/Chief Technology Officer (Технический директор)", True),
            (E, "Технический директор CTO (AI/ИИ, Цифровые ассистенты)", True),
            (A, "Руководитель направления AI-ассистентов", True),
            (E, "Секретарь технического директора (IT)", False),
            # Руководители проектов и разработка не ПО.
            (E, "Руководитель проекта разработки образовательных программ", False),
            (E, "Руководитель проектов разработки мобильной ОС", False),
            (E, "Руководитель отдела фармацевтической разработки", False),
            (E, "Руководитель отдела разработки клеевых систем", False),
            (E, "Руководитель направления разработки технологии культивирования", False),
            (E, "Руководитель отдела разработки и запуска новых продуктов", False),
            (E, "Технический директор (разработка месторождений)", False),
            (E, "Директор по разработке (жилая недвижимость)", False),
            (E, "Начальник отдела разработки готовых лекарственных форм", False),
            (E, "Начальник лаборатории разработки усилителей мощности и РЭА", False),
            (E, "Начальник отдела разработки планов развития НПЗ", False),
            # «Development» — разработка, но не People / Corporate / Infrastructure.
            (E, "Head of People Development", False),
            (E, "Head of Corporate Development", False),
            (E, "Head of Infrastructure Development and Climate Resiliency Department", False),
            (E, "Head of Development", True),
            # Тимлид в любой форме — не руководитель направления; холдинг — не команда.
            (E, "Руководитель подгруппы разработки DWH", False),
            (A, "Руководитель ML-группы", False),
            (A, "Руководитель AI-команды", False),
            (DS, "Руководитель дизайн-команды", False),
            (E, "Руководитель разработки (тим-лид)", False),
            (E, "Руководитель разработки группы компаний", True),
            # «Начальник» и английские Director / VP.
            (E, "Начальник отдела разработки ПО", True),
            (E, "Director of Engineering", True),
            (E, "VP Engineering", True),
            (P, "Director of Product", True),
            (P, "VP of Product", True),
            (D, "Director of Data", True),
            (E, "Руководитель разработки программных продуктов", True),
            (E, "Руководитель разработки интернет-магазина", True),
            (E, "Руководитель отдела разработки и эксплуатации ПО", True),
            # Продукт: CPO бывает Chief People Officer; не цифровые продукты.
            (P, "Chief People Officer (CPO)", False),
            (P, "Директор по персоналу (CPO)", False),
            (P, "CPO (HR Tech)", True),
            (P, "Head of Financial Products", True),
            (P, "Руководитель IT-продуктов", True),
            (P, "Директор по продукту (медицинские изделия)", False),
            (P, "Директор продуктовой сети супермаркетов", False),
            (P, "Директор сопровождения продуктов и процессов (АСОИ ФинЦЕРТ)", False),
            # Данные: «центр» — не «цены»; CDO бывает Design / Development.
            (D, "Руководитель центра компетенций по данным", True),
            (D, "CDO (Chief Design Officer)", False),
            (D, "Chief Development Officer (CDO)", False),
            (D, "Руководитель проектов по анализу данных", False),
            (D, "Head of Analytics (Marketing)", False),
            # Governance: мастер-данные и НСИ — да; 1С с MDM — да; MDM у админов — нет.
            (G, "Специалист по управлению мастер данными", True),
            (G, "Методолог НСИ", True),
            (G, "Функциональный архитектор НСИ", True),
            (G, "Аналитик качества клиентских данных", True),
            (G, "Data Steward (оператор связи)", True),
            (G, "Системный аналитик 1С (MDM)", True),
            (G, "Оператор НСИ", False),
            (G, "Специалист по ведению нормативно-справочной информации (НСИ) и складскому учету", False),
            (G, "Ведущий Разработчик серверной части (Python) [Центр DataGov, Big Data, МТС Веб Сервисы]", False),
            (G, "Системный администратор (MDM, Intune)", False),
            # Дизайн.
            (DS, "Head of UX", True),
            (DS, "Директор по продуктовому дизайну", True),
            (DS, "Chief Design Officer", True),
            (DS, "Head of Sound Design", False),
            (DS, "Head of Instructional Design", False),
            (DS, "Руководитель отдела дизайна (обувь)", False),
            (DS, "Руководитель отдела дизайна и разработки (фабрика игрушек)", False),
            (DS, "Директор Союза дизайнеров Республики Татарстан", False),
            (DS, "Арт-директор дизайн-студии", False),
            # AI.
            (A, "Руководитель отдела машинного обучения", True),
            (A, "Head of GenAI", True),
            (A, "Head of MLOps", True),
            (A, "Руководитель MLM-направления", False),
            (A, "Руководитель направления AI-тренеров", False),
        ]

    def test_findings(self):
        for matcher, title, expected in self.cases():
            with self.subTest(role=matcher.__name__, title=title):
                self.assertEqual(matcher(title), expected)


class ProductManagerGoodsTest(unittest.TestCase):
    """«Менеджер по продукту» в фарме, FMCG, одежде, дистрибуции техники — не IT.
    Заголовки из ночной выдачи HH: 248 вакансий, около четверти — товарные линейки."""

    def test_goods_product_managers_rejected(self):
        for title in (
            "OTC продакт-менеджер",
            "RX продакт-менеджер",
            "Senior Product manager, Immunology",
            "Менеджер по продукту (Product Manager лекарственные препараты, БАДы)",
            "Product Manager / R&D Manager (Cosmetics, China)",
            "Продакт-менеджер (Парфюмерия/Ароматика)",
            "Младший Продукт Менеджер проекта Деликатесы из дичи",
            "Менеджер продукта/Product Manager (Fashion)",
            "Продакт-менеджер (Product Manager) в сегменте «Обувь»",
            "Продакт менеджер по работе с фабриками ЮВА/байер",
            "Продакт-менеджер по трехфазным ИБП",
            "Продукт-менеджер по SSD и серверной памяти (Product Manager)",
            "Продакт-менеджер-Менеджер по продукту (совместимые картриджи для принтеров)",
            "Продакт-менеджер (строительная химия)",
            "Старший продакт менеджер (сварочное оборудование)",
            "Продакт-менеджер в производстве физических товаров (офис)",
            "Менеджер по продукту / Product-manager в девелопменте",
            "Менеджер по запуску продукции | младший менеджер по продукту (маркетплейсы)",
        ):
            self.assertFalse(is_product_manager_vacancy(title), title)

    def test_digital_product_managers_kept(self):
        for title in (
            "Product Manager (Медданные)",
            "Коммерческий продуктовый менеджер по направлению ИИ-решений",  # «коммерческий» ⊃ «мерч»
            "Технический продуктовый менеджер по аппаратным платформам сетевого оборудования",
            "Product Manager (веб-сервис для ресторанной сети)",
            "Менеджер продукта ЭДО",
            "Product manager (релевантность поиска)",  # «релевантность» ⊃ «реле»
            "Product Manager внутренних инструментов",  # не «строительный инструмент»
            "Product Manager (импортозамещение)",
            "Старший менеджер продукта (Подписка Ozon Premium)",
            "Product manager в Т‑Бизнес",
        ):
            self.assertTrue(is_product_manager_vacancy(title), title)

    def test_digital_marker_overrides_industry_word(self):
        """Отрасль — не приговор, если продукт цифровой."""
        self.assertTrue(is_product_manager_vacancy(
            "Специалист по развитию сайта и приложения (Product manager, fashion / e-com)"))
        self.assertTrue(is_product_manager_vacancy("Product Manager (мобильное приложение аптеки)"))
        self.assertFalse(is_product_manager_vacancy("Продуктовый менеджер (Аптеки)"))


from bot.role_filters import is_php_developer_vacancy  # noqa: E402
from bot.role_categories import get_category  # noqa: E402
from bot.roles import ROLES  # noqa: E402


class PhpDeveloperTest(unittest.TestCase):
    """Заголовки — из живой выдачи HH за 3 дня (24.10.2026)."""

    def test_php_titles(self):
        for title in [
            "PHP-разработчик",
            "Middle+/Senior PHP Developer (Symfony)",
            "Back end PHP/Simfony разработчик (middle/senior)",
            "Программист PHP (Symphony)",
            "Ведущий PHP (Laravel) разработчик",
            "PHP Team Lead (Backend)",
            "Технический лидер команды (php)",
            "Стажер/PHP-разработчик",
            "Go/PHP разработчик",
        ]:
            self.assertTrue(is_php_developer_vacancy(title), title)

    def test_fullstack_on_php_is_kept(self):
        # В отличие от Python/Java/Go: четверть PHP-вакансий — fullstack.
        for title in [
            "Fullstack PHP-разработчик",
            "Разработчик полного цикла / Fullstack-разработчик PHP / Laravel + Vue (Middle+ / Senior)",
            "Senior Fullstack-разработчик (1С-Битрикс + Vue.js)",
        ]:
            self.assertTrue(is_php_developer_vacancy(title), title)

    def test_bitrix_developers_without_word_php(self):
        for title in [
            "Разработчик Битрикс24 (коробочная версия)",
            "Программист Битрикс 24 (офис)",
            "Веб-программист Битрикс",
            "Bitrix- разработчик",
            "Разработчик сайта на 1с Битрикс НЕ УДАЛЕННО",
            "Разработчик / Вебмастер / WordPress / Full stack",
        ]:
            self.assertTrue(is_php_developer_vacancy(title), title)

    def test_bitrix_admins_sales_and_analysts_are_not_php(self):
        for title in [
            "Администратор Битрикс24",
            "Специалист по внедрению Битрикс24 (интегратор Битрикс24)",
            "Интегратор CRM Битрикс24/AMO CRM",
            "Менеджер по продажам Битрикс24 (B2B, полный цикл)",
            "Менеджер продукта Bitrix24",
            "Системный аналитик 1С-Битрикс / Bitrix24 / e-commerce",
            "Руководитель проекта 1С и Битрикс24",
            "Разработчик 1С и CRM (Bitrix)",
            "Project Manager/Бизнес-аналитик (CRM: Bitrix24, amoCRM)",
        ]:
            self.assertFalse(is_php_developer_vacancy(title), title)

    def test_other_stacks_and_roles_are_not_php(self):
        for title in [
            "Python-разработчик",
            "Golang-разработчик (Middle+ / Senior)",
            "Frontend-разработчик (PHP шаблоны)",
            "QA Engineer (PHP)",
            "DevOps-инженер (PHP-проекты)",
            "Преподаватель PHP",
            "Data Engineer (PHP, ETL)",
        ]:
            self.assertFalse(is_php_developer_vacancy(title), title)

    def test_php_role_is_in_backend_menu(self):
        self.assertIn("backend_php", get_category("backend").role_ids)
        self.assertEqual(ROLES["backend_php"].button_label, "Backend | PHP")
        self.assertLessEqual(len("s2:role:backend:backend_php".encode()), 64)


from bot.role_filters import (  # noqa: E402
    is_android_developer_vacancy,
    is_flutter_developer_vacancy,
    is_fullstack_vacancy,
    is_ios_developer_vacancy,
    is_react_native_developer_vacancy,
)


class FullstackAndMobileTest(unittest.TestCase):
    """Заголовки — из живой выдачи HH, Хабра и GetMatch за 3 дня (24.10.2026)."""

    def check(self, matcher, yes, no):
        for title in yes:
            self.assertTrue(matcher(title), title)
        for title in no:
            self.assertFalse(matcher(title), title)

    def test_fullstack(self):
        self.check(is_fullstack_vacancy,
                   ["Fullstack-разработчик (Node.js/React)", "Senior Full-Stack Developer (Angular / .NET Core)",
                    "Full-stack разработчик (Go / Next.js)", "Fullstack Team Lead (корпоративные сайты)",
                    "Разработчик полного цикла / Fullstack-разработчик PHP / Laravel + Vue (Middle+ / Senior)"],
                   ["Fullstack-аналитик", "Системный аналитик / Fullstack-аналитик", "Fullstack QA Engineer (Java)",
                    "AQA/Fullstack QA (Ai sales)", "Дизайнер Fullstack", "Младший QA-инженер Fullstack",
                    "Frontend-разработчик (React)"])

    def test_flutter(self):
        self.check(is_flutter_developer_vacancy,
                   ["Flutter-разработчик", "Flutter-разработчик (в офис)", "Mobile Developer (Flutter/Dart)"],
                   ["Python-developer", "QA Engineer (Flutter)", "Golang-разработчик"])

    def test_ios(self):
        self.check(is_ios_developer_vacancy,
                   ["IOS Developer (Middle+)", "Senior+ iOS Developer", "IOS разработчик в WB чат",
                    "Swift-разработчик", "Разработчик iOS / Проектная работа / АУТСТАФФ"],
                   ["Менеджер по работе с клиентами (продажа зарубежных банковских карт / сопровождение SWIFT)",
                    "Тестировщик iOS-приложений", "Сервисный инженер (ремонт iPhone и iOS-устройств)",
                    "Product Owner (iOS)"])

    def test_android(self):
        self.check(is_android_developer_vacancy,
                   ["Android-разработчик (Kotlin, Jetpack Compose)", "Senior Android Developer",
                    "Разработчик приложений для ОС Андроид", "Kotlin-разработчик (мобильная разработка)"],
                   ["Backend-разработчик (Java/Kotlin)", "Java / Kotlin разработчик (Software Engineer)",
                    "Сервисный инженер (Обучение с нуля / Ремонт iPhone и Android)",
                    "Сборщик заказов / Кладовщик на склад запчастей для Apple и Android",
                    "Тестировщик мобильных приложений / Mobile App (Android)"])

    def test_react_native_and_web_react_are_split(self):
        from bot.role_filters import is_react_developer_vacancy
        self.check(is_react_native_developer_vacancy,
                   ["React Native разработчик", "Мобильный разработчик (React Native /JavaScript /TypeScript)"],
                   ["Fullstack-разработчик (Node.js/React) / AI-native", "Frontend-разработчик (React)"])
        self.assertFalse(is_react_developer_vacancy("React Native разработчик"))
        self.assertTrue(is_react_developer_vacancy("Фронтенд-разработчик (reactjs, redux toolkit)"))

    def test_menu(self):
        self.assertEqual(get_category("fullstack").role_ids, ("fullstack",))
        self.assertEqual(get_category("mobile").role_ids,
                         ("mobile_flutter", "mobile_ios", "mobile_android", "mobile_react_native"))
        for role_id in get_category("mobile").role_ids:
            self.assertLessEqual(len(f"s2:role:mobile:{role_id}".encode()), 64)


# --- C# / .NET (24.10.2026). Заголовки — из живых лент Хабра, GetMatch и GeekJob. ---
from bot.role_filters import is_csharp_developer_vacancy  # noqa: E402


class CSharpDeveloperTest(unittest.TestCase):
    def test_csharp_titles(self):
        for title in (
            "C#/.NET-разработчик",
            "Middle+ C#/.NET-разработчик",
            ".NET разработчик (Новосибирск, офис)",
            "Разработчик .Net / Проектная работа / АУТСТАФФ",
            "Senior .NET Engineer",
            "Senior Product Engineer (.NET)",
            "Team Lead C# (.net)",
            "Ведущий разработчик C#",
            "Разработчик C#",
            "Старший C#-разработчик, ERP и учётные системы",
            "Ведущий разработчик серверной части (C#) [Секретарь, МТС Веб Сервисы]",
            "Технический руководитель .NET",
            "Разработчик .NET (Стажер)",
            "ASP.NET Core developer",
            "Dotnet developer",
        ):
            self.assertTrue(is_csharp_developer_vacancy(title), title)

    def test_not_csharp_backend(self):
        for title in (
            "Fullstack QA Engineer (Manual + Automation C#)",  # QA
            "QA Fullstack Engineer (C#)",
            "Инженера по тестированию (фулстек) на Java или C#",
            "Senior Fullstack Engineer (C# and Angular)",  # уходит в Fullstack
            "Unity-разработчик (WebGL)",  # геймдев
            "Unity C# developer",
            "Game developer C#",
            "Frontend-разработчик (.NET Blazor)",
            "Community Manager",  # «maui» внутри слова не должно ловить
            "Admin of example.net",
            "Разработчик C++",
            "Java-разработчик",
            "1С-разработчик",
        ):
            self.assertFalse(is_csharp_developer_vacancy(title), title)

    def test_role_is_in_backend_menu(self):
        self.assertIn("backend_csharp", get_category("backend").role_ids)
        self.assertEqual(ROLES["backend_csharp"].button_label, "Backend | C# / .NET")
        self.assertLessEqual(len("s2:role:backend:backend_csharp".encode()), 64)

    def test_other_backend_roles_do_not_take_csharp(self):
        for title in ("C#/.NET-разработчик", "Senior .NET Engineer", "Разработчик C#"):
            for role_id in ("backend_python", "backend_java", "backend_go", "backend_php"):
                self.assertFalse(ROLES[role_id].matcher(title), (role_id, title))
