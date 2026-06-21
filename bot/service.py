from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Iterable

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramRetryAfter

from bot.config import Settings
from bot.database import VacancyDatabase
from bot.formatters import format_combined_digest
from bot.models import Vacancy
from bot.parsers.base import BaseParser
from bot.parsers.djinni import DjinniParser
from bot.parsers.dou import DouParser
from bot.parsers.geekjob import GeekJobParser
from bot.parsers.getmatch import GetMatchParser
from bot.parsers.habr import HabrParser
from bot.parsers.hh import HHParser
from bot.parsers.remotejob import RemoteJobParser

logger = logging.getLogger(__name__)


class VacancyService:
    def __init__(self, settings: Settings, db: VacancyDatabase, bot: Bot) -> None:
        self.settings = settings
        self.db = db
        self.bot = bot
        self.parsers: list[BaseParser] = [
            HHParser(settings),
            HabrParser(),
            GeekJobParser(),
            GetMatchParser(),
            DjinniParser(),
            DouParser(),
            RemoteJobParser(),
        ]

    async def collect_all(self) -> list[Vacancy]:
        all_vacancies: dict[str, Vacancy] = {}

        for parser in self.parsers:
            try:
                vacancies = await parser.fetch()
                logger.info("%s: найдено %s подходящих вакансий", parser.source, len(vacancies))
                for vacancy in vacancies:
                    all_vacancies[vacancy.uid] = vacancy
            except Exception:
                logger.exception("Ошибка парсера %s", parser.source)

        return list(all_vacancies.values())

    def filter_new(self, vacancies: Iterable[Vacancy]) -> list[Vacancy]:
        new_items = []
        for vacancy in vacancies:
            if not self.db.is_known(vacancy.uid):
                new_items.append(vacancy)
        return new_items

    async def run_daily_post(self) -> tuple[int, int]:
        run_id = self.db.start_run()
        found_total = 0
        posted_new = 0

        try:
            vacancies = await self.collect_all()
            found_total = len(vacancies)
            new_vacancies = self.filter_new(vacancies)
            new_vacancies = new_vacancies[: self.settings.max_posts_per_run]

            to_post = new_vacancies[: self.settings.max_posts_per_run]
            posted_new = 0
            if to_post:
                posted_new = await self._send_combined(to_post, found_total)
            else:
                logger.info("Новых вакансий нет — публикация в канал пропущена")

            for vacancy in vacancies:
                self.db.save_vacancy(vacancy)

            self.db.finish_run(run_id, found_total, posted_new, "ok")
            return found_total, posted_new
        except Exception:
            self.db.finish_run(run_id, found_total, posted_new, "error")
            raise

    async def _send_combined(
        self, new_vacancies: list[Vacancy], total_found: int
    ) -> int:
        if not new_vacancies:
            return 0

        text, included = format_combined_digest(new_vacancies, total_found)
        await self._safe_send(text)
        return included

    async def send_test_post(self) -> int:
        samples = self._sample_vacancies()
        text, included = format_combined_digest(samples, len(samples))
        text = "🧪 <b>Тестовая публикация</b>\n\n" + text
        await self._safe_send(text)
        return included

    @staticmethod
    def _sample_vacancies() -> list[Vacancy]:
        return [
            Vacancy(
                source="hh.ru",
                external_id="sample-1",
                title="Product Designer",
                company="Яндекс",
                url="https://hh.ru/vacancy/123456",
                salary="200 000 — 350 000 ₽",
                location="Москва",
                work_format="Гибрид",
                published_at=datetime.now(),
            ),
            Vacancy(
                source="habr.com",
                external_id="sample-2",
                title="Продуктовый дизайнер",
                company="Тинькофф",
                url="https://career.habr.com/vacancies/123456",
                salary="от 250 000 ₽",
                location="Удалённо",
                work_format="Удалённо",
                published_at=datetime.now(),
            ),
            Vacancy(
                source="getmatch.ru",
                external_id="sample-3",
                title="Senior Product Designer",
                company="Avito",
                url="https://getmatch.ru/vacancies/123456",
                salary="300 000 — 450 000 ₽",
                location="Москва / удалённо",
                published_at=datetime.now(),
            ),
        ]

    async def _safe_send(self, text: str) -> None:
        while True:
            try:
                await self.bot.send_message(
                    chat_id=self.settings.telegram_chat_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=False,
                )
                return
            except TelegramRetryAfter as exc:
                await asyncio.sleep(exc.retry_after + 1)
