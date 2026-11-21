import asyncio
from dataclasses import asdict
from pathlib import Path
from unittest.mock import AsyncMock

from bot.compatibility import compatibility, parse_profile, vacancy_tasks
from bot.database import VacancyDatabase
from bot.models import Vacancy
from bot.formatters import format_vacancy
from bot.parsers.hh import HHParser
from bot.resume import load_match_profile
from bot.skills_match import skill_requirements
from bot.subscriber_formatters import personal_pages


def job(**values):
    return Vacancy("hh.ru", "1", values.pop("title", "Senior Product Designer"), "Studio", "https://example.org", **values)


def test_task_evidence_changes_score_for_identical_skills():
    vacancy = job(skills=["Figma"], tasks=["управление командой"])
    title_and_skills = "Senior Product Designer\nFigma"
    listed = parse_profile(title_and_skills + "\nУправление командой")
    done = parse_profile(title_and_skills + "\nРуководил командой дизайнеров")
    assert listed.skills == done.skills
    a, b = (compatibility(vacancy, cv) for cv in (listed, done))
    assert (a, b) == (67, 100)
    assert not parse_profile("Не руководил командой").tasks


def test_overlapping_jobs_and_education():
    cv = parse_profile("Опыт работы\n01.2020 — 12.2022\nJan 2021 - Dec 2023\nОбразование\n01.2000 — 12.2015")
    assert cv.years == 4
    assert cv.years_from_dates
    assert compatibility(job(min_years=6), cv) == 0
    cv = parse_profile("Общий стаж: 2 года\nФормат работы: только удалённо")
    report = compatibility(job(min_years=3, work_format="Офис"), cv)
    assert report == 0


def test_unknowns_and_bonuses():
    cv = parse_profile("Python")
    report = compatibility(job(skills=["Python"]), cv)
    assert report == 17
    assert skill_requirements("Node.js. SQL будет плюсом. Excel не требуется.") == (["Node.js"], ["SQL"])
    assert not vacancy_tasks("Наставничество будет плюсом")


def test_hh_declared_years_and_format_are_independent_from_inferred_grade(tmp_path):
    vacancy = HHParser(None)._parse_item({
        "id": "1", "name": "Product Designer", "work_format": [{"id": "ON_SITE"}],
        "area": {"name": "Москва"}, "experience": {"id": "between3And6"},
        "snippet": {"responsibility": "Развитие дизайн-системы", "requirement": "Figma. HTML будет плюсом."},
    })
    db = VacancyDatabase(tmp_path / "test.db")
    db.save_role_cache({"designer": [vacancy]}, [])
    cached, = db.load_role_cache(["designer"])["designer"]
    cv = parse_profile("Product Designer\nОпыт работы — 5 лет\nСоздала дизайн-систему\nFigma HTML\nГород: Москва\nФормат работы: офис")
    [(text, _)] = personal_pages("Сегодня", [cached], cv)
    assert text.rsplit("\n", 1)[0].endswith(format_vacancy(cached, personal=True) + "\nСовместимость вакансии — 100%")


def test_existing_pdf_is_upgraded_once_and_concurrent_replacement_wins(tmp_path):
    async def scenario():
        db = VacancyDatabase(tmp_path / "test.db")
        db.save_resume(1, ["Figma"], file_name="resume.pdf", file_id="tg-old")
        old = db.get_resume(1)["resume_id"]
        bot = AsyncMock()
        async def download(file_id, destination, timeout):
            destination.write((Path(__file__).parent / "fixtures" / "designer-resume.pdf").read_bytes())
        bot.download.side_effect = download
        first = await load_match_profile(db, bot, 1)
        assert first == await load_match_profile(db, bot, 1)
        bot.download.assert_awaited_once()
        assert db.get_resume(1)["resume_id"] == old
        db.save_resume(1, ["SQL"], profile=asdict(parse_profile("SQL")))
        db.upgrade_resume(1, old, asdict(first))
        assert (await load_match_profile(db, bot, 1)).skills == ["SQL"]
        db.delete_resume(1)
        assert await load_match_profile(db, bot, 1) is None
    asyncio.run(scenario())

def test_title_alone_does_not_yield_overall_match_and_results_need_evidence():
    cv = parse_profile("Senior Python Developer")
    assert compatibility(job(title="Senior Python Developer"), cv) is None
    cv = parse_profile("Продуктовый дизайнер\nУвеличила конверсию с 4% до 7%")
    result = compatibility(job(tasks=["улучшение продуктовых метрик"]), cv)
    assert result == 75
    assert not parse_profile("Продуктовые метрики: конверсия, retention").tasks
