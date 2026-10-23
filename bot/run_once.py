"""Однократный прогон парсинга (для GitHub Actions и cron без polling)."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]

from aiogram import Bot
from aiogram.enums import ParseMode

from bot.broadcast import load_broadcast, run_broadcast, send_preview
from bot.config import Settings
from bot.database import VacancyDatabase
from bot.service import VacancyService
from bot.subscriber_service import SubscriberService

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Однократный запуск бота")
    parser.add_argument(
        "mode",
        nargs="?",
        choices=("fetch", "test", "status", "subscribers", "subscribers-preview", "broadcast"),
        default=os.getenv("RUN_MODE", "fetch"),
        help="fetch — пост в канал; subscribers — рассылка; subscribers-preview — проверка без "
        "отправки; broadcast — разовое сообщение всем (по умолчанию только превью админу)",
    )
    parser.add_argument("--file", help="broadcast: файл с текстом сообщения (HTML Телеграма)")
    parser.add_argument(
        "--send",
        action="store_true",
        help="broadcast: разослать всем. Без флага — только превью админу",
    )
    parser.add_argument(
        "--include-starters",
        action="store_true",
        help="broadcast: ещё и тем, кто нажимал /start, но не подписался",
    )
    return parser.parse_args()


def format_status(db: VacancyDatabase) -> str:
    last = db.last_run()
    total = db.total_known()

    if not last:
        return "📊 <b>Статус</b>\nБаза пуста — парсинг ещё не запускался."

    return (
        "📊 <b>Статус</b>\n"
        f"Всего вакансий в базе: {total}\n"
        f"Последний запуск: {last['started_at']}\n"
        f"Завершён: {last['finished_at'] or '—'}\n"
        f"Найдено: {last['found_total']}\n"
        f"Опубликовано новых: {last['posted_new']}\n"
        f"Статус: {last['status']}"
    )


def should_run_scheduled_fetch(db: VacancyDatabase, timezone: str) -> tuple[bool, str]:
    if os.getenv("GITHUB_EVENT_NAME") != "schedule":
        return True, "manual run"

    now = datetime.now(ZoneInfo(timezone))
    today = now.date().isoformat()
    skip_dates = {
        value.strip()
        for value in os.getenv("SCHEDULE_SKIP_DATES", "").split(",")
        if value.strip()
    }
    if today in skip_dates:
        return False, f"дата {today} в SCHEDULE_SKIP_DATES"

    if db.has_successful_post_today(timezone):
        return False, "сегодня уже была успешная публикация"

    # GitHub Actions часто запускает cron с большой задержкой и не в нужный слот.
    # Поэтому не ставим верхнюю границу окна: постим один раз в день при первом
    # же сработавшем запуске начиная с 12:00 МСК. Идеально это 12:00–14:59, но
    # если GitHub запустил позже — пост всё равно выйдет (а не потеряется).
    hour = now.hour
    if hour < 12:
        return False, f"ещё не 12:00 {timezone} (сейчас {hour}:xx)"

    return True, f"окно публикации открыто ({hour}:xx {timezone})"


async def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    args = parse_args()
    settings = Settings.from_env()
    db = VacancyDatabase(settings.db_path)
    bot = Bot(token=settings.telegram_bot_token)
    service = VacancyService(settings, db, bot)

    admin_id = os.getenv("TELEGRAM_ADMIN_ID", "").strip()

    try:
        if args.mode == "test":
            posted = await service.send_test_post()
            logger.info("Тест отправлен: %s вакансий", posted)
            await _notify_admin(bot, admin_id, f"✅ Тестовая публикация: {posted} вакансий в канале.")
            return 0

        if args.mode == "status":
            text = format_status(db)
            logger.info("Статус:\n%s", text.replace("<b>", "").replace("</b>", ""))
            if admin_id:
                await _notify_admin(bot, admin_id, text, parse_mode=ParseMode.HTML)
            else:
                logger.info(
                    "TELEGRAM_ADMIN_ID не задан — статус только в логах GitHub Actions"
                )
            return 0

        if args.mode == "subscribers":
            subscriber_service = SubscriberService(settings, db, bot)
            stats = await subscriber_service.run_daily_digests()
            logger.info(
                "Рассылка подписчикам: получателей=%s, сообщений=%s, ролей собрано=%s, со сбоем=%s",
                stats.subscribers,
                stats.messages,
                stats.roles_collected,
                len(stats.failed_roles),
            )
            if admin_id:
                lines = [
                    "✅ Рассылка подписчикам.",
                    f"Активных подписчиков: {stats.subscribers}",
                    f"Отправлено сообщений: {stats.messages}",
                    f"Ролей собрано: {stats.roles_collected}",
                ]
                if stats.failed_roles:
                    # Без этой строки сбой сбора выглядит так же, как пустой день.
                    lines.append(
                        f"⚠️ Не собрались роли: {', '.join(stats.failed_roles)}"
                    )
                await _notify_admin(bot, admin_id, "\n".join(lines))
            return 0

        if args.mode == "broadcast":
            return await _broadcast(bot, db, args, admin_id)

        if args.mode == "subscribers-preview":
            subscriber_service = SubscriberService(settings, db, bot)
            await subscriber_service.preview_digests()
            return 0

        allowed, reason = should_run_scheduled_fetch(db, settings.timezone)
        if not allowed:
            logger.info("Автопубликация пропущена: %s", reason)
            return 0

        logger.info("Автопубликация: %s", reason)
        found, posted = await service.run_daily_post()
        logger.info("Готово: найдено=%s, опубликовано=%s", found, posted)
        if posted:
            msg = f"✅ Парсинг завершён.\nНайдено: {found}\nОпубликовано новых: {posted}"
        else:
            msg = (
                f"✅ Парсинг завершён.\nНайдено: {found}\n"
                "Новых свежих вакансий нет — в канал отправлено уведомление."
            )
        await _notify_admin(bot, admin_id, msg)
        return 0
    except Exception:
        logger.exception("Ошибка выполнения режима %s", args.mode)
        return 1
    finally:
        await bot.session.close()


async def _broadcast(bot: Bot, db: VacancyDatabase, args: argparse.Namespace, admin_id: str) -> int:
    if not args.file:
        logger.error("broadcast: укажите --file с текстом сообщения")
        return 1
    broadcast_id, text = load_broadcast(Path(args.file))
    user_ids = db.broadcast_audience(include_starters=args.include_starters)

    if not args.send:
        if not admin_id:
            logger.error("broadcast: для превью нужен TELEGRAM_ADMIN_ID в .env")
            return 1
        await send_preview(bot, int(admin_id), text)
        logger.info(
            "Превью «%s» отправлено админу. Получателей при отправке: %s. "
            "Чтобы разослать всем, добавьте --send",
            broadcast_id,
            len(user_ids),
        )
        return 0

    stats = await run_broadcast(bot, db, broadcast_id, text, user_ids)
    await _notify_admin(
        bot,
        admin_id,
        f"✅ Рассылка «{broadcast_id}».\n"
        f"Получателей: {stats.recipients}\n"
        f"Доставлено сейчас: {stats.sent}\n"
        f"Уже получали раньше: {stats.already_sent}\n"
        f"Заблокировали бота: {stats.blocked}\n"
        f"Не доставлено (повторится при перезапуске): {stats.failed}",
    )
    return 0


async def _notify_admin(
    bot: Bot,
    admin_id: str,
    text: str,
    parse_mode: str | None = None,
) -> None:
    if not admin_id:
        return
    try:
        kwargs = {"chat_id": int(admin_id), "text": text}
        if parse_mode:
            kwargs["parse_mode"] = parse_mode
        await bot.send_message(**kwargs)
    except Exception:
        logger.exception("Не удалось отправить уведомление admin_id=%s", admin_id)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
