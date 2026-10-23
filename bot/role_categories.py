from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class RoleCategory:
    id: str
    title: str
    role_ids: tuple[str, ...]


CATEGORIES: dict[str, RoleCategory] = {
    "design": RoleCategory(
        id="design",
        title="Дизайн",
        role_ids=(
            "product_designer",
            "communication_designer",
            "graphic_designer",
            "art_director",
        ),
    ),
    "frontend": RoleCategory(
        id="frontend",
        title="Frontend",
        role_ids=("frontend_react", "frontend_vue", "frontend_angular"),
    ),
    "backend": RoleCategory(
        id="backend",
        title="Backend",
        role_ids=("backend_python", "backend_java", "backend_go"),
    ),
    "product": RoleCategory(
        id="product",
        title="Продукт",
        role_ids=("product_manager", "product_owner"),
    ),
    "qa": RoleCategory(
        id="qa",
        title="QA",
        role_ids=("qa_manual", "qa_automation"),
    ),
    "data": RoleCategory(
        id="data",
        title="Data",
        role_ids=(
            "data_scientist",
            "ml_engineer",
            "data_engineer",
            "data_analyst",
            "product_analyst",
            "data_governance",
        ),
    ),
    "leaders": RoleCategory(
        id="leaders",
        title="Руководители",
        role_ids=(
            "head_of_data",
            "head_of_ai",
            "head_of_design",
            "head_of_product",
            "head_of_engineering",
        ),
    ),
}

CATEGORY_IDS = tuple(CATEGORIES.keys())

ROLE_TO_CATEGORY: dict[str, str] = {
    role_id: category.id
    for category in CATEGORIES.values()
    for role_id in category.role_ids
}


def get_category(category_id: str) -> Optional[RoleCategory]:
    return CATEGORIES.get(category_id)
