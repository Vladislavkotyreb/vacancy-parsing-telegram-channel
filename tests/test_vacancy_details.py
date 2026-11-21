import json

import pytest

from bot.database import VacancyDatabase, _vacancy_from_json
from bot.formatters import TELEGRAM_MAX_LENGTH, format_vacancy
from bot.parsers.getmatch import GetMatchParser
from bot.parsers.hh import HHParser
from bot.subscriber_formatters import personal_pages
from bot.vacancy_details import vacancy_details


def test_hh_to_private_digest_and_saved_overflow(tmp_path):
    vacancy = HHParser(None)._parse_item({
        "id": "1", "name": "Product Designer", "alternate_url": "https://hh.ru/vacancy/1",
        "snippet": {"responsibility": "Проектировать <highlighttext>B2C</highlighttext>-продукты.",
                    "requirement": "Опыт в R&D будет плюсом."},
        "contacts": {"email": "hiring@example.org"},
    })
    db = VacancyDatabase(tmp_path / "jobs.db")
    db.save_role_cache({"designer": [vacancy]}, [])
    [cached] = db.load_role_cache(["designer"])["designer"]
    db.replace_digest_overflow(11, "2026-11-21", [cached])
    [saved] = db.get_digest_overflow(11, "2026-11-21")
    [(text, batch)] = personal_pages("Сегодня", [saved], None)
    assert batch == [vacancy]
    assert "Проектировать B2C-продукты. Опыт в R&amp;D будет плюсом." in text
    assert '<a href="mailto:hiring@example.org">hiring@example.org</a>' in text
    assert "Открыть вакансию" in text
    assert "Главное" not in format_vacancy(saved)
    assert "hiring@" not in format_vacancy(saved)


def test_getmatch_application_link_and_pagination():
    raw = {"id": 1, "position": "Designer", "url": "/vacancies/1",
           "offer_description": "<p>Проектировать продукт для логистики.</p>"
                                "<p>Портфолио с кейсами обязательно.</p>"
                                '<p><a href="https://t.me/design_hiring">Откликнуться</a></p>'}
    jobs = [GetMatchParser()._parse_item(dict(raw, id=i)) for i in range(1, 41)]
    pages = personal_pages("Вакансии", jobs, None)
    assert len(pages) > 1
    assert [job for _, batch in pages for job in batch] == jobs
    for text, batch in pages:
        assert len(text) <= TELEGRAM_MAX_LENGTH
        assert text.count('<a href="https://t.me/design_hiring">@design_hiring</a>') == len(batch)


@pytest.mark.parametrize("description", [
    "Подписывайтесь на наш канал https://t.me/company_blog",
    "Пишите в службу поддержки support@example.org",
    "Для отклика: https://t.me/company_feed/123",
    "Откликнуться: https://evil.example/t.me/some_user",
    "Для отклика: https://t.me/career_helper_bot",
    "Не писать @someone_here",
    '<a href="https://example.org/news">@some_user</a>',
    "Контакты компании. Подписывайтесь на @company_feed",
    "Contact with candidates comes from @tebra.example or via our applicant tracking system.",
    "Apply to jobs using the website. For an accommodation during the application process email hr@example.org",
    "To exercise your data protection rights, contact us at privacy@example.org.",
    "Отклик: письма отправляем с домена @tebra.example",
])
def test_no_unrelated_or_nonpersonal_contact(description):
    assert vacancy_details(description)[1] is None


def test_only_published_fields_and_legacy_data():
    assert vacancy_details("Отклик:\n@design_hiring")[1] == "@design_hiring"
    assert vacancy_details(apply_to="mailto:jobs@example.org")[1] == "jobs@example.org"
    assert vacancy_details(contacts={"phones": [{"country": "+7", "city": "999", "number": "123-45-67"}]})[1] == "+79991234567"
    assert vacancy_details(tags=[{"title": "B2C"}, {"title": "Figma"}]) == ("Навыки в вакансии — B2C, Figma", None)
    vacancy = _vacancy_from_json(json.dumps(dict(source="hh.ru", external_id="1", title="Designer", company="Co", url="https://hh.ru")))
    assert "Главное" not in format_vacancy(vacancy, personal=True)
    assert "Контакт" not in format_vacancy(vacancy, personal=True)


def test_experience_heading_yields_to_actual_minimum():
    summary, contact = vacancy_details("Чем будешь заниматься\n— Проектировать интерфейсы.\n"
                                       "Опыт, который хотим видеть\n— 3+ года в продуктовом дизайне.\n"
                                       "Продукт: @demo_company\nПисать сюда @demo_hiring")
    assert summary == "Проектировать интерфейсы. 3+ года в продуктовом дизайне."
    assert contact == "@demo_hiring"
