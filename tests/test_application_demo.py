import asyncio
import io
import unittest
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.dispatcher.event.bases import UNHANDLED

from bot.application_demo import (
    ApplicationDemo, DOCX_LIMIT, TEXT_LIMIT, create_demo_router,
    extract_document, extract_profile,
)
from bot.menu import BTN_NOW


class DemoTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.demo = ApplicationDemo(123)
        self.replies = []

        async def capture(text, **kwargs):
            self.replies.append((text, kwargs.get("reply_markup")))

        self.message = SimpleNamespace(
            from_user=SimpleNamespace(id=123), chat=SimpleNamespace(id=123, type="private"),
            text="/try_apply", document=None, answer=AsyncMock(side_effect=capture),
            bot=SimpleNamespace(download=AsyncMock()),
        )

    async def asyncTearDown(self):
        await self.demo.close()

    def callback(self, data):
        return SimpleNamespace(from_user=SimpleNamespace(id=123), message=self.message, data=data, answer=AsyncMock())

    def data(self, action, value=""):
        keyboard = self.replies[-1][1]
        return next(button.callback_data for row in keyboard.inline_keyboard for button in row if button.callback_data.endswith(f":{action}:{value}"))

    async def click(self, action, value=""):
        await self.demo.callback(self.callback(self.data(action, value)))

    async def begin_role(self):
        await self.demo.start(self.message)
        await self.click("mode", "role")
        await self.click("role", "python")

    async def ready_letter(self):
        await self.begin_role()
        await self.click("apply", "p1")
        await self.click("example")
        await self.click("confirm")

    async def test_role_route_delays_resume_and_requires_profile_confirmation(self):
        await self.begin_role()
        self.assertIsNone(self.demo.session.profile)
        self.assertEqual(self.demo.session.stage, "jobs")
        await self.click("apply", "p1")
        self.assertEqual(self.demo.session.stage, "resume")
        await self.click("example")
        self.assertFalse(self.demo.session.confirmed)
        self.assertFalse(self.demo.session.drafts)
        forged = f"apd:{self.demo.session.nonce}:{self.demo.session.revision}:send:"
        await self.demo.callback(self.callback(forged))
        self.assertFalse(self.demo.session.sent)
        await self.click("confirm")
        self.assertEqual(self.demo.session.stage, "review")
        self.assertIn("Python, SQL, PostgreSQL", self.demo.session.drafts["p1"])

    async def test_edit_invalidates_confirmation_and_concurrent_send_is_deduplicated(self):
        await self.ready_letter()
        old_send = self.data("send")
        await self.click("edit", "p1")
        self.message.text = "Здравствуйте! Это мой проверенный и отредактированный текст."
        await self.demo.input(self.message)
        self.assertEqual(self.demo.session.drafts["p1"], self.message.text)
        stale = self.callback(old_send)
        await self.demo.callback(stale)
        self.assertTrue(stale.answer.call_args.kwargs["show_alert"])
        self.assertFalse(self.demo.session.sent)
        send = self.data("send")
        await asyncio.gather(self.demo.callback(self.callback(send)), self.demo.callback(self.callback(send)))
        self.assertEqual(self.demo.session.sent, {"p1"})
        results = [text for text, _ in self.replies if text.startswith("✓ Тест завершён")]
        self.assertEqual(len(results), 1)

    async def test_batch_selection_confirmation_and_sent_exclusion(self):
        await self.begin_role()
        await self.click("batch")
        stale_prepare = self.data("prepare")
        await self.click("toggle", "p3")
        await self.demo.callback(self.callback(stale_prepare))
        self.assertEqual(self.demo.session.stage, "batch")
        await self.click("prepare")
        await self.click("example")
        await self.click("confirm")
        self.assertEqual(self.demo.session.pending, ["p1", "p2"])
        self.assertIn("2 откликов", self.replies[-1][0])
        await self.click("send")
        await self.click("jobs")
        await self.click("batch")
        self.assertEqual(self.demo.session.selected, {"p3"})

    async def test_resume_confirmation_opens_results_without_reselecting_role(self):
        self.message.text = "/start apply_test"
        self.assertTrue(self.demo.entry(self.message))
        await self.demo.start(self.message)
        await self.click("mode", "resume")
        self.message.text = "Frontend-разработчик. React и TypeScript. Разрабатывал интерфейсы каталога."
        await self.demo.input(self.message)
        self.assertEqual(self.demo.session.profile["role"], "front")
        self.assertEqual(self.demo.session.stage, "profile")
        await self.click("confirm")
        self.assertEqual(self.demo.session.role, "front")
        self.assertEqual(self.demo.session.stage, "jobs")
        self.assertIn("React-разработчик", self.replies[-1][0])
        self.assertTrue(self.data("roles"))

    async def test_owner_and_private_chat_isolation_at_router_boundary(self):
        router = create_demo_router(123)
        try:
            for user_id, chat_id, chat_type in [(999, 999, "private"), (123, -100, "supergroup"), (123, 999, "private")]:
                self.message.from_user.id = user_id
                self.message.chat.id, self.message.chat.type = chat_id, chat_type
                result = await router.propagate_event("message", self.message)
                self.assertIs(result, UNHANDLED)
            self.assertFalse(self.replies)
            self.message.from_user.id = self.message.chat.id = 123
            self.message.chat.type = "private"
            await router.propagate_event("message", self.message)
            self.assertIn("Личный тест", self.replies[-1][0])
            self.message.text = "/start"
            self.assertIs(await router.propagate_event("message", self.message), UNHANDLED)
        finally:
            await router.shutdown.trigger()

    async def test_other_commands_pass_and_exit_clears_data_and_invalidates_callbacks(self):
        await self.begin_role()
        await self.click("apply", "p1")
        stale_data = self.data("example")
        for text in ("/vacancies", "/start", BTN_NOW):
            self.message.text = text
            self.assertFalse(self.demo.accepts_input(self.message))
        await self.demo.exit(self.message)
        self.assertIsNone(self.demo.session)
        self.assertIsNone(self.demo.expiry_handle)
        stale = self.callback(stale_data)
        await self.demo.callback(stale)
        self.assertTrue(stale.answer.call_args.kwargs["show_alert"])

    async def test_new_session_rejects_old_nonce_and_expiry_clears_without_input(self):
        await self.demo.start(self.message)
        old = self.data("mode", "role")
        await self.demo.start(self.message)
        stale = self.callback(old)
        await self.demo.callback(stale)
        self.assertEqual(self.demo.session.stage, "choose")
        with patch("bot.application_demo.TTL_SECONDS", 0.01):
            await self.demo.start(self.message)
            await asyncio.sleep(0.03)
        self.assertIsNone(self.demo.session)

    async def test_document_download_is_bounded_even_if_metadata_is_wrong(self):
        await self.begin_role()
        await self.click("apply", "p1")
        self.message.text = None
        self.message.document = SimpleNamespace(file_name="resume.txt", file_size=10)

        async def oversized(doc, destination, **kwargs):
            destination.write(b"x" * (TEXT_LIMIT + 1))

        self.message.bot.download.side_effect = oversized
        await self.demo.input(self.message)
        self.assertIsNone(self.demo.session.profile)
        self.assertIn("превышает", self.replies[-1][0])

    async def test_owner_callback_does_not_accept_other_users(self):
        await self.demo.start(self.message)
        callback = self.callback(self.data("mode", "role"))
        callback.from_user.id = 999
        await self.demo.callback(callback)
        self.assertEqual(self.demo.session.stage, "choose")
        callback.answer.assert_not_awaited()

    async def test_document_timeout_keeps_resume_step_available(self):
        await self.begin_role()
        await self.click("apply", "p1")
        self.message.text = None
        self.message.document = SimpleNamespace(file_name="resume.txt", file_size=100)
        self.message.bot.download.side_effect = asyncio.TimeoutError()
        await self.demo.input(self.message)
        self.assertIsNone(self.demo.session.profile)
        self.assertEqual(self.demo.session.stage, "resume")
        self.assertIn("Пришлите текст резюме", self.replies[-1][0])

    async def test_callback_payloads_fit_telegram_limit(self):
        await self.ready_letter()
        for _, keyboard in self.replies:
            if keyboard:
                self.assertTrue(all(len(button.callback_data.encode()) <= 64 for row in keyboard.inline_keyboard for button in row))


class DocumentTests(unittest.TestCase):
    @staticmethod
    def docx(xml, extra=b""):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("word/document.xml", xml)
            if extra:
                archive.writestr("padding.bin", extra)
        return output.getvalue()

    def test_txt_and_docx_extract_only_text(self):
        self.assertEqual(extract_document("Опыт: Python и SQL".encode(), "cv.TXT"), "Опыт: Python и SQL")
        xml = '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:t>Python</w:t><w:t>SQL</w:t></w:document>'
        self.assertEqual(extract_document(self.docx(xml), "cv.docx"), "Python SQL")

    def test_file_limits_pdf_and_xml_entities_are_rejected(self):
        for data, filename in [(b"x" * (TEXT_LIMIT + 1), "cv.txt"), (b"x" * (DOCX_LIMIT + 1), "cv.docx"), (b"%PDF", "cv.pdf")]:
            with self.assertRaises(ValueError):
                extract_document(data, filename)
        with self.assertRaises(ValueError):
            extract_document(self.docx("<doc/>", b"x" * (8 * 1024 * 1024 + 1)), "cv.docx")
        xml = '<?xml version="1.0" encoding="utf-16"?><!DOCTYPE a [<!ENTITY x "x">]><a>&x;</a>'
        with self.assertRaises(ValueError):
            extract_document(self.docx(xml.encode("utf-16")), "cv.docx")

    def test_profile_is_bounded_and_does_not_invent_skills(self):
        profile = extract_profile("Python разработчик. Пишу скрипты для личных задач. " * 40)
        self.assertLessEqual(len(profile["facts"]), 700)
        self.assertNotIn("PostgreSQL", profile["facts"])
        self.assertTrue(profile["truncated"])

    def test_explicit_profession_outweighs_incidental_programming_skills(self):
        cases = [
            ("Продуктовый дизайнер. Figma, исследования. Знаком с React и Python.", "design"),
            ("Product Designer. I prototype interfaces using React and Python.", "design"),
            ("Frontend-разработчик. React, TypeScript. Пишу вспомогательные скрипты на Python.", "front"),
            ("Python-разработчик. Создаю API, знаком с React и frontend инструментами.", "python"),
        ]
        for text, role in cases:
            with self.subTest(role=role):
                self.assertEqual(extract_profile(text)["role"], role)
