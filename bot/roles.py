from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from bot.filters import is_product_designer_vacancy
from bot.role_filters import (
    is_angular_developer_vacancy,
    is_art_director_vacancy,
    is_backend_vacancy,
    is_communication_designer_vacancy,
    is_data_analyst_vacancy,
    is_data_engineer_vacancy,
    is_data_governance_vacancy,
    is_data_scientist_vacancy,
    is_frontend_vacancy,
    is_go_developer_vacancy,
    is_graphic_designer_vacancy,
    is_head_of_ai_vacancy,
    is_head_of_data_vacancy,
    is_head_of_design_vacancy,
    is_head_of_engineering_vacancy,
    is_head_of_product_vacancy,
    is_java_developer_vacancy,
    is_php_developer_vacancy,
    is_csharp_developer_vacancy,
    is_design_lead_vacancy,
    is_devops_vacancy,
    is_it_project_manager_vacancy,
    is_fullstack_vacancy,
    is_flutter_developer_vacancy,
    is_ios_developer_vacancy,
    is_android_developer_vacancy,
    is_react_native_developer_vacancy,
    is_ml_engineer_vacancy,
    is_product_analyst_vacancy,
    is_product_manager_vacancy,
    is_product_owner_vacancy,
    is_python_developer_vacancy,
    is_qa_automation_vacancy,
    is_qa_manual_vacancy,
    is_react_developer_vacancy,
    is_vue_developer_vacancy,
)


@dataclass(frozen=True)
class Role:
    id: str
    label: str
    button_label: str
    hh_queries: tuple[str, ...]
    matcher: Callable[[str], bool]
    # Профобласти HH (https://api.hh.ru/professional_roles). Пусто — не сужаем.
    # Нужны там, где заголовок не выдаёт отрасль: «тестировщик» и «руководитель
    # проектов» одинаково встречаются в IT, на стройке и на производстве.
    hh_professional_roles: tuple[int, ...] = ()


ROLES: dict[str, Role] = {
    "product_designer": Role(
        id="product_designer",
        label="продуктового дизайнера",
        button_label="UX/UI | Продуктовый дизайнер",
        hh_queries=(
            "продуктовый дизайнер",
            "product designer",
            "product design",
            "продуктовый ux",
            "product ux designer",
            "ux ui designer",
            "UX UI дизайнер",
        ),
        matcher=is_product_designer_vacancy,
    ),
    "design_lead": Role(
        id="design_lead",
        label="дизайн-лида",
        button_label="Design Lead",
        hh_queries=(
            "design lead",
            "lead designer",
            "lead product designer",
            "дизайн лид",
            "лид дизайнер",
            "тимлид дизайн",
            "руководитель группы дизайна",
        ),
        matcher=is_design_lead_vacancy,
    ),
    "communication_designer": Role(
        id="communication_designer",
        label="коммуникационного дизайнера",
        button_label="Коммуникационный дизайнер",
        hh_queries=(
            "коммуникационный дизайнер",
            "communication designer",
            "communication design",
            "visual communication",
        ),
        matcher=is_communication_designer_vacancy,
    ),
    "graphic_designer": Role(
        id="graphic_designer",
        label="графического дизайнера",
        button_label="Графический дизайнер",
        hh_queries=(
            "графический дизайнер",
            "graphic designer",
            "graphic design",
            "visual designer",
        ),
        matcher=is_graphic_designer_vacancy,
    ),
    "art_director": Role(
        id="art_director",
        label="арт-директора",
        button_label="Арт-директор",
        hh_queries=("арт-директор", "арт директор", "art director"),
        matcher=is_art_director_vacancy,
        # 12 — «Арт-директор, креативный директор», 34 — «Дизайнер, художник».
        # Одной 12 мало: «Арт-директор/Дизайнер по упаковке» работодатели
        # относят к 34. Зато обе вместе отсекают концертных менеджеров и пиар
        # ресторанов, которых по заголовку не отличить.
        hh_professional_roles=(12, 34),
    ),
    "frontend_react": Role(
        id="frontend_react",
        label="React-разработчика",
        button_label="Frontend | React",
        hh_queries=("react developer", "react разработчик", "frontend react", "react frontend", "react"),
        matcher=is_react_developer_vacancy,
    ),
    "frontend_vue": Role(
        id="frontend_vue",
        label="Vue-разработчика",
        button_label="Frontend | Vue",
        hh_queries=("vue developer", "vue разработчик", "vue.js developer", "frontend vue", "vue.js"),
        matcher=is_vue_developer_vacancy,
    ),
    "frontend_angular": Role(
        id="frontend_angular",
        label="Angular-разработчика",
        button_label="Frontend | Angular",
        hh_queries=("angular developer", "angular разработчик", "frontend angular", "angular"),
        matcher=is_angular_developer_vacancy,
    ),
    "backend_python": Role(
        id="backend_python",
        label="Python-разработчика",
        button_label="Backend | Python",
        hh_queries=("python developer", "python разработчик", "python backend", "django developer", "python"),
        matcher=is_python_developer_vacancy,
    ),
    "backend_java": Role(
        id="backend_java",
        label="Java-разработчика",
        button_label="Backend | Java",
        hh_queries=("java developer", "java разработчик", "java backend", "spring developer", "java"),
        matcher=is_java_developer_vacancy,
    ),
    "backend_go": Role(
        id="backend_go",
        label="Go-разработчика",
        button_label="Backend | Go",
        hh_queries=("go developer", "golang developer", "go разработчик", "golang разработчик", "golang"),
        matcher=is_go_developer_vacancy,
    ),
    "backend_php": Role(
        id="backend_php",
        label="PHP-разработчика",
        button_label="Backend | PHP",
        # «битрикс»/«bitrix» приносят в основном администраторов и продажи —
        # их отсекает фильтр, зато так находятся «Программист Битрикс 24» и
        # «Разработчик Битрикс», где слова PHP нет. «yii» на HH ищет мусор.
        hh_queries=("php", "php разработчик", "php developer", "laravel", "symfony", "битрикс", "bitrix"),
        matcher=is_php_developer_vacancy,
    ),
    "backend_csharp": Role(
        id="backend_csharp",
        label="C#/.NET-разработчика",
        button_label="Backend | C# / .NET",
        hh_queries=("c#", ".net", "asp.net"),
        matcher=is_csharp_developer_vacancy,
    ),
    "devops": Role(
        id="devops",
        label="DevOps-инженера",
        button_label="DevOps / SRE",
        hh_queries=("devops", "sre", "site reliability", "devsecops"),
        matcher=is_devops_vacancy,
    ),
    "fullstack": Role(
        id="fullstack",
        label="fullstack-разработчика",
        button_label="Fullstack",
        # «фуллстек» и «dart» HH ищет нечётко — приносят Python, 1С и всё подряд.
        hh_queries=("fullstack", "full stack", "разработчик полного цикла"),
        matcher=is_fullstack_vacancy,
    ),
    "mobile_flutter": Role(
        id="mobile_flutter",
        label="Flutter-разработчика",
        button_label="Mobile | Flutter",
        hh_queries=("flutter",),
        matcher=is_flutter_developer_vacancy,
    ),
    "mobile_ios": Role(
        id="mobile_ios",
        label="iOS-разработчика",
        button_label="Mobile | iOS",
        hh_queries=("ios", "swift"),
        matcher=is_ios_developer_vacancy,
    ),
    "mobile_android": Role(
        id="mobile_android",
        label="Android-разработчика",
        button_label="Mobile | Android",
        hh_queries=("android", "kotlin"),
        matcher=is_android_developer_vacancy,
    ),
    "mobile_react_native": Role(
        id="mobile_react_native",
        label="React Native-разработчика",
        button_label="Mobile | React Native",
        hh_queries=("react native",),
        matcher=is_react_native_developer_vacancy,
    ),
    "product_manager": Role(
        id="product_manager",
        label="продакт-менеджера",
        button_label="Product Manager",
        hh_queries=(
            "product manager",
            "продакт менеджер",
            "продуктовый менеджер",
            "менеджер продукта",
        ),
        matcher=is_product_manager_vacancy,
        hh_professional_roles=(73,),
    ),
    "product_owner": Role(
        id="product_owner",
        label="владельца продукта",
        button_label="Product Owner",
        hh_queries=("product owner", "продакт оунер", "владелец продукта"),
        matcher=is_product_owner_vacancy,
        hh_professional_roles=(73,),
    ),
    "it_project_manager": Role(
        id="it_project_manager",
        label="IT-проджект-менеджера",
        button_label="IT Project Manager",
        # Только IT-формулировки: голое «project manager» на HH — стройка и ивенты.
        hh_queries=(
            "it project manager",
            "it проджект менеджер",
            "руководитель it проектов",
            "руководитель ит проектов",
            "менеджер it проектов",
            "менеджер ит проектов",
            "delivery manager",
            "technical project manager",
        ),
        matcher=is_it_project_manager_vacancy,
    ),
    "qa_manual": Role(
        id="qa_manual",
        label="QA-инженера (ручное тестирование)",
        button_label="QA | Ручное тестирование",
        hh_queries=(
            "qa engineer",
            "тестировщик",
            "инженер по тестированию",
            "ручное тестирование",
        ),
        matcher=is_qa_manual_vacancy,
        hh_professional_roles=(124,),
    ),
    "qa_automation": Role(
        id="qa_automation",
        label="QA-автоматизатора",
        button_label="QA | Автоматизация",
        hh_queries=(
            "qa automation",
            "автоматизатор тестирования",
            "автоматизация тестирования",
            "aqa",
            "sdet",
        ),
        matcher=is_qa_automation_vacancy,
        hh_professional_roles=(124,),
    ),
    # Data. GetMatch не подключён: сбор оттуда берёт только specialization=design.
    "data_scientist": Role(
        id="data_scientist",
        label="дата-сайентиста",
        button_label="Data Scientist",
        hh_queries=("data scientist", "дата сайентист", "data science"),
        matcher=is_data_scientist_vacancy,
    ),
    "ml_engineer": Role(
        id="ml_engineer",
        label="ML/AI-инженера",
        button_label="ML / AI Engineer",
        # «llm», а не «llm engineer»: поиск HH по названию требует все слова,
        # а пишут чаще «LLM-инженер». Лишнее отсечёт матчер.
        hh_queries=(
            "ml engineer",
            "ml инженер",
            "machine learning",
            "mlops",
            "llm",
            "ai engineer",
            "computer vision",
        ),
        matcher=is_ml_engineer_vacancy,
    ),
    "data_engineer": Role(
        id="data_engineer",
        label="дата-инженера",
        button_label="Data Engineer",
        hh_queries=("data engineer", "инженер данных", "дата инженер", "dwh", "etl"),
        matcher=is_data_engineer_vacancy,
    ),
    "data_analyst": Role(
        id="data_analyst",
        label="аналитика данных",
        button_label="Аналитик данных / BI",
        hh_queries=(
            "аналитик данных",
            "data analyst",
            "дата аналитик",
            "bi аналитик",
            "bi разработчик",
        ),
        matcher=is_data_analyst_vacancy,
    ),
    "product_analyst": Role(
        id="product_analyst",
        label="продуктового аналитика",
        button_label="Продуктовый аналитик",
        hh_queries=("продуктовый аналитик", "product analyst"),
        matcher=is_product_analyst_vacancy,
    ),
    "data_governance": Role(
        id="data_governance",
        label="специалиста по Data Governance",
        button_label="Data Governance",
        hh_queries=(
            "data governance",
            "data steward",
            "качество данных",
            "управление данными",
            "data quality",
            "mdm",
        ),
        matcher=is_data_governance_vacancy,
    ),
    # Руководители. Вакансий мало — около одной в день на все роли вместе, —
    # поэтому дайджест приходит не каждый день, и это нормально.
    "head_of_data": Role(
        id="head_of_data",
        label="руководителя Data",
        button_label="Head of Data / CDO",
        hh_queries=(
            "head of data",
            "chief data officer",
            "директор по данным",
            "директор по аналитике",
            "head of analytics",
            "руководитель аналитики данных",
        ),
        matcher=is_head_of_data_vacancy,
    ),
    "head_of_ai": Role(
        id="head_of_ai",
        label="руководителя AI",
        button_label="Head of AI",
        hh_queries=(
            "head of ai",
            "chief ai officer",
            "директор по искусственному интеллекту",
            "руководитель ai",
            "руководитель ии",
            "head of ml",
        ),
        matcher=is_head_of_ai_vacancy,
    ),
    "head_of_design": Role(
        id="head_of_design",
        label="руководителя дизайна",
        button_label="Head of Design",
        hh_queries=(
            "head of design",
            "design director",
            "директор по дизайну",
            "дизайн директор",
            "руководитель отдела дизайна",
            "руководитель направления дизайна",
        ),
        matcher=is_head_of_design_vacancy,
    ),
    "head_of_product": Role(
        id="head_of_product",
        label="руководителя продукта",
        button_label="Head of Product / CPO",
        hh_queries=("head of product", "cpo", "chief product officer", "директор по продукту", "product director"),
        matcher=is_head_of_product_vacancy,
    ),
    "head_of_engineering": Role(
        id="head_of_engineering",
        label="руководителя разработки",
        button_label="CTO / Head of Engineering",
        hh_queries=(
            "cto",
            "технический директор",
            "engineering manager",
            "head of engineering",
            "руководитель разработки",
            "директор по разработке",
        ),
        matcher=is_head_of_engineering_vacancy,
    ),
    # Legacy — для уже подписанных пользователей, не показываем в меню
    "frontend": Role(
        id="frontend",
        label="frontend-разработчика",
        button_label="Frontend",
        hh_queries=(
            "frontend developer",
            "frontend разработчик",
            "фронтенд разработчик",
            "react developer",
            "vue developer",
            "angular developer",
            "frontend",
            "фронтенд",
        ),
        matcher=is_frontend_vacancy,
    ),
    "backend": Role(
        id="backend",
        label="backend-разработчика",
        button_label="Backend",
        hh_queries=(
            "backend developer",
            "backend разработчик",
            "бэкенд разработчик",
            "python developer",
            "go developer",
            "java developer",
            "backend",
            "бэкенд",
        ),
        matcher=is_backend_vacancy,
    ),
}

def get_role(role_id: str) -> Optional[Role]:
    return ROLES.get(role_id)
