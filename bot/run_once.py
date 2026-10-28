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

from bot.broadcast import SAFE_FROM, SAFE_TO, find_video, is_safe_time, load_broadcast, run_broadcast, send_preview
from bot.config import Settings
from bot.runtime import limit_threads
from bot.database import VacancyDatabase
from bot.service import VacancyService
from bot.subscriber_service import SubscriberService

logger = logging.getLogger(__name__)

# Утренняя рассылка пишет лог сама: в CRON её запускают без перенаправления
# вывода, и 25.10.2026 сбой рассылки не оставил следов.
DIGEST_LOG = Path(__file__).resolve().parent.parent / "logs" / "digest.log"


def _digest_lock():
    """Замок на время рассылки: две одновременные (CRON + ручной запуск) слали всё дважды.

    flock снимается ядром при любом завершении процесса, даже kill -9, —
    «залипшего» замка не бывает. None — замок держит другая рассылка.
    """
    import fcntl

    path = DIGEST_LOG.with_name("digest.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle  # держим открытым до конца процесса


def _log_to_file(path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(path, encoding="utf-8")
    except OSError:
        logger.exception("Не могу писать лог в %s", path)
        return
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)


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
    limit_threads()

    args = parse_args()
    if args.mode == "subscribers":
        _log_to_file(DIGEST_LOG)
    try:
        settings = Settings.from_env()
        db = VacancyDatabase(settings.db_path)
        bot = Bot(token=settings.telegram_bot_token)
        service = VacancyService(settings, db, bot)
    except Exception:
        # Без этого ошибка старта уходила только в stderr, а CRON его не сохраняет.
        logger.exception("Режим %s не запустился", args.mode)
        return 1

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
            lock = _digest_lock()
            if lock is None:
                logger.warning("Рассылка подписчикам уже идёт — второй запуск пропущен")
                await _notify_admin(bot, admin_id, "⚠️ Рассылка подписчикам уже идёт — второй запуск пропущен.")
                return 0
            subscriber_service = SubscriberService(settings, db, bot)
            stats = await subscriber_service.run_daily_digests()
            logger.info(
                "Рассылка подписчикам: получателей=%s, сообщений=%s, ролей собрано=%s, "
                "со сбоем=%s, HH ограничил=%s",
                stats.subscribers,
                stats.messages,
                stats.roles_collected,
                len(stats.failed_roles),
                len(stats.limited_roles),
            )
            if admin_id:
                lines = [
                    "⚠️ Рассылка подписчикам: дошла не всем." if stats.failed_users else "✅ Рассылка подписчикам.",
                    f"Активных подписчиков: {stats.subscribers}",
                    f"Отправлено сообщений: {stats.messages}",
                    f"Ролей собрано: {stats.roles_collected}",
                    f"Написали «новых нет»: {stats.empty_notices}",
                ]
                if stats.failed_users:
                    lines.append(f"⚠️ Не дошло и после повтора: {len(stats.failed_users)} — подробности в logs/digest.log")
                if stats.blocked:
                    lines.append(f"Заблокировали бота: {stats.blocked}")
                if stats.failed_roles:
                    # Без этой строки сбой сбора выглядит так же, как пустой день.
                    lines.append(
                        f"⚠️ Не собрались роли: {', '.join(stats.failed_roles)}"
                    )
                if stats.limited_roles:
                    lines.append(
                        "⚠️ Сбор неполный (HH или другая площадка не ответили), "
                        f"«новых нет» им не писали: {', '.join(stats.limited_roles)}"
                    )
                await _notify_admin(bot, admin_id, "\n".join(lines), retries=3)
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
    except Exception as exc:
        logger.exception("Ошибка выполнения режима %s", args.mode)
        if args.mode == "subscribers":
            # Раньше упавшая рассылка ничего не сообщала: о сбое узнавали от подписчиков.
            try:
                await _notify_admin(
                    bot, admin_id, f"⛔ Рассылка подписчикам упала: {type(exc).__name__}: {exc}\nЛог: logs/digest.log",
                    retries=3,
                )
            except Exception:
                logger.exception("Не смог сообщить админу о падении рассылки")
        return 1
    finally:
        await bot.session.close()


async def _broadcast(bot: Bot, db: VacancyDatabase, args: argparse.Namespace, admin_id: str) -> int:
    if not args.file:
        logger.error("broadcast: укажите --file с текстом сообщения")
        return 1
    broadcast_id, text = load_broadcast(Path(args.file))
    video = find_video(Path(args.file), text)
    user_ids = db.broadcast_audience(include_starters=args.include_starters)

    if not args.send:
        if not admin_id:
            logger.error("broadcast: для превью нужен TELEGRAM_ADMIN_ID в .env")
            return 1
        await send_preview(bot, int(admin_id), text, video)
        logger.info(
            "Превью «%s» отправлено админу. Получателей при отправке: %s. "
            "Чтобы разослать всем, добавьте --send",
            broadcast_id,
            len(user_ids),
        )
        return 0

    now = datetime.now(ZoneInfo(os.getenv("TIMEZONE", "Europe/Moscow")))
    if not is_safe_time(now.hour, now.minute):
        message = (
            f"⛔ Рассылка «{broadcast_id}» не отправлена: сейчас {now:%H:%M} МСК. "
            f"Всем отправляем только с {SAFE_FROM[0]:02d}:{SAFE_FROM[1]:02d} до {SAFE_TO[0]:02d}:{SAFE_TO[1]:02d}. "
            "Превью (без --send) можно в любое время."
        )
        logger.error(message)
        await _notify_admin(bot, admin_id, message)
        return 1
    stats = await run_broadcast(bot, db, broadcast_id, text, user_ids, video)
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
    retries: int = 0,
) -> None:
    if not admin_id:
        return
    kwargs = {"chat_id": int(admin_id), "text": text}
    if parse_mode:
        kwargs["parse_mode"] = parse_mode
    for attempt in range(retries + 1):
        try:
            await bot.send_message(**kwargs)
            return
        except Exception:
            logger.exception("Не удалось отправить уведомление admin_id=%s (попытка %s)", admin_id, attempt + 1)
            if attempt < retries:
                await asyncio.sleep(30)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
