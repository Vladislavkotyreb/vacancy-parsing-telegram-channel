from __future__ import annotations

from bot.roles import ROLES, get_role


def format_subscription_roles(role_ids: list[str]) -> str:
    """Именительный падеж для «Текущая подписка: …»."""
    labels = []
    for role_id in role_ids:
        role = get_role(role_id)
        if role:
            labels.append(role.button_label)
        else:
            labels.append(role_id)
    return ", ".join(labels) if labels else "не выбрана"


def format_digest_roles_label(role_ids: list[str]) -> str:
    """Подпись для заголовка дайджеста."""
    if not role_ids:
        return "по вашим подпискам"
    if len(role_ids) == 1:
        role = get_role(role_ids[0])
        return role.label if role else role_ids[0]
    names = [ROLES[role_id].button_label for role_id in role_ids if role_id in ROLES]
    return f"({', '.join(names)})"


def format_success_roles(role_ids: list[str]) -> str:
    """Текст после оформления подписки."""
    if not role_ids:
        return "новые вакансии"
    if len(role_ids) == 1:
        role = get_role(role_ids[0])
        return f"новые вакансии {role.label}" if role else "новые вакансии"
    return f"новые вакансии по ролям: {format_subscription_roles(role_ids)}"


def plural_ru(n: int, one: str, few: str, many: str) -> str:
    """1 вакансия, 2 вакансии, 5 вакансий; 11–19 — всегда третья форма."""
    n = abs(n) % 100
    if 11 <= n <= 19:
        return many
    n %= 10
    if n == 1:
        return one
    if 2 <= n <= 4:
        return few
    return many
