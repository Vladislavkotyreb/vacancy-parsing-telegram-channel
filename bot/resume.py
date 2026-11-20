from __future__ import annotations

import asyncio
from dataclasses import asdict
from io import BytesIO
import logging
import subprocess
import sys
from pathlib import Path

from aiogram.exceptions import TelegramAPIError

from bot.compatibility import ResumeProfile, parse_profile

MAX_FILE_BYTES = 2 * 1024 * 1024


def parse_resume_profile(filename: str, data: bytes) -> ResumeProfile:
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("Файл больше 2 МБ. Пришли сокращённую версию.")
    ext = Path(filename).suffix.lower()
    if ext == ".txt":
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ValueError("Сохрани TXT в кодировке UTF-8.")
    elif ext == ".pdf":
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "bot.pdf_text"],
                input=data, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=8,
            )
        except subprocess.TimeoutExpired:
            raise ValueError("Обработка PDF заняла слишком много времени. Попробуй меньший PDF.")
        if proc.returncode == 3:
            raise ValueError("Не удалось запустить чтение PDF на сервере. Попробуй позже.")
        if proc.returncode:
            raise ValueError("Не удалось открыть PDF. Проверь, что файл открывается без пароля.")
        text = proc.stdout.decode("utf-8")
        if not text.strip():
            raise ValueError("В PDF нет доступного текста. Экспортируй резюме в PDF с выделяемым текстом.")
    else:
        raise ValueError("Прикрепи резюме в PDF с выделяемым текстом.")
    profile = parse_profile(text)
    if not (profile.skills or profile.roles or profile.tasks):
        raise ValueError("Не нашёл знакомых навыков. Проверь, что навыки указаны текстом.")
    return profile


def parse_resume(filename: str, data: bytes) -> list[str]:
    return parse_resume_profile(filename, data).skills

async def load_match_profile(db, bot, user_id: int):
    """Однократно извлекает профиль из ранее сохранённого в Telegram документа."""
    if not db.resume_test_enabled(user_id):
        return None
    record = db.get_resume(user_id)
    if not record:
        return None
    if record["profile"] is None and record["file_id"] and record["file_name"]:
        buffer = BytesIO()
        try:
            await bot.download(record["file_id"], destination=buffer, timeout=10)
            profile = await asyncio.get_running_loop().run_in_executor(
                None, parse_resume_profile, record["file_name"], buffer.getvalue()
            )
            db.upgrade_resume(user_id, record["resume_id"], asdict(profile))
        except (TelegramAPIError, asyncio.TimeoutError, OSError, ValueError):
            logging.getLogger(__name__).warning("Не удалось обновить профиль резюме для %s", user_id)
        # Пока читали PDF, пользователь мог заменить или удалить запись.
        record = db.get_resume(user_id)
        if not record:
            return None
    return ResumeProfile(**record["profile"]) if record["profile"] is not None else record["skills"]
