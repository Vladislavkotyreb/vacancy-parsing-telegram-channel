"""Owner-only, temporary Telegram demo. Never submits applications or calls an LLM."""
from __future__ import annotations

import asyncio
import io
import re
import secrets
import time
import zipfile
from dataclasses import dataclass, field
from typing import Optional
from xml.etree import ElementTree

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.menu import BTN_CHOOSE_ROLES, BTN_CHOOSE_ROLES_AGAIN, BTN_MY_SUBSCRIPTION, BTN_NOW, BTN_UNSUBSCRIBE

TTL_SECONDS = 30 * 60
TEXT_LIMIT = 100 * 1024
DOCX_LIMIT = 2 * 1024 * 1024
PREFIX = "apd:"
ROLES = {"design": "Продуктовый дизайнер", "front": "Frontend-разработчик", "python": "Python-разработчик"}
JOBS = {
    "d1": ("design", "Ozon", "Продуктовый дизайнер", "Каталог и оформление заказа"),
    "d2": ("design", "Avito", "Product Designer", "Поиск и выбор товаров"),
    "d3": ("design", "Яндекс", "UX-дизайнер", "Прототипы и пользовательские сценарии"),
    "f1": ("front", "Ozon", "Frontend-разработчик", "Интерфейсы каталога"),
    "f2": ("front", "Avito", "React-разработчик", "Развитие пользовательских интерфейсов"),
    "f3": ("front", "Яндекс", "Frontend-разработчик", "Доступность и производительность интерфейсов"),
    "p1": ("python", "Ozon", "Python-разработчик", "Сервисы обработки заказов"),
    "p2": ("python", "Avito", "Backend-разработчик", "API и работа с данными"),
    "p3": ("python", "Яндекс", "Python-разработчик", "Сервисы автоматизации"),
}
EXAMPLES = {
    "design": "Продуктовый дизайнер. 4 года в B2C и e-commerce. Работал с каталогом и корзиной. Figma, прототипы, юзабилити-тестирования.",
    "front": "Frontend-разработчик. 3 года опыта. JavaScript, TypeScript, React. Разрабатывал интерфейсы каталога и личного кабинета.",
    "python": "Python-разработчик. 3 года опыта. Python, SQL, PostgreSQL. Разрабатывал API и сервисы обработки данных.",
}
MENU_TEXTS = {BTN_NOW, BTN_MY_SUBSCRIPTION, BTN_UNSUBSCRIBE, BTN_CHOOSE_ROLES, BTN_CHOOSE_ROLES_AGAIN}


def extract_profile(text: str) -> dict:
    """Keep a bounded verbatim fragment; keyword suggestion is explicitly not AI."""
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) < 20:
        raise ValueError("Пришлите хотя бы пару предложений об опыте и навыках.")
    lower = cleaned.lower()
    role = "python" if "python" in lower else "front" if any(word in lower for word in ("react", "frontend", "javascript", "фронтенд")) else "design"
    return {"role": role, "facts": cleaned[:700], "truncated": len(cleaned) > 700}


def extract_document(data: bytes, filename: str) -> str:
    if filename.lower().endswith(".txt"):
        if len(data) > TEXT_LIMIT:
            raise ValueError("TXT должен быть не больше 100 КБ.")
        return data.decode("utf-8-sig")
    if not filename.lower().endswith(".docx"):
        raise ValueError("В этом тесте доступны текст, TXT и DOCX. Из PDF скопируйте текст резюме.")
    if len(data) > DOCX_LIMIT:
        raise ValueError("DOCX должен быть не больше 2 МБ.")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries) > 1000 or sum(item.file_size for item in entries) > 8 * 1024 * 1024:
            raise ValueError("DOCX слишком большой после распаковки. Пришлите текст.")
        info = archive.getinfo("word/document.xml")
        if info.file_size > 1024 * 1024:
            raise ValueError("В DOCX слишком много текста. Пришлите короткую версию.")
        xml = archive.read(info)
    declarations = xml.replace(b"\x00", b"").upper()
    if b"<!DOCTYPE" in declarations or b"<!ENTITY" in declarations:
        raise ValueError("Не удалось безопасно прочитать DOCX. Пришлите текст.")
    root = ElementTree.fromstring(xml)
    return " ".join(node.text or "" for node in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"))


class LimitedBuffer(io.BytesIO):
    def __init__(self, limit: int):
        super().__init__()
        self.limit = limit

    def write(self, data):
        if self.tell() + len(data) > self.limit:
            raise ValueError("Файл превышает допустимый размер.")
        return super().write(data)


@dataclass
class DemoSession:
    nonce: str = field(default_factory=lambda: secrets.token_hex(4))
    expires: float = field(default_factory=lambda: time.monotonic() + TTL_SECONDS)
    revision: int = 0
    stage: str = "choose"
    role: str = ""
    profile: Optional[dict] = None
    confirmed: bool = False
    pending: list[str] = field(default_factory=list)
    selected: set[str] = field(default_factory=set)
    drafts: dict[str, str] = field(default_factory=dict)
    sent: set[str] = field(default_factory=set)
    editing: str = ""


class ApplicationDemo:
    def __init__(self, owner_id: int):
        if owner_id <= 0:
            raise ValueError("A positive owner Telegram ID is required")
        self.owner_id = owner_id
        self.session: Optional[DemoSession] = None
        self.lock = asyncio.Lock()
        self.expiry_handle = None

    def authorized(self, event) -> bool:
        message = getattr(event, "message", None) or event
        chat = getattr(message, "chat", None)
        user = getattr(event, "from_user", None)
        return bool(user and user.id == self.owner_id and chat and chat.type == "private" and chat.id == self.owner_id)

    def active(self) -> Optional[DemoSession]:
        if self.session and self.session.expires <= time.monotonic():
            self.clear()
        return self.session

    def clear(self):
        self.session = None
        if self.expiry_handle:
            self.expiry_handle.cancel()
            self.expiry_handle = None

    async def close(self, **kwargs):
        self.clear()

    @staticmethod
    def entry(message) -> bool:
        parts = (message.text or "").split()
        command = parts[0].split("@")[0] if parts else ""
        return command == "/try_apply" or (command == "/start" and parts[1:] == ["apply_test"])

    @staticmethod
    def exit_command(message) -> bool:
        return (message.text or "").split("@")[0].strip() == "/exit_test"

    def accepts_input(self, message) -> bool:
        session = self.active()
        text = message.text or ""
        return bool(session and session.stage in {"resume", "edit"} and not text.startswith("/") and text not in MENU_TEXTS and (text or message.document))

    async def show(self, message, text: str, buttons=()):
        session = self.active()
        if not session:
            return
        session.revision += 1
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=label, callback_data=f"{PREFIX}{session.nonce}:{session.revision}:{action}:{value}")
        ] for label, action, value in buttons]) if buttons else None
        await message.answer(text, reply_markup=keyboard, parse_mode=None)

    async def start(self, message):
        if not self.authorized(message):
            return
        async with self.lock:
            self.clear()
            self.session = DemoSession()
            self.expiry_handle = asyncio.get_running_loop().call_later(TTL_SECONDS, self.clear)
            await self.show(message, "Личный тест. Реальные отклики не отправляются. Профиль хранится временно: 30 минут, до /exit_test или перезапуска бота.\n\nВакансии — примеры. Разбор резюме и письма тестовые, без ИИ.\n\nКак получать вакансии?", [("По должности", "mode", "role"), ("По моему резюме", "mode", "resume")])

    async def exit(self, message):
        if not self.authorized(message):
            return
        async with self.lock:
            self.clear()
            await message.answer("Тест завершён. Временный профиль, письма и история удалены. Подписка на вакансии не менялась.", parse_mode=None)

    async def roles(self, message):
        self.session.stage = "roles"
        await self.show(message, "Выберите должность для тестовой подборки.", [(label, "role", key) for key, label in ROLES.items()])

    async def jobs(self, message):
        session = self.session
        session.stage = "jobs"
        items = [key for key, job in JOBS.items() if job[0] == session.role]
        text = "HH · тестовая подборка\n" + ROLES[session.role] + "\n\n" + "\n\n".join(f"{JOBS[key][1]} — {JOBS[key][2]}\n{JOBS[key][3]}" + ("\n✓ Тестовый отклик отправлен" if key in session.sent else "") for key in items)
        buttons = [(f"Откликнуться · {JOBS[key][1]}", "apply", key) for key in items if key not in session.sent]
        if buttons:
            buttons.append(("Откликнуться на все выбранные", "batch", ""))
        buttons.append(("Другая должность", "roles", ""))
        await self.show(message, text, buttons)

    async def ask_resume(self, message):
        self.session.stage = "resume"
        await self.show(message, "Для персонального письма нужен ваш опыт. Пришлите текст резюме, TXT до 100 КБ или DOCX до 2 МБ. PDF в этом тесте не читается: скопируйте из него текст.\n\nМожно пройти тест на вымышленном примере.", [("Использовать пример", "example", "")])

    async def profile(self, message, text):
        session = self.session
        session.profile = extract_profile(text)
        session.confirmed = False
        session.stage = "profile"
        suggestion = ROLES[session.profile["role"]]
        await self.show(message, f"Тестовый разбор без ИИ.\nПредполагаемая должность по ключевым словам: {suggestion}.\n\nФрагмент резюме для письма:\n{session.profile['facts']}" + ("\n\nДлинный текст сокращён до 700 символов." if session.profile["truncated"] else "") + "\n\nИспользовать эти сведения?", [("Подтвердить профиль", "confirm", ""), ("Прислать другой текст", "resume", "")])

    async def review(self, message):
        session = self.session
        session.stage = "review"
        session.pending = [key for key in session.pending if key not in session.sent]
        for key in session.pending:
            job = JOBS[key]
            if key not in session.drafts:
                session.drafts[key] = f"Здравствуйте, команда {job[1]}!\n\nМеня заинтересовала позиция «{job[2]}» и задача «{job[3]}».\n\nИз моего резюме: {session.profile['facts']}\n\nБуду рад обсудить позицию и рассказать подробнее о своём опыте."
            await message.answer(f"Тестовый черновик — без ИИ\n{job[1]} · {job[2]}\n\n{session.drafts[key]}", parse_mode=None)
        buttons = [(f"Изменить письмо · {JOBS[key][1]}", "edit", key) for key in session.pending]
        if session.pending:
            buttons.append((f"Подтвердить тестовую отправку · {len(session.pending)}", "send", ""))
        buttons.append(("Назад к вакансиям", "jobs", ""))
        await self.show(message, f"Проверьте письма выше. Будет имитирована отправка {len(session.pending)} откликов. На HH ничего не уйдёт.", buttons)

    async def batch(self, message):
        session = self.session
        session.stage = "batch"
        available = [key for key, job in JOBS.items() if job[0] == session.role and key not in session.sent]
        session.selected.intersection_update(available)
        buttons = [(f"{'✓' if key in session.selected else '○'} {JOBS[key][1]} · {JOBS[key][2]}", "toggle", key) for key in available]
        if session.selected:
            buttons.append((f"Подготовить письма · {len(session.selected)}", "prepare", ""))
        buttons.append(("Назад", "jobs", ""))
        await self.show(message, "Выберите вакансии для тестовых откликов. Уже отправленные исключены.", buttons)

    async def callback(self, callback):
        if not self.authorized(callback):
            return
        async with self.lock:
            session = self.active()
            parts = (callback.data or "").split(":", 4)
            if not session or len(parts) != 5 or parts[0] != "apd" or parts[1] != session.nonce or parts[2] != str(session.revision):
                await callback.answer("Кнопка устарела. Используйте последний экран или /try_apply.", show_alert=True)
                return
            _, _, _, action, value = parts
            await callback.answer()
            message = callback.message
            if action == "mode":
                await (self.roles(message) if value == "role" else self.ask_resume(message))
            elif action == "roles":
                session.pending = []
                await self.roles(message)
            elif action == "role" and value in ROLES:
                session.role = value
                await self.jobs(message)
            elif action == "jobs":
                session.pending = []
                await self.jobs(message)
            elif action in {"resume", "example"}:
                if action == "example":
                    await self.profile(message, EXAMPLES[session.role or "design"])
                else:
                    await self.ask_resume(message)
            elif action == "confirm" and session.stage == "profile":
                session.confirmed = True
                session.role = session.role or session.profile["role"]
                if session.pending:
                    await self.review(message)
                else:
                    await self.jobs(message)
            elif action == "apply" and value in JOBS and JOBS[value][0] == session.role and value not in session.sent:
                session.pending = [value]
                await (self.review(message) if session.confirmed else self.ask_resume(message))
            elif action == "batch":
                session.selected = {key for key, job in JOBS.items() if job[0] == session.role and key not in session.sent}
                await self.batch(message)
            elif action == "toggle" and session.stage == "batch" and value in JOBS and JOBS[value][0] == session.role and value not in session.sent:
                session.selected.symmetric_difference_update({value})
                await self.batch(message)
            elif action == "prepare" and session.stage == "batch":
                session.pending = sorted(session.selected - session.sent)
                await (self.review(message) if session.confirmed else self.ask_resume(message))
            elif action == "edit" and session.stage == "review" and value in session.pending:
                session.stage, session.editing = "edit", value
                await self.show(message, f"Пришлите новый текст письма для {JOBS[value][1]} (до 1600 символов). Он заменит черновик; отправка потребует нового подтверждения.", [("Оставить прежнее письмо", "cancel", "")])
            elif action == "cancel" and session.stage == "edit":
                await self.review(message)
            elif action == "send" and session.stage == "review" and session.confirmed:
                count = len(set(session.pending) - session.sent)
                session.sent.update(session.pending)
                session.pending = []
                session.stage = "done"
                await self.show(message, f"✓ Тест завершён: имитирована отправка {count} откликов. Реальные отклики не отправлялись. Повторные отправки исключены в этой сессии.", [("К вакансиям", "jobs", "")])

    async def input(self, message):
        if not self.authorized(message):
            return
        async with self.lock:
            session = self.active()
            if not session or not self.accepts_input(message):
                return
            if session.stage == "edit":
                text = (message.text or "").strip()
                if not text or len(text) > 1600:
                    await message.answer("Пришлите письмо текстом: от 1 до 1600 символов.", parse_mode=None)
                    return
                session.drafts[session.editing] = text
                await self.review(message)
                return
            try:
                text = message.text
                if message.document:
                    doc = message.document
                    name = doc.file_name or ""
                    if not name.lower().endswith((".txt", ".docx")):
                        raise ValueError("Поддерживаются TXT и DOCX. Для PDF пришлите текст резюме.")
                    limit = TEXT_LIMIT if name.lower().endswith(".txt") else DOCX_LIMIT
                    if not doc.file_size or doc.file_size > limit:
                        raise ValueError("Файл слишком большой: максимум 100 КБ для TXT или 2 МБ для DOCX.")
                    with LimitedBuffer(limit) as buffer:
                        await message.bot.download(doc, destination=buffer, timeout=20)
                        text = extract_document(buffer.getvalue(), name)
                if not text or len(text.encode("utf-8")) > TEXT_LIMIT:
                    raise ValueError("Пришлите текст резюме до 100 КБ.")
                if self.active() is not session:
                    await message.answer("Время теста истекло. Начните заново: /try_apply.", parse_mode=None)
                    return
                await self.profile(message, text)
            except (ValueError, UnicodeError) as exc:
                await message.answer(str(exc) if isinstance(exc, ValueError) and not isinstance(exc, UnicodeError) else "Не удалось прочитать кодировку. Пришлите текст или TXT в UTF-8.", parse_mode=None)
            except (zipfile.BadZipFile, KeyError, ElementTree.ParseError, RuntimeError, OSError, asyncio.TimeoutError, TelegramAPIError):
                await message.answer("Не удалось прочитать файл. Пришлите текст резюме сообщением.", parse_mode=None)


def create_demo_router(owner_id: int) -> Router:
    demo = ApplicationDemo(owner_id)
    router = Router(name="private_application_demo")
    router.message.filter(demo.authorized)
    router.callback_query.filter(demo.authorized)
    router.message.register(demo.start, demo.entry)
    router.message.register(demo.exit, demo.exit_command)
    router.message.register(demo.input, demo.accepts_input)
    router.callback_query.register(demo.callback, F.data.startswith(PREFIX))
    router.shutdown.register(demo.close)
    return router
