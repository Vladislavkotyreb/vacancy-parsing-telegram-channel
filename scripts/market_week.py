"""Цифры рынка за неделю — готовый текст поста для LinkedIn / Телеграма.

Собирает вакансии за 7 дней теми же парсерами и фильтрами ролей, что и
рассылка подписчикам, и считает по ним цифры. Ничего не отправляет и ничего
не пишет в базу бота.

    PYTHONIOENCODING=utf-8 .venv/bin/python scripts/market_week.py
    PYTHONIOENCODING=utf-8 .venv/bin/python scripts/market_week.py --roles product_designer,devops

Запускать не с 10:00 до 10:30 МСК (утренние пост и рассылка). Сбор занимает
несколько минут. Текст печатается и сохраняется в logs/market_week.txt.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import re
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from bot.config import Settings  # noqa: E402
from bot.cross_source import dedupe_across_sources, normalize_company  # noqa: E402
from bot.dates import is_fresh  # noqa: E402
from bot.models import Vacancy  # noqa: E402
from bot.regions import CIS, for_region  # noqa: E402
from bot.role_categories import CATEGORIES, CATEGORY_IDS  # noqa: E402
from bot.roles import ROLES  # noqa: E402
from bot.runtime import limit_threads  # noqa: E402
from bot.subscriber_collect import SourceLimited, collect_for_role, shared_feeds  # noqa: E402

WEEK_HOURS = 7 * 24
BOT_LINK = "https://t.me/productdesignervacparser228bot"
# Старые роли первой версии бота дублируют новые — в цифрах рынка их нет.
SKIP_ROLES = {"frontend", "backend"}
MIN_SALARIES_FOR_MEDIAN = 5
log = logging.getLogger("market_week")

_NUMBER = re.compile(r"\d[\d\s  ]*\d|\d")
_RUB = re.compile(r"₽|руб|rub|rur", re.I)


def salary_rub(text: Optional[str]) -> Optional[int]:
    """Месячная зарплата в рублях из строки площадки: середина вилки или одна граница.

    «от 250 000 ₽» → 250000, «200 000 — 300 000 ₽» → 250000. Не рубли, «за
    час» и явно странные значения — None: медиана по ним только врёт.
    """
    if not text or not _RUB.search(text) or re.search(r"час|hour|год|year", text, re.I):
        return None
    numbers = [int(re.sub(r"\D", "", n)) for n in _NUMBER.findall(text)]
    numbers = [n for n in numbers if 10_000 <= n <= 3_000_000]
    if not numbers:
        return None
    return int(sum(numbers[:2]) / len(numbers[:2]))


def is_remote(vacancy: Vacancy) -> bool:
    text = f"{vacancy.work_format or ''} {vacancy.location or ''}".lower()
    return "удал" in text or "remote" in text


def _money(value: float) -> str:
    return f"{round(value / 1000):,}".replace(",", " ") + " тыс ₽"


def _pct(part: int, whole: int) -> str:
    return f"{round(100 * part / whole)}%" if whole else "—"


async def collect(settings: Settings, role_ids: list[str]) -> tuple[dict[str, list[Vacancy]], list[str]]:
    by_role: dict[str, list[Vacancy]] = {}
    incomplete: list[str] = []
    with shared_feeds():
        for role_id in role_ids:
            try:
                vacancies = await collect_for_role(settings, ROLES[role_id])
            except SourceLimited as exc:
                vacancies = exc.vacancies
                incomplete.append(role_id)
            except Exception:
                logging.exception("Роль %s не собралась", role_id)
                incomplete.append(role_id)
                vacancies = []
            fresh = [v for v in for_region(vacancies, CIS) if is_fresh(v, WEEK_HOURS)]
            by_role[role_id] = fresh
            log.info("%s: %s вакансий за неделю", role_id, len(fresh))
    return by_role, incomplete


def build_post(by_role: dict[str, list[Vacancy]], incomplete: list[str], today: datetime) -> str:
    everything = dedupe_across_sources([v for vs in by_role.values() for v in vs])
    total = len(everything)
    week_from = (today - timedelta(days=7)).strftime("%d.%m")
    week_to = today.strftime("%d.%m")

    lines = [
        f"IT-вакансии за неделю {week_from}–{week_to}: {total} вакансий",
        "",
        "Собрал бот, который каждое утро присылает подборку по твоей роли с HH, "
        "Хабр Карьеры, GeekJob и GetMatch. Цифры — по России и СНГ, только вакансии "
        "с релевантным названием, без дублей между площадками.",
        "",
    ]

    # Направления: сколько вакансий и сколько из них удалённых.
    lines.append("По направлениям:")
    rows = []
    for category_id in CATEGORY_IDS:
        role_ids = [r for r in CATEGORIES[category_id].role_ids if r in by_role]
        if not role_ids:
            continue
        vacancies = dedupe_across_sources([v for r in role_ids for v in by_role[r]])
        if vacancies:
            rows.append((len(vacancies), CATEGORIES[category_id].title, sum(is_remote(v) for v in vacancies)))
    for count, title, remote in sorted(rows, reverse=True):
        lines.append(f"• {title} — {count} (удалённо {_pct(remote, count)})")
    lines.append("")

    # Роли с медианой зарплаты — только где указана зарплата у достаточного числа вакансий.
    salary_rows = []
    for role_id, vacancies in by_role.items():
        salaries = [s for s in (salary_rub(v.salary) for v in vacancies) if s]
        if len(salaries) >= MIN_SALARIES_FOR_MEDIAN:
            salary_rows.append((statistics.median(salaries), ROLES[role_id].button_label, len(salaries), len(vacancies)))
    if salary_rows:
        lines.append("Медиана зарплат в вакансиях, где она указана:")
        for median, label, with_salary, count in sorted(salary_rows, reverse=True)[:10]:
            lines.append(f"• {label} — {_money(median)} (зарплата указана в {with_salary} из {count})")
        lines.append("")

    # Кто больше всех нанимает.
    companies: Counter = Counter()
    names: dict[str, str] = {}
    for vacancy in everything:
        key = normalize_company(vacancy.company)
        if key and key not in ("—", "-"):
            companies[key] += 1
            names.setdefault(key, vacancy.company)
    top = [(names[k], n) for k, n in companies.most_common(5) if n >= 2]
    if top:
        lines.append("Больше всех нанимают: " + ", ".join(f"{name} ({n})" for name, n in top))
        lines.append("")

    remote_total = sum(is_remote(v) for v in everything)
    salary_total = sum(1 for v in everything if salary_rub(v.salary))
    lines.append(f"Удалённых — {_pct(remote_total, total)}, зарплата указана в {_pct(salary_total, total)} вакансий.")
    lines.append("")
    lines.append(f"Свежие вакансии по своей роли каждое утро — в боте: {BOT_LINK}")

    if incomplete:
        lines.append("")
        lines.append(
            "[для себя, не публиковать] Неполный сбор (HH или площадка не ответили): "
            + ", ".join(incomplete)
        )
    return "\n".join(lines)


async def main() -> int:
    parser = argparse.ArgumentParser(description="Цифры рынка за неделю — текст поста")
    parser.add_argument("--roles", help="через запятую; по умолчанию все роли меню")
    parser.add_argument("--out", default=str(REPO / "logs" / "market_week.txt"))
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    log.setLevel(logging.INFO)
    limit_threads()

    role_ids = [r.strip() for r in args.roles.split(",")] if args.roles else [
        r for r in ROLES if r not in SKIP_ROLES
    ]
    unknown = [r for r in role_ids if r not in ROLES]
    if unknown:
        print(f"Неизвестные роли: {', '.join(unknown)}")
        return 1

    settings = replace(Settings.from_env(), max_vacancy_age_hours=WEEK_HOURS)
    by_role, incomplete = await collect(settings, role_ids)
    post = build_post(by_role, incomplete, datetime.now())

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(post, encoding="utf-8")
    print(post)
    print(f"\n(сохранено в {out})")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
