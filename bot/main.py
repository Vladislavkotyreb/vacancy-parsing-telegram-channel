from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Awaitable, Callable
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import Message, TelegramObject
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from bot.config import Settings
from bot.database import VacancyDatabase
from bot.service import VacancyService

logger = logging.getLogger(__name__)
router = Router()


class InjectMiddleware:
    def __init__(self, **dependencies: Any) -> None:
        self.dependencies = dependencies

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data.update(self.dependencies)
        return await handler(event, data)


def setup_scheduler(service: VacancyService, timezone: str) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=ZoneInfo(timezone))

    async def job() -> None:
        logger.info("Запуск ежедневного парсинга")
        found, posted = await service.run_daily_post()
        logger.info("Парсинг завершён: найдено=%s, опубликовано=%s", found, posted)

    scheduler.add_job(
        job,
        CronTrigger(hour=12, minute=0),
        id="daily_vacancy_post",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    return scheduler


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привет! Я собираю вакансии <b>продуктового дизайнера</b> "
        "с площадок РФ и СНГ и публикую новые каждый день в 12:00 (МСК).\n\n"
        "Источники: HeadHunter, Habr Career, GeekJob, GetMatch, Remote-job.ru.\n\n"
        "Команды:\n"
        "/status — статус последнего прогона\n"
        "/fetch — запустить парсинг вручную\n"
        "/test — тестовая публикация в канал",
        parse_mode="HTML",
    )


@router.message(Command("status"))
async def cmd_status(message: Message, db: VacancyDatabase) -> None:
    last = db.last_run()
    total = db.total_known()

    if not last:
        await message.answer("База пуста — парсинг ещё не запускался.")
        return

    await message.answer(
        "📊 <b>Статус</b>\n"
        f"Всего вакансий в базе: {total}\n"
        f"Последний запуск: {last['started_at']}\n"
        f"Завершён: {last['finished_at'] or '—'}\n"
        f"Найдено: {last['found_total']}\n"
        f"Опубликовано новых: {last['posted_new']}\n"
        f"Статус: {last['status']}",
        parse_mode="HTML",
    )


@router.message(Command("fetch"))
async def cmd_fetch(message: Message, service: VacancyService) -> None:
    await message.answer("⏳ Запускаю парсинг…")
    found, posted = await service.run_daily_post()
    if posted:
        await message.answer(
            f"✅ Готово.\nНайдено: {found}\nОпубликовано новых: {posted}",
        )
    else:
        await message.answer(
            f"✅ Готово.\nНайдено: {found}\n"
            "Новых свежих вакансий нет — в канал отправлено уведомление.",
        )


@router.message(Command("test"))
async def cmd_test(message: Message, service: VacancyService) -> None:
    await message.answer("⏳ Отправляю тестовую публикацию в канал…")
    posted = await service.send_test_post()
    await message.answer(f"✅ Тест отправлен: {posted} вакансий в одном сообщении.")


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    settings = Settings.from_env()
    db = VacancyDatabase(settings.db_path)
    bot = Bot(token=settings.telegram_bot_token)
    service = VacancyService(settings, db, bot)

    dp = Dispatcher()
    dp.update.middleware(InjectMiddleware(db=db, service=service))
    dp.include_router(router)

    scheduler = setup_scheduler(service, settings.timezone)
    scheduler.start()

    job = scheduler.get_job("daily_vacancy_post")
    next_run = job.next_run_time if job else None
    logger.info(
        "Бот запущен. Следующая публикация: %s (%s)",
        next_run,
        settings.timezone,
    )

    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
