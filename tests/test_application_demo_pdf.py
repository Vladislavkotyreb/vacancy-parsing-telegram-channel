import asyncio
import io
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from bot.application_demo import ApplicationDemo, PDF_LIMIT, extract_pdf
from bot.application_demo_pdf import PAGE_LIMIT, TEXT_LIMIT


def pdf_bytes(text="", pages=1, password=None):
    """Synthetic in-memory fixture, including an explicit Cyrillic character map."""
    writer = PdfWriter()
    for _ in range(pages):
        page = writer.add_blank_page(612, 792)
        if not text:
            continue
        alphabet = {char: number for number, char in enumerate(dict.fromkeys(text), 1)}
        mappings = "\n".join(f"<{code:02X}> <{char.encode('utf-16-be').hex()}>" for char, code in alphabet.items())
        cmap = DecodedStreamObject()
        cmap.set_data(f"begincmap\n1 begincodespacerange\n<00> <FF>\nendcodespacerange\n{len(alphabet)} beginbfchar\n{mappings}\nendbfchar\nendcmap".encode())
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica"), NameObject("/ToUnicode"): writer._add_object(cmap)})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
        content = DecodedStreamObject()
        encoded = "".join(f"{alphabet[char]:02X}" for char in text)
        content.set_data(f"BT /F1 12 Tf 72 720 Td <{encoded}> Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(content)
    if password:
        writer.encrypt(password)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


class PDFExtractionTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_worker_extracts_cyrillic_and_latin_text(self):
        text = "Продуктовый дизайнер. Опыт 4 года. Figma и Python."
        self.assertEqual(await extract_pdf(pdf_bytes(text)), text)

    async def test_scan_encrypted_invalid_page_and_text_limits(self):
        cases = [
            (pdf_bytes(), "OCR"),
            (pdf_bytes("Private resume", password="test"), "паролем"),
            (b"%PDF-1.4\nbroken", "Не удалось прочитать"),
            (pdf_bytes(pages=PAGE_LIMIT + 1), "20 страниц"),
            (pdf_bytes("a" * (TEXT_LIMIT + 1)), "слишком много текста"),
        ]
        for data, expected in cases:
            with self.subTest(expected=expected), self.assertRaisesRegex(ValueError, expected):
                await extract_pdf(data)

    async def test_pdf_size_rejected_before_process_launch(self):
        with patch("bot.application_demo.asyncio.create_subprocess_exec", new_callable=AsyncMock) as spawn:
            with self.assertRaisesRegex(ValueError, "2 МБ"):
                await extract_pdf(b"x" * (PDF_LIMIT + 1))
            spawn.assert_not_awaited()

    async def test_timeout_kills_and_reaps_child(self):
        async def communicate(data=None):
            if data is not None:
                await asyncio.sleep(10)
            return b"", None

        process = SimpleNamespace(returncode=None, communicate=AsyncMock(side_effect=communicate), kill=Mock())
        with patch("bot.application_demo.asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)), patch("bot.application_demo.PDF_TIMEOUT", 0.01):
            with self.assertRaisesRegex(ValueError, "слишком долго"):
                await extract_pdf(b"%PDF-1.4")
        process.kill.assert_called_once()
        self.assertEqual(process.communicate.await_count, 2)

    async def test_cancellation_kills_child_and_propagates(self):
        started = asyncio.Event()

        async def communicate(data=None):
            if data is not None:
                started.set()
                await asyncio.sleep(10)
            return b"", None

        process = SimpleNamespace(returncode=None, communicate=AsyncMock(side_effect=communicate), kill=Mock())
        with patch("bot.application_demo.asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)):
            task = asyncio.create_task(extract_pdf(b"%PDF-1.4"))
            await started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        process.kill.assert_called_once()
        self.assertEqual(process.communicate.await_count, 2)

    async def test_invalid_worker_output_has_user_facing_error(self):
        for output in (b"[]", b"{}", b"not-json", json.dumps({"error": []}).encode()):
            process = SimpleNamespace(returncode=0, communicate=AsyncMock(return_value=(output, None)))
            with patch("bot.application_demo.asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)):
                with self.assertRaisesRegex(ValueError, "Не удалось прочитать"):
                    await extract_pdf(b"%PDF-1.4")


class PDFTelegramFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.demo = ApplicationDemo(123)
        self.replies = []
        self.content = pdf_bytes("Продуктовый дизайнер. 4 года опыта. Figma и исследования.")

        async def answer(text, **kwargs):
            self.replies.append(text)

        async def download(doc, destination, **kwargs):
            destination.write(self.content)

        self.message = SimpleNamespace(from_user=SimpleNamespace(id=123), chat=SimpleNamespace(id=123, type="private"), text="/try_apply", document=None, answer=AsyncMock(side_effect=answer), bot=SimpleNamespace(download=AsyncMock(side_effect=download)))
        await self.demo.start(self.message)
        await self.demo.ask_resume(self.message)
        self.message.text = None
        self.message.document = SimpleNamespace(file_name="cv.PDF", file_size=len(self.content))

    async def asyncTearDown(self):
        await self.demo.close()

    async def test_uploaded_pdf_reaches_profile_confirmation(self):
        await self.demo.input(self.message)
        self.assertEqual(self.demo.session.stage, "profile")
        self.assertIn("Продуктовый дизайнер", self.demo.session.profile["facts"])
        self.assertFalse(self.demo.session.confirmed)

    async def test_scanned_pdf_leaves_resume_step_ready_for_retry(self):
        self.content = pdf_bytes()
        await self.demo.input(self.message)
        self.assertEqual(self.demo.session.stage, "resume")
        self.assertIsNone(self.demo.session.profile)
        self.assertIn("OCR", self.replies[-1])

    async def test_expired_session_does_not_restore_extracted_personal_data(self):
        async def expire(data):
            self.demo.clear()
            return "Продуктовый дизайнер. 4 года опыта."

        with patch("bot.application_demo.extract_pdf", new=AsyncMock(side_effect=expire)):
            await self.demo.input(self.message)
        self.assertIsNone(self.demo.session)
        self.assertIn("Время теста истекло", self.replies[-1])
