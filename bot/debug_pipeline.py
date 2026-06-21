"""Dry-run пайплайна без публикации в Telegram (для отладки)."""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import timezone

from aiogram import Bot

from bot.config import Settings
from bot.database import VacancyDatabase
from bot.dates import dedupe_by_title_company, ensure_aware
from bot.debug_log import debug_log
from bot.service import VacancyService

logger = logging.getLogger(__name__)


async def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    run_id = "dry-run"
    settings = Settings.from_env()
    db = VacancyDatabase(settings.db_path)
    bot = Bot(token=settings.telegram_bot_token)
    service = VacancyService(settings, db, bot)

    debug_log(
        hypothesis_id="E",
        location="debug_pipeline.py:main",
        message="settings loaded",
        data={
            "max_vacancy_age_hours": settings.max_vacancy_age_hours,
            "db_total_known": db.total_known(),
        },
        run_id=run_id,
    )

    try:
        vacancies = await service.collect_all()
        found_total = len(vacancies)
        new_vacancies = service.filter_new(vacancies)
        fresh_vacancies = service.filter_fresh(new_vacancies)
        deduped = dedupe_by_title_company(fresh_vacancies)
        to_post = deduped

        without_date = sum(1 for v in vacancies if not v.published_at)
        stale_new = len(new_vacancies) - len(fresh_vacancies)
        dedup_removed = len(fresh_vacancies) - len(deduped)

        by_source: dict[str, dict[str, int]] = {}
        for vacancy in vacancies:
            bucket = by_source.setdefault(
                vacancy.source,
                {"total": 0, "with_date": 0, "known": 0, "fresh_new": 0},
            )
            bucket["total"] += 1
            if vacancy.published_at:
                bucket["with_date"] += 1
            if db.is_known(vacancy.uid):
                bucket["known"] += 1
            if vacancy in fresh_vacancies and vacancy in new_vacancies:
                bucket["fresh_new"] += 1

        debug_log(
            hypothesis_id="A,B,C,D",
            location="debug_pipeline.py:summary",
            message="pipeline summary",
            data={
                "found_total": found_total,
                "new_count": len(new_vacancies),
                "fresh_count": len(fresh_vacancies),
                "deduped_count": len(deduped),
                "to_post_count": len(to_post),
                "without_date": without_date,
                "stale_or_no_date_new": stale_new,
                "dedup_removed": dedup_removed,
                "by_source": by_source,
            },
            run_id=run_id,
        )

        if to_post:
            sample = [
                {
                    "uid": v.uid,
                    "title": v.title[:60],
                    "company": v.company[:40],
                    "published_at": (
                        ensure_aware(v.published_at).isoformat()
                        if v.published_at
                        else None
                    ),
                }
                for v in to_post[:5]
            ]
            debug_log(
                hypothesis_id="B,D",
                location="debug_pipeline.py:sample",
                message="sample to_post",
                data={"sample": sample},
                run_id=run_id,
            )

        print(
            f"found={found_total} new={len(new_vacancies)} "
            f"fresh={len(fresh_vacancies)} deduped={len(deduped)} "
            f"to_post={len(to_post)} db_known={db.total_known()}"
        )
        return 0
    except Exception as exc:
        debug_log(
            hypothesis_id="E",
            location="debug_pipeline.py:error",
            message="pipeline failed",
            data={"error_type": type(exc).__name__, "error": str(exc)[:300]},
            run_id=run_id,
        )
        logger.exception("Debug pipeline failed")
        return 1
    finally:
        await bot.session.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
