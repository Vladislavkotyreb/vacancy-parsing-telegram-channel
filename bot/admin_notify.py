"""Сообщение админу из серверных скриптов (автодеплой):

    python -m bot.admin_notify "текст"

Без TELEGRAM_ADMIN_ID молча ничего не делает. Сеть хостинга рвётся — три
попытки с паузой; не вышло — код 1, скрипт запишет это в свой лог.
"""

from __future__ import annotations

import asyncio
import sys

from aiogram import Bot
from aiogram.exceptions import TelegramNetworkError

from bot.config import Settings

ATTEMPTS = 3
PAUSE_SEC = 10


async def notify(text: str, settings: Settings, pause: float = PAUSE_SEC) -> bool:
    if not settings.telegram_admin_id:
        return True
    bot = Bot(token=settings.telegram_bot_token)
    try:
        for attempt in range(1, ATTEMPTS + 1):
            try:
                await bot.send_message(
                    settings.telegram_admin_id, text, disable_web_page_preview=True
                )
                return True
            except TelegramNetworkError:
                if attempt < ATTEMPTS:
                    await asyncio.sleep(pause)
        return False
    finally:
        await bot.session.close()


def main() -> int:
    text = " ".join(sys.argv[1:]).strip()
    if not text:
        print("Использование: python -m bot.admin_notify \"текст\"", file=sys.stderr)
        return 2
    return 0 if asyncio.run(notify(text, Settings.from_env())) else 1


if __name__ == "__main__":
    sys.exit(main())
