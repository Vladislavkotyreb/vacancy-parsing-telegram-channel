from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from bot.filters import is_product_designer_vacancy
from bot.role_filters import (
    is_angular_developer_vacancy,
    is_backend_vacancy,
    is_communication_designer_vacancy,
    is_frontend_vacancy,
    is_go_developer_vacancy,
    is_graphic_designer_vacancy,
    is_java_developer_vacancy,
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
    geekjob_queries: tuple[str, ...]
    uses_getmatch: bool
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
        geekjob_queries=("продуктовый дизайнер", "product designer", "ux designer"),
        uses_getmatch=True,
        matcher=is_product_designer_vacancy,
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
        geekjob_queries=("коммуникационный дизайнер", "communication designer", "communication design"),
        uses_getmatch=True,
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
        geekjob_queries=("графический дизайнер", "graphic designer", "дизайнер"),
        uses_getmatch=True,
        matcher=is_graphic_designer_vacancy,
    ),
    "frontend_react": Role(
        id="frontend_react",
        label="React-разработчика",
        button_label="Frontend | React",
        hh_queries=("react developer", "react разработчик", "frontend react", "react frontend", "react"),
        geekjob_queries=("react", "react developer"),
        uses_getmatch=False,
        matcher=is_react_developer_vacancy,
    ),
    "frontend_vue": Role(
        id="frontend_vue",
        label="Vue-разработчика",
        button_label="Frontend | Vue",
        hh_queries=("vue developer", "vue разработчик", "vue.js developer", "frontend vue", "vue.js"),
        geekjob_queries=("vue", "vue.js", "vue developer"),
        uses_getmatch=False,
        matcher=is_vue_developer_vacancy,
    ),
    "frontend_angular": Role(
        id="frontend_angular",
        label="Angular-разработчика",
        button_label="Frontend | Angular",
        hh_queries=("angular developer", "angular разработчик", "frontend angular", "angular"),
        geekjob_queries=("angular", "angular developer"),
        uses_getmatch=False,
        matcher=is_angular_developer_vacancy,
    ),
    "backend_python": Role(
        id="backend_python",
        label="Python-разработчика",
        button_label="Backend | Python",
        hh_queries=("python developer", "python разработчик", "python backend", "django developer", "python"),
        geekjob_queries=("python", "python developer", "django"),
        uses_getmatch=False,
        matcher=is_python_developer_vacancy,
    ),
    "backend_java": Role(
        id="backend_java",
        label="Java-разработчика",
        button_label="Backend | Java",
        hh_queries=("java developer", "java разработчик", "java backend", "spring developer", "java"),
        geekjob_queries=("java", "java developer", "spring"),
        uses_getmatch=False,
        matcher=is_java_developer_vacancy,
    ),
    "backend_go": Role(
        id="backend_go",
        label="Go-разработчика",
        button_label="Backend | Go",
        hh_queries=("go developer", "golang developer", "go разработчик", "golang разработчик", "golang"),
        geekjob_queries=("golang", "go developer", "go backend"),
        uses_getmatch=False,
        matcher=is_go_developer_vacancy,
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
        geekjob_queries=("product manager", "продакт менеджер", "продуктовый менеджер"),
        uses_getmatch=False,
        matcher=is_product_manager_vacancy,
        hh_professional_roles=(73,),
    ),
    "product_owner": Role(
        id="product_owner",
        label="владельца продукта",
        button_label="Product Owner",
        hh_queries=("product owner", "продакт оунер", "владелец продукта"),
        geekjob_queries=("product owner", "владелец продукта"),
        uses_getmatch=False,
        matcher=is_product_owner_vacancy,
        hh_professional_roles=(73,),
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
        geekjob_queries=("qa", "тестировщик", "тестирование"),
        uses_getmatch=False,
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
        geekjob_queries=("qa automation", "автоматизация тестирования", "aqa"),
        uses_getmatch=False,
        matcher=is_qa_automation_vacancy,
        hh_professional_roles=(124,),
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
        geekjob_queries=("frontend", "react", "vue", "angular", "фронтенд"),
        uses_getmatch=False,
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
        geekjob_queries=("backend", "python", "golang", "java", "бэкенд"),
        uses_getmatch=False,
        matcher=is_backend_vacancy,
    ),
}

def get_role(role_id: str) -> Optional[Role]:
    return ROLES.get(role_id)
