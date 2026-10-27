"""Платное размещение вакансий («Партнёрская вакансия»).

Админ добавляет вакансию командой /promo_add (bot/chat_main.py); утренняя
рассылка отправляет её отдельным сообщением перед подборкой подписчикам
нужных ролей — каждому один раз, не больше одной рекламной вакансии в день.
Пометка «Реклама» стоит всегда: в РФ платная реклама в интернете требует
маркировки (рекламодатель и токен erid из ОРД).
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Optional

from bot.role_categories import CATEGORIES
from bot.roles import ROLES

MAX_DAYS = 60

# Поля команды: ключ в сообщении → поле Promo. Порядок — как в подсказке.
FIELDS = {
    "роли": "roles",
    "дней": "days",
    "должность": "title",
    "компания": "company",
    "зарплата": "salary",
    "формат": "work_format",
    "ссылка": "url",
    "erid": "erid",
}
REQUIRED = ("roles", "days", "title", "company", "url")

PROMO_HELP = (
    "Партнёрская вакансия — одним сообщением, каждое поле с новой строки:\n\n"
    "/promo_add\n"
    "роли: product_designer, design_lead\n"
    "дней: 7\n"
    "должность: Senior Product Designer\n"
    "компания: Ozon\n"
    "зарплата: от 300 000 ₽\n"
    "формат: удалённо\n"
    "ссылка: https://...\n"
    "erid: 2SDnje… (токен из ОРД, если есть)\n\n"
    "Роли — id ролей или разделов целиком (design, product, devops…). "
    "Зарплата, формат и erid необязательны.\n"
    "Посмотреть: /promo_list · снять: /promo_stop <номер>"
)


@dataclass
class Promo:
    roles: list[str]
    days: int
    title: str
    company: str
    url: str
    salary: Optional[str] = None
    work_format: Optional[str] = None
    erid: Optional[str] = None
    id: Optional[int] = None
    expires_at: Optional[str] = None
    active: bool = True


def resolve_roles(spec: str) -> tuple[list[str], list[str]]:
    """«product_designer, devops» или «design» → id ролей; второе — что не узнали."""
    roles: list[str] = []
    unknown: list[str] = []
    for part in (p.strip().lower() for p in spec.replace(";", ",").split(",")):
        if not part:
            continue
        if part in CATEGORIES:
            roles.extend(CATEGORIES[part].role_ids)
        elif part in ROLES:
            roles.append(part)
        else:
            unknown.append(part)
    return list(dict.fromkeys(roles)), unknown


def parse_promo(text: str) -> tuple[Optional[Promo], list[str]]:
    """Текст команды → (Promo или None, список ошибок по-человечески)."""
    values: dict[str, str] = {}
    for line in text.splitlines()[1:]:  # первая строка — сама команда
        key, sep, value = line.partition(":")
        field = FIELDS.get(key.strip().lower())
        if sep and field and value.strip():
            values[field] = value.strip()

    errors = [f"нет поля «{k}»" for k, f in FIELDS.items() if f in REQUIRED and f not in values]
    roles: list[str] = []
    if "roles" in values:
        roles, unknown = resolve_roles(values["roles"])
        if unknown:
            errors.append(f"неизвестные роли: {', '.join(unknown)}")
        if not roles and not unknown:
            errors.append("не указано ни одной роли")
    days = 0
    if "days" in values:
        try:
            days = int(values["days"])
        except ValueError:
            days = 0
        if not 1 <= days <= MAX_DAYS:
            errors.append(f"«дней» — число от 1 до {MAX_DAYS}")
    url = values.get("url", "")
    if url and not url.startswith(("https://", "http://")):
        errors.append("ссылка должна начинаться с https://")
    if errors:
        return None, errors

    return Promo(
        roles=roles,
        days=days,
        title=values["title"],
        company=values["company"],
        url=url,
        salary=values.get("salary"),
        work_format=values.get("work_format"),
        erid=values.get("erid"),
    ), []


def format_promo(promo: Promo) -> str:
    esc = html.escape
    lines = [
        "📌 <i>Реклама · Партнёрская вакансия</i>",
        "",
        f"🎨 <b>{esc(promo.title)}</b>",
        f"🏢 {esc(promo.company)}",
    ]
    if promo.salary:
        lines.append(f"💰 {esc(promo.salary)}")
    if promo.work_format:
        lines.append(f"📍 {esc(promo.work_format)}")
    lines.append(f'<a href="{esc(promo.url, quote=True)}">Откликнуться</a>')
    footer = f"Рекламодатель: {esc(promo.company)}"
    if promo.erid:
        footer += f" · erid: {esc(promo.erid)}"
    lines.extend(["", f"<i>{footer}</i>"])
    return "\n".join(lines)


def promo_from_row(row: dict) -> Promo:
    return Promo(
        roles=row["roles"].split(","),
        days=0,
        title=row["title"],
        company=row["company"],
        url=row["url"],
        salary=row.get("salary"),
        work_format=row.get("work_format"),
        erid=row.get("erid"),
        id=row["id"],
        expires_at=row["expires_at"],
        active=bool(row["active"]),
    )
