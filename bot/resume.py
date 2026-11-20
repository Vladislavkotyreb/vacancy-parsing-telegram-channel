from __future__ import annotations

import subprocess
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
                ["pdftotext", "-f", "1", "-l", "20", "-enc", "UTF-8", "-", "-"],
                input=data, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=8,
            )
        except FileNotFoundError:
            raise ValueError("Чтение PDF сейчас недоступно. Пришли резюме в TXT.")
        except subprocess.TimeoutExpired:
            raise ValueError("Не удалось обработать PDF. Пришли текстовую версию.")
        if proc.returncode:
            raise ValueError("Не удалось прочитать PDF. Пришли PDF с текстом или TXT.")
        text = proc.stdout.decode("utf-8", errors="replace")
    else:
        raise ValueError("Пришли резюме как документ TXT или PDF с текстом.")
    skills = extract_skills(text)
    if not skills:
        raise ValueError("Не нашёл знакомых навыков. Проверь, что навыки указаны текстом.")
    return skills
