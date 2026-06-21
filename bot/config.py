from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    telegram_chat_id: int
    hh_user_agent: str
    timezone: str
    max_vacancy_age_hours: int
    db_path: Path

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        if not token:
            raise ValueError(
                "TELEGRAM_BOT_TOKEN не задан. "
                "Локально: .env | GitHub: Settings → Secrets → Actions"
            )
        if not chat_id:
            raise ValueError(
                "TELEGRAM_CHAT_ID не задан. "
                "Локально: .env | GitHub: Settings → Secrets → Actions"
            )

        return cls(
            telegram_bot_token=token,
            telegram_chat_id=int(chat_id),
            hh_user_agent=os.getenv(
                "HH_USER_AGENT",
                "ProductDesignerVacancyBot/1.0 (contact@example.com)",
            ).strip(),
            timezone=os.getenv("TIMEZONE", "Europe/Moscow").strip(),
            max_vacancy_age_hours=int(os.getenv("MAX_VACANCY_AGE_HOURS", "72")),
            db_path=BASE_DIR / "data" / "vacancies.db",
        )


# Регионы РФ и СНГ в HH.ru
HH_AREAS = [
    113,  # Россия
    16,   # Беларусь
    40,   # Казахстан
    5,    # Узбекистан
    48,   # Кыргызстан
    97,   # Армения
    9,    # Азербайджан
    62,   # Молдова
    28,   # Грузия
    100,  # Таджикистан
]

SEARCH_QUERIES = [
    "продуктовый дизайнер",
    "product designer",
    "product design",
    "продуктовый ux",
    "product ux designer",
]
