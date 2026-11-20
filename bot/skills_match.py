"""Доля распознанных навыков вакансии, которые упомянуты в резюме."""
from __future__ import annotations

import html
import re
from typing import Any, Iterable, Optional

from bot.models import Vacancy

# Ключи — стабильные названия, хранимые в SQLite и показанные в Telegram.
_ALIASES = {
    "Figma": r"figma|фигм[аеу]",
    "UX-исследования": r"ux[- ]исследован\w*|ux research\w*|user research\w*|пользовательск\w* исследован\w*",
    "Прототипирование": r"прототип\w*|prototyp\w*",
    "Дизайн-системы": r"дизайн[- ]систем\w*|design systems?",
    "A/B-тесты": r"[aа]/[bб][- ](?:тест\w*|test\w*)",
    "React": r"react(?:\.js|js)?",
    "Vue": r"vue(?:\.js|js)?",
    "Node.js": r"node\.?js",
    "JavaScript": r"javascript|js",
    "TypeScript": r"typescript|ts",
    "Go": r"golang|(?-i:Go)",
    "C++": r"c\+\+",
    ".NET": r"\.net",
    "Discovery": r"(?:product )?discovery|дискавери",
    "Roadmap": r"roadmaps?|дорожн\w+ карт\w*",
    "CustDev": r"custdev|customer development|кастдев\w*",
    "Юнит-экономика": r"юнит[- ]экономик\w*|unit economics",
    "C#": r"c#|c sharp",
    "PostgreSQL": r"postgres(?:ql)?",
    "Kubernetes": r"kubernetes|k8s",
    "CI/CD": r"ci[ /-]cd",
    "ML": r"ml|machine learning|машинн\w+ обучени\w*",
}
for _skill in (
    "Python SQL HTML CSS Java Kotlin Swift Flutter Dart PHP Angular Django FastAPI "
    "Spring Docker Linux Git Redis Kafka Spark Airflow ClickHouse PowerBI Tableau "
    "Excel Pandas PyTorch TensorFlow Jira Scrum Kanban Selenium Playwright Pytest "
    "REST GraphQL AWS Terraform Ansible ETL Photoshop Illustrator AfterEffects"
).split():
    _ALIASES[_skill] = re.escape(_skill)
_ALIASES["PowerBI"] = r"power\s?bi"
_ALIASES["AfterEffects"] = r"after\s?effects"
# Один проход по тексту. Составные имена (Node.js) выигрывают у частей (js).
_PATTERN = re.compile(r"(?<!\w)(?:" + "|".join(
    rf"(?P<s{i}>{pattern})"
    for i, pattern in enumerate(_ALIASES.values())
) + r")(?!\w)", re.I)
_NAMES = tuple(_ALIASES)


def extract_skills(text: str) -> list[str]:
    text = text.replace("‑", "-").replace("–", "-")
    return sorted({_NAMES[int(match.lastgroup[1:])] for match in _PATTERN.finditer(text)})


def source_text(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(source_text(item) for item in value)
    if isinstance(value, dict):
        return source_text(value.get("title") or value.get("name") or value.get("value"))
    if isinstance(value, str):
        return html.unescape(re.sub("<[^>]+>", " ", value))
    return ""


_BONUS = re.compile(r"будет плюсом|будет преимуществом|желательно|nice[- ]to[- ]have|is a plus|preferred", re.I)
_NOT_REQUIRED = re.compile(r"не требу(?:ется|ются)|not required", re.I)


def requirement_clauses(*fields: Any):
    for value in fields:
        # Точка внутри Node.js или .NET не разделяет требования.
        for clause in re.split(r"[;\n]|[.!?](?=\s|$)", source_text(value)):
            if clause.strip() and not _NOT_REQUIRED.search(clause):
                yield clause, bool(_BONUS.search(clause))


def skill_requirements(*fields: Any) -> tuple[list[str], list[str]]:
    required, bonus = set(), set()
    for clause, optional in requirement_clauses(*fields):
        target = bonus if optional else required
        target.update(extract_skills(clause))
    return sorted(required), sorted(bonus - required)


def match_line(vacancy: Vacancy, resume: Optional[Iterable[str]]) -> str:
    if resume is None:
        return "📎 Совпадение по навыкам: добавь резюме через /resume"
    required = set(vacancy.skills or extract_skills(vacancy.title))
    if not required:
        return "📎 Совпадение по навыкам: в вакансии не распознаны навыки"
    common = sorted(required.intersection(resume))
    score = round(100 * len(common) / len(required))
    line = f"🎯 Совпадение по навыкам: {score}% ({len(common)} из {len(required)})"
    if common:
        line += "\nСовпали: " + ", ".join(common)
    missing = sorted(required.difference(common))
    if missing:
        line += "\nНе найдены в резюме: " + ", ".join(missing)
    return line
