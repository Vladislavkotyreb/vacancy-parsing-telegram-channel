from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.chat_main import upload_resume
from bot.database import VacancyDatabase
from bot.digest_more import send_overflow
from bot.formatters import format_vacancy
from bot.models import Vacancy
from bot.parsers.habr_career import parse_item
from bot.resume import parse_resume
from bot.skills_match import match_line
from bot.subscriber_formatters import personal_pages


def test_tokens_aliases_and_empty_documents():
    assert parse_resume("cv.TXT", b"Postgres, JS; Node.js; PostgreSQL") == [
        "JavaScript", "Node.js", "PostgreSQL"
    ]
    with pytest.raises(ValueError):
        parse_resume("cv.txt", b"NoSQL, JavaBeans and HTMLish")
    with pytest.raises(ValueError):
        parse_resume("cv.txt", b"\xff")


def test_personal_scores_from_cached_source_tags(tmp_path):
    db = VacancyDatabase(tmp_path / "test.db")
    job = parse_item({"id": 3, "title": "Designer", "skills": [
        {"title": "Figma"}, {"title": "SQL"}, {"title": "HTML"}]})
    db.save_role_cache({"design": [job]}, [])
    db.enable_resume_test(1)
    db.enable_resume_test(2)
    db.save_resume(1, ["Figma", "SQL"])
    db.save_resume(2, ["HTML"])
    cached, = db.load_role_cache(["design"])["design"]
    for user, expected in ((1, "67%"), (2, "33%")):
        [(text, batch)] = personal_pages("Сегодня", [cached], db.resume_skills(user))
        assert batch == [cached]
        assert expected in text
        assert "Не найдены в резюме" in text
    db.delete_resume(1)
    assert "/resume" in match_line(cached, db.resume_skills(1))
    assert db.resume_skills(2) == ["HTML"]
    assert "Совпадение" not in format_vacancy(cached)


def test_old_rows_without_skill_data():
    old = Vacancy("old", "1", "Разработчик", "А", "https://example.org")
    assert "%" not in match_line(old, ["SQL"])
    old.title = "Python developer"
    assert "0% (0 из 1)" in match_line(old, ["SQL"])


def test_upload_and_overflow(tmp_path):
    import asyncio

    async def scenario():
        db = VacancyDatabase(Path(tmp_path) / "test.db")
        db.enable_resume_test(1)
        doc = SimpleNamespace(file_name="cv.txt", file_size=8, file_id="file-1")
        message = SimpleNamespace(chat=SimpleNamespace(id=1), document=doc, from_user=SimpleNamespace(username="test"), answer=AsyncMock())
        bot = AsyncMock()
        async def download(document, destination):
            destination.write(b"Figma, SQL")
        bot.download.side_effect = download
        await upload_resume(message, db, bot)
        assert db.resume_skills(1) == ["Figma", "SQL"]
        doc.file_name = "bad.doc"
        await upload_resume(message, db, bot)
        assert db.resume_skills(1) == ["Figma", "SQL"]
        job = Vacancy("x", "1", "Designer", "A", "url", skills=["Figma", "HTML"])
        await send_overflow(bot, db, 1, [job])
        assert "50% (1 из 2)" in bot.send_message.await_args.kwargs["text"]
        assert db.is_sent_to_subscriber(1, job.uid)

    asyncio.run(scenario())


def test_legacy_resume_migration(tmp_path):
    import sqlite3

    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE resume_profiles(user_id INTEGER PRIMARY KEY, skills_json TEXT NOT NULL)")
        conn.execute("""INSERT INTO resume_profiles VALUES (1, '["SQL"]')""")
    first = VacancyDatabase(path).get_resume(1)
    assert first["skills"] == ["SQL"]
    assert first["resume_id"] and first["file_id"] is None
    assert VacancyDatabase(path).get_resume(1) == first


def test_resume_management_buttons(tmp_path):
    import asyncio
    from bot.chat_main import cmd_resume, resume_action

    async def scenario():
        db = VacancyDatabase(tmp_path / "test.db")
        msg = SimpleNamespace(chat=SimpleNamespace(id=42), from_user=SimpleNamespace(id=42, username="designer"),
                              answer=AsyncMock(), answer_document=AsyncMock(), edit_reply_markup=AsyncMock())
        bot = AsyncMock()
        async def upload(name, file_id, contents):
            msg.document = SimpleNamespace(file_name=name, file_size=len(contents), file_id=file_id)
            async def download(doc, destination):
                destination.write(contents)
            bot.download.side_effect = download
            await upload_resume(msg, db, bot)

        db.enable_resume_test(42)
        await upload("cv.txt", "tg-1", b"Figma")
        first = db.get_resume(42)
        assert first["username"] == "designer" and first["file_id"] == "tg-1"
        assert "Мои резюме" in str(msg.answer.await_args.kwargs["reply_markup"])
        await cmd_resume(msg, db)
        card = msg.answer_document.await_args
        assert card.args == ("tg-1",)
        assert "cv.txt" in card.kwargs["caption"] and "Figma" in card.kwargs["caption"]
        delete, replace = card.kwargs["reply_markup"].inline_keyboard[0]

        async def press(button):
            cb = SimpleNamespace(data=button.callback_data, from_user=msg.from_user, message=msg, answer=AsyncMock())
            await resume_action(cb, db)
            return cb

        await press(replace)
        assert "скрепку" in msg.answer.await_args.args[0]
        await upload("empty.txt", "tg-bad", b"")
        assert db.get_resume(42) == first
        await upload("new.txt", "tg-2", b"SQL")
        second = db.get_resume(42)
        assert second["resume_id"] != first["resume_id"] and second["skills"] == ["SQL"]
        stale = await press(delete)
        assert stale.answer.await_args.kwargs["show_alert"]
        assert db.get_resume(42) == second
        await cmd_resume(msg, db)
        delete = msg.answer_document.await_args.kwargs["reply_markup"].inline_keyboard[0][0]
        msg.chat.id = msg.from_user.id = 28
        await press(delete)
        assert db.get_resume(42) == second
        msg.chat.id = msg.from_user.id = 42
        await press(delete)
        assert db.get_resume(42) is None
        assert "Добавить резюме" in str(msg.answer.await_args.kwargs["reply_markup"])

    asyncio.run(scenario())
