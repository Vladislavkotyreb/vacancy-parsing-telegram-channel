from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from bot.skills_match import extract_skills

MAX_FILE_BYTES = 2 * 1024 * 1024


def parse_resume(filename: str, data: bytes) -> list[str]:
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
    skills = extract_skills(text)
    if not skills:
        raise ValueError("Не нашёл знакомых навыков. Проверь, что навыки указаны текстом.")
    return skills
