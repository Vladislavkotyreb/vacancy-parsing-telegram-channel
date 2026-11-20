"""Сравнение профессиональных фактов в резюме с доступными требованиями вакансии."""
from __future__ import annotations

import re
from datetime import date
from dataclasses import dataclass, field
from typing import Optional

from bot.grades import extract_grade
from bot.models import Vacancy
from bot.roles import ROLES
from bot.skills_match import extract_skills, match_line, requirement_clauses


@dataclass
class ResumeProfile:
    skills: list[str] = field(default_factory=list)
    roles: list[str] = field(default_factory=list)
    grades: dict[str, str] = field(default_factory=dict)
    years: Optional[int] = None
    years_from_dates: bool = False
    city: Optional[str] = None
    formats: list[str] = field(default_factory=list)
    tasks: dict[str, str] = field(default_factory=dict)


# Для вакансии достаточно названной обязанности. Для резюме ищем выполненное действие.
_TASK_RULES = {
    "управление командой": (
        r"руковод\w* команд|управ\w* команд|people management|manag\w* (?:a |the )?team",
        r"(?:руководил[аи]?|управлял[аи]?|собрал[аи]?) команд(?:ой|у)(?: из \d+ (?:дизайнеров|разработчиков))?|"
        r"(?:managed|led|built) (?:a |the )?team(?: of \d+ (?:designers|engineers))?"),
    "наставничество": (r"ментор\w*|наставнич\w*|mentor\w*",
                        r"менторил[аи]?|обучал[аи]? (?:дизайнеров|разработчиков)|mentored"),
    "исследования пользователей": (
        r"(?:ux|user)[ -]research|пользовательск\w+ исследован|интервью с пользовател",
        r"(?:пров[её]л[аи]?|проводил[аи]?) (?:\d+ )?(?:интервью с пользователями|(?:UX[- ]|пользовательские )исследования)|conducted user research"),
    "развитие дизайн-системы": (r"дизайн[- ]систем|design system",
                               r"(?:создал[аи]?|построил[аи]?|развивал[аи]?|внедрил[аи]?) дизайн[- ]систему|(?:built|maintained) (?:a |the )?design system"),
    "улучшение продуктовых метрик": (
        r"рост конверсии|(?:повыш|увелич)\w* конверси|продуктовы\w+ метрик|increase conversion|improve retention",
        r"(?:повысил[аи]?|увеличил[аи]?|поднял[аи]?) (?:конверсию|retention|удержание) "
        r"(?:(?:на|с) \d+(?:[.,]\d+)?%(?: до \d+(?:[.,]\d+)?%)?)|"
        r"(?:increased|improved) (?:conversion|retention) by \d+(?:[.,]\d+)?%"),
    "проектирование интерфейсов": (
        r"проектирова\w* интерфейс|interaction design|design user flows",
        r"(?:спроектировал[аи]?|разработал[аи]?) (?:пользовательски[ей] |мобильны[ей] )?интерфейс\w*|designed user flows"),
    "эксперименты": (r"[aа]/[bб][- ](?:тест|эксперимент|test)",
                     r"(?:запустил[аи]?|проводил[аи]?|пров[её]л[аи]?) [aа]/[bб][- ]тест\w*|ran a/b tests"),
    "оптимизация производительности": (
        r"high[- ]load|высок\w+ нагруз\w*|оптимизаци\w* производительности|latency|throughput",
        r"сократил[аи]? время ответа|оптимизировал[аи]? производительность|reduced (?:api )?latency"),
    "автоматизация тестирования": (r"автотест|автоматизаци\w* тестирован|test automation|automated tests",
                                   r"писал[аи]? автотесты|написал[аи]? автотесты|автоматизировал[аи]? тестирование|wrote automated tests"),
    "поставка в production": (r"ci[ /-]cd|deployment pipeline|релизн\w+ процесс",
                              r"(?:настроил[аи]?|внедрил[аи]?) ci[ /-]cd|built (?:a |the )?deployment pipeline"),
}
_TASKS = {name: (re.compile(req, re.I), re.compile(done, re.I))
          for name, (req, done) in _TASK_RULES.items()}
_NEGATED = re.compile(r"\b(?:не|не приходилось|never|not|did not|have not|никогда не)\s*$", re.I)
_TITLE = re.compile(r"дизайнер|руководитель|директор|лид\b|менеджер|аналитик|инженер|"
                    r"разработчик|тестировщик|designer|director|manager|engineer|developer|analyst|"
                    r"\b(?:lead|head|qa|devops|cto|cpo)\b|scientist|архитектор", re.I)
_COLLABORATION = re.compile(r"вместе с|совместно с|работал[аи]? с|ищем|worked with|hiring|collaborat", re.I)
_FORMATS = {"удалённо": r"удал[её]н\w*|remote", "гибрид": r"гибрид\w*|hybrid", "офис": r"офис\w*|on[- ]?site|in[- ]office"}
_TOTAL_YEARS = re.compile(r"(?:общий (?:стаж|опыт)|опыт работы|стаж работы|total experience)\s*[:—–-]?\s*(\d{1,2})\s*(?:лет|год\w*|years?)\b", re.I)


# Интервалы учитываем только внутри раздела трудового опыта. Стаж округляем вниз.
_MONTH_NAMES = (
    ("янв", "jan"), ("фев", "feb"), ("мар", "mar"), ("апр", "apr"), ("ма", "may"),
    ("июн", "jun"), ("июл", "jul"), ("авг", "aug"), ("сен", "sep"), ("окт", "oct"),
    ("ноя", "nov"), ("дек", "dec"),
)
_DATE = (r"(?:(?:0?[1-9]|1[0-2])[./]|(?:январ|феврал|март|апрел|ма[йя]|июн|июл|август|"
         r"сентябр|октябр|ноябр|декабр|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
         r"[а-яa-z]*\.?\s+)(?:19|20)\d{2}")
_PERIOD = re.compile(rf"(?<!\w)({_DATE})\s*(?:[-–—]|to)\s*({_DATE}|present|current|настоящее время|по н\.?\s?в\.?)", re.I)


def _month_number(value: str) -> int:
    year = int(value[-4:])
    prefix = value[:-4].lower().strip(" ./")
    if prefix.isdigit():
        month = int(prefix)
    else:
        month = next(i for i, names in enumerate(_MONTH_NAMES, 1) if prefix.startswith(names))
    return year * 12 + month


def _employment_years(text: str) -> Optional[int]:
    declared = _TOTAL_YEARS.search(text)
    if declared:
        return int(declared[1])
    in_history = False
    intervals = []
    today = date.today()
    current = today.year * 12 + today.month
    for line in text.splitlines():
        title = line.strip().rstrip(":").casefold()
        if title in ("опыт работы", "профессиональный опыт", "work experience", "experience", "employment history"):
            in_history = True
        elif title in ("образование", "education", "обучение", "курсы", "projects", "проекты", "навыки", "skills"):
            in_history = False
        if in_history:
            for start, end in _PERIOD.findall(line):
                first = _month_number(start)
                last = _month_number(end) if end[-1].isdigit() else current
                if first <= last <= current:
                    intervals.append((first, last + 1))
    months, covered = 0, 0
    for start, end in sorted(intervals):
        months += max(0, end - max(covered, start))
        covered = max(covered, end)
    return months // 12 if months else None


def _roles(title: str) -> list[str]:
    if not _TITLE.search(title) or _COLLABORATION.search(title):
        return []
    roles = [role.id for role in ROLES.values() if role.matcher(title)]
    return [r for r in roles if r not in ("backend", "frontend")] or roles


def work_formats(text: str) -> list[str]:
    return [name for name, pattern in _FORMATS.items() if re.search(pattern, text, re.I)]


def vacancy_tasks(*fields) -> list[str]:
    clauses = [text for text, optional in requirement_clauses(*fields) if not optional]
    return [name for name, (requirement, _) in _TASKS.items()
            if any(requirement.search(c) for c in clauses)]


def parse_profile(text: str) -> ResumeProfile:
    profile = ResumeProfile(skills=extract_skills(text))
    for line in text.splitlines():
        line = " ".join(line.split())
        if not line:
            continue
        if len(line) <= 100 and len(line.split()) <= 10:
            for role in _roles(line):
                if role not in profile.roles:
                    profile.roles.append(role)
                grade = extract_grade(line)
                if grade:
                    profile.grades.setdefault(role, grade)
        if re.match(r"(?:формат работы|предпочитаемый формат|work preference)\s*[:—-]", line, re.I):
            profile.formats = work_formats(line) if not re.search(r"\b(?:не|кроме|except|not)\b", line, re.I) else []
        city = re.fullmatch(r"(?:город(?: проживания)?|city)\s*:\s*([а-яёa-z][а-яёa-z -]{1,45})", line, re.I)
        if city and profile.city is None:
            profile.city = city[1].strip()
        for name, (_, evidence) in _TASKS.items():
            match = evidence.search(line)
            if match and not _NEGATED.search(line[:match.start()]):
                profile.tasks.setdefault(name, match[0])
    profile.years = _employment_years(text)
    profile.years_from_dates = profile.years is not None and not _TOTAL_YEARS.search(text)
    return profile


def compatibility(vacancy: Vacancy, cv: ResumeProfile) -> str:
    # Доля подтверждённых требований. Отсутствующие сведения остаются в знаменателе.
    ratings = []
    unverified_weight = 0
    reasons = []
    unknown = []
    conflicts = []

    roles = _roles(vacancy.title)
    shared = [r for r in roles if r in cv.roles]
    if roles and cv.roles:
        if shared:
            ratings.append((3, 1))
            reasons.append("Профиль: " + ROLES[shared[0]].button_label)
        else:
            # Роли смежны или названы иначе — не объявляем смену профессии несовместимостью.
            unverified_weight += 3
            unknown.append("точный профиль должности")
    elif roles:
        unverified_weight += 3
        unknown.append("роль в резюме")

    # На HH grade иногда получен из диапазона стажа. Не считаем один факт дважды.
    grade = extract_grade(vacancy.title) or (vacancy.grade if vacancy.source != "hh.ru" else None)
    if grade:
        levels = [cv.grades[r] for r in shared if r in cv.grades]
        if not levels:
            unverified_weight += 2
            unknown.append("грейд " + grade)
        elif grade in levels:
            ratings.append((2, 1))
            reasons.append("Уровень: " + grade)
        else:
            unverified_weight += 2
            unknown.append("грейд: вакансия " + grade + ", резюме " + "/".join(sorted(set(levels))))

    if vacancy.min_years:
        if cv.years is None:
            unverified_weight += 2
            unknown.append(f"стаж от {vacancy.min_years} лет")
        elif cv.years < vacancy.min_years:
            if cv.years_from_dates:
                unverified_weight += 2
                unknown.append(f"стаж от {vacancy.min_years} лет: по указанным периодам {cv.years} г.")
            else:
                conflicts.append(f"стаж: в резюме {cv.years} г., нужно от {vacancy.min_years}")
        else:
            ratings.append((2, 1))
            reasons.append(f"Общий стаж: {cv.years} г., требуется от {vacancy.min_years}")

    tasks = set(vacancy.tasks)
    if {"head_of_design", "head_of_engineering", "head_of_data", "head_of_product", "head_of_ai"}.intersection(roles):
        tasks.add("управление командой")
    if tasks:
        proven = sorted(tasks.intersection(cv.tasks))
        if proven:
            ratings.append((3, len(proven) / len(tasks)))
            reasons.append("Практика: " + ", ".join("«" + cv.tasks[t] + "»" for t in proven))
        else:
            unverified_weight += 3
        unknown.extend(sorted(tasks.difference(proven)))

    formats = work_formats(vacancy.work_format or "")
    if formats:
        common = sorted(set(formats).intersection(cv.formats))
        if common:
            ratings.append((1, 1))
            reasons.append("Формат: " + ", ".join(common))
        elif cv.formats:
            conflicts.append("формат: вакансия " + "/".join(formats) + ", резюме " + "/".join(cv.formats))
        else:
            unverified_weight += 1
            unknown.append("формат " + "/".join(formats))

    if formats and "удалённо" not in formats and vacancy.location and not work_formats(vacancy.location):
        city = vacancy.location.strip()
        if cv.city and cv.city.casefold() in [c.strip().casefold() for c in city.split(",")]:
            ratings.append((1, 1))
            reasons.append("Город: " + cv.city)
        else:
            unverified_weight += 1
            unknown.append("возможность работы в указанной локации")

    skills = set(vacancy.skills or extract_skills(vacancy.title))
    if skills:
        common = sorted(skills.intersection(cv.skills))
        if not ratings and not conflicts:
            reasons.append(match_line(vacancy, cv.skills))
        else:
            ratings.append((1, len(common) / len(skills)))
            reasons.append(f"Навыки: {len(common)} из {len(skills)}" + (" · " + ", ".join(common) if common else ""))
            unknown.extend(sorted(skills.difference(common)))

    bonus = sorted(set(vacancy.bonus_skills).intersection(cv.skills))
    if bonus:
        reasons.append("Плюс к профилю: " + ", ".join(bonus))

    beyond_title = bool(vacancy.min_years or vacancy.tasks or formats or skills.difference(extract_skills(vacancy.title)))
    if conflicts:
        header = "🎯 Есть расхождение: " + "; ".join(conflicts)
    elif beyond_title and len(ratings) >= 2 and any(w >= 2 for w, _ in ratings):
        score = round(100 * sum(w * value for w, value in ratings) / (unverified_weight + sum(w for w, _ in ratings)))
        header = f"🎯 Резюме подтверждает {score}% распознанных требований"
    else:
        header = "🎯 Для общей оценки мало данных"
    if unknown:
        reasons.append("Уточнить: " + ", ".join(unknown))
    return "\n".join([header] + reasons)
