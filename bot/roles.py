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
    is_python_developer_vacancy,
    is_react_developer_vacancy,
    is_vue_developer_vacancy,
)


@dataclass(frozen=True)
class Role:
    id: str
    label: str
    button_label: str
    hh_queries: tuple[str, ...]
    habr_queries: tuple[str, ...]
    geekjob_queries: tuple[str, ...]
    uses_getmatch: bool
    matcher: Callable[[str], bool]


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
        ),
        habr_queries=("продуктовый дизайнер", "product designer", "ux ui designer"),
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
        habr_queries=("коммуникационный дизайнер", "communication designer", "communication design"),
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
        habr_queries=("графический дизайнер", "graphic designer", "graphic design"),
        geekjob_queries=("графический дизайнер", "graphic designer", "дизайнер"),
        uses_getmatch=True,
        matcher=is_graphic_designer_vacancy,
    ),
    "frontend_react": Role(
        id="frontend_react",
        label="React-разработчика",
        button_label="Frontend | React",
        hh_queries=("react developer", "react разработчик", "frontend react", "react frontend"),
        habr_queries=("react", "react developer", "react разработчик"),
        geekjob_queries=("react", "react developer"),
        uses_getmatch=False,
        matcher=is_react_developer_vacancy,
    ),
    "frontend_vue": Role(
        id="frontend_vue",
        label="Vue-разработчика",
        button_label="Frontend | Vue",
        hh_queries=("vue developer", "vue разработчик", "vue.js developer", "frontend vue"),
        habr_queries=("vue", "vue.js", "vue developer", "vue разработчик"),
        geekjob_queries=("vue", "vue.js", "vue developer"),
        uses_getmatch=False,
        matcher=is_vue_developer_vacancy,
    ),
    "frontend_angular": Role(
        id="frontend_angular",
        label="Angular-разработчика",
        button_label="Frontend | Angular",
        hh_queries=("angular developer", "angular разработчик", "frontend angular"),
        habr_queries=("angular", "angular developer", "angular разработчик"),
        geekjob_queries=("angular", "angular developer"),
        uses_getmatch=False,
        matcher=is_angular_developer_vacancy,
    ),
    "backend_python": Role(
        id="backend_python",
        label="Python-разработчика",
        button_label="Backend | Python",
        hh_queries=("python developer", "python разработчик", "python backend", "django developer"),
        habr_queries=("python", "python developer", "python разработчик"),
        geekjob_queries=("python", "python developer", "django"),
        uses_getmatch=False,
        matcher=is_python_developer_vacancy,
    ),
    "backend_java": Role(
        id="backend_java",
        label="Java-разработчика",
        button_label="Backend | Java",
        hh_queries=("java developer", "java разработчик", "java backend", "spring developer"),
        habr_queries=("java developer", "java разработчик", "java backend"),
        geekjob_queries=("java", "java developer", "spring"),
        uses_getmatch=False,
        matcher=is_java_developer_vacancy,
    ),
    "backend_go": Role(
        id="backend_go",
        label="Go-разработчика",
        button_label="Backend | Go",
        hh_queries=("go developer", "golang developer", "go разработчик", "golang разработчик"),
        habr_queries=("golang", "go developer", "go разработчик"),
        geekjob_queries=("golang", "go developer", "go backend"),
        uses_getmatch=False,
        matcher=is_go_developer_vacancy,
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
        ),
        habr_queries=("frontend", "react", "vue", "angular", "фронтенд"),
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
        ),
        habr_queries=("backend", "python developer", "go developer", "java developer", "бэкенд"),
        geekjob_queries=("backend", "python", "golang", "java", "бэкенд"),
        uses_getmatch=False,
        matcher=is_backend_vacancy,
    ),
}

# Порядок кнопок в меню выбора роли
MVP_ROLE_IDS = (
    "product_designer",
    "communication_designer",
    "graphic_designer",
    "frontend_react",
    "frontend_vue",
    "frontend_angular",
    "backend_python",
    "backend_java",
    "backend_go",
)


def get_role(role_id: str) -> Optional[Role]:
    return ROLES.get(role_id)
