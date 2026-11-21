"""Обновление клавиатур при переходе с версии без общей кнопки резюме."""
from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.methods import SendDocument, SendMessage
from aiogram.types import Chat, Document, Message, User

from bot.chat_main import router
from bot.database import VacancyDatabase
from bot.menu import BTN_ADD_RESUME, BTN_MY_RESUMES, reply_keyboard
from bot.resume_menu import refresh_existing_chats, refresh_resume_menu


def test_existing_chats_receive_full_keyboard_once(tmp_path):
    path = tmp_path / "bot.db"
    db = VacancyDatabase(path)
    db.set_subscriber_roles(10, ["backend_go"])
    db.record_activity(20, None, None, None, day="2026-11-01")
    db.save_resume(30, ["SQL"])
    db.set_subscriber_roles(40, ["backend_go"])
    db.deactivate_subscriber(40)
    # Состояние старой версии перед выкаткой.
    with sqlite3.connect(path) as conn:
        conn.execute("DROP TABLE resume_menu_pending")
    db = VacancyDatabase(path)

    async def scenario():
        bot = AsyncMock()
        with patch("bot.resume_menu.asyncio.sleep", new=AsyncMock()):
            await refresh_existing_chats(bot, db)
            await refresh_existing_chats(bot, VacancyDatabase(path))
        calls = bot.send_message.await_args_list
        assert [c.args[0] for c in calls] == [10, 20, 30]
        assert all(c.kwargs["disable_notification"] for c in calls)
        assert [c.kwargs["reply_markup"] for c in calls] == [
            reply_keyboard(False), reply_keyboard(False), reply_keyboard(True)]
        assert db.get_subscriber_roles(10) == ["backend_go"]
        assert db.get_subscriber(20) is None
        assert db.needs_resume_menu(40)
        await refresh_resume_menu(bot, db, 40, proactive=False)
        assert bot.send_message.await_args.args[0] == 40
        assert db.get_subscriber(40) is None

    asyncio.run(scenario())


def test_blocked_chat_and_rate_limit_do_not_prevent_other_keyboards(tmp_path):
    db = VacancyDatabase(tmp_path / "retry.db")
    with sqlite3.connect(db.db_path) as conn:
        conn.executemany("INSERT INTO resume_menu_pending VALUES (?)", [(10,), (20,), (30,)])
    calls = []
    async def send(user_id, text, **kwargs):
        calls.append(user_id)
        method = SendMessage(chat_id=user_id, text=text)
        if user_id == 10:
            raise TelegramForbiddenError(method=method, message="blocked by the user")
        if user_id == 20 and calls.count(20) == 1:
            raise TelegramRetryAfter(method=method, message="retry", retry_after=1)

    async def scenario():
        bot = AsyncMock()
        bot.send_message.side_effect = send
        with patch("bot.resume_menu.asyncio.sleep", new=AsyncMock()):
            await refresh_existing_chats(bot, db)
        assert calls == [10, 20, 30, 20]
        assert db.pending_resume_menus() == []
    asyncio.run(scenario())


def test_user_without_subscription_can_attach_and_open_pdf(tmp_path):
    async def scenario():
        db = VacancyDatabase(tmp_path / "bot.db")
        transport = AsyncMock()
        bot = Bot(token="1:test", session=transport)
        chat = Chat(id=120034, type="private")
        user = User(id=chat.id, first_name="Тест", is_bot=False)
        async def submit(**payload):
            transport.reset_mock()
            message = Message(message_id=1, date=datetime.now(timezone.utc), chat=chat,
                              from_user=user, **payload).as_(bot)
            await router.propagate_event("message", message, db=db, bot=bot)
            transport.assert_awaited_once()
            return transport.await_args.args[1]

        async def download(document, destination):
            destination.write((Path(__file__).parent / "fixtures/designer-resume.pdf").read_bytes())

        prompt = await submit(text=BTN_ADD_RESUME)
        assert isinstance(prompt, SendMessage) and prompt.reply_markup == reply_keyboard(False)
        with patch.object(bot, "download", side_effect=download):
            saved = await submit(document=Document(file_id="attached-pdf", file_unique_id="unique",
                                                   file_name="Моё резюме.pdf"))
        assert saved.reply_markup == reply_keyboard(True)
        card = await submit(text=BTN_MY_RESUMES)
        assert isinstance(card, SendDocument) and card.document == "attached-pdf"
        assert "Figma" in card.caption
        assert [b.text for b in card.reply_markup.inline_keyboard[0]] == ["Удалить", "Залить другое"]
        assert db.get_subscriber(chat.id) is None
    asyncio.run(scenario())
