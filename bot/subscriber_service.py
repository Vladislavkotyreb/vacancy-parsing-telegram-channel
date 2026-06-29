from __future__ import annotations

import asyncio
import logging
from typing import Iterable

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter

from bot.config import Settings
from bot.database import VacancyDatabase
from bot.dates import dedupe_by_title_company, is_fresh
from bot.models import Vacancy
from bot.roles import MVP_ROLE_IDS, ROLES, get_role
from bot.subscriber_collect import collect_for_role
from bot.subscriber_formatters import format_subscriber_digest

logger = logging.getLogger(__name__)


class SubscriberService:
    def __init__(self, settings: Settings, db: VacancyDatabase, bot: Bot) -> None:
        self.settings = settings
        self.db = db
        self.bot = bot

    async def run_daily_digests(self) -> dict[str, int]:
        subscribers = self.db.list_active_subscribers()
        if not subscribers:
            logger.info("Подписчиков нет — рассылка пропущена")
            return {"subscribers": 0, "messages": 0}

        by_role: dict[str, list[int]] = {}
        for row in subscribers:
            by_role.setdefault(row["role"], []).append(int(row["user_id"]))

        total_messages = 0
        for role_id in MVP_ROLE_IDS:
            user_ids = by_role.get(role_id, [])
            if not user_ids:
                continue

            role = get_role(role_id)
            if not role:
                continue

            vacancies = await collect_for_role(self.settings, role)
            fresh = self._filter_fresh(vacancies)
            logger.info(
                "Подписчики [%s]: найдено=%s, свежих=%s, получателей=%s",
                role_id,
                len(vacancies),
                len(fresh),
                len(user_ids),
            )

            for user_id in user_ids:
                try:
                    sent = await self._send_to_user(user_id, role, fresh, len(vacancies))
                    total_messages += sent
                    await asyncio.sleep(0.05)
                except TelegramForbiddenError:
                    logger.warning("Подписчик %s заблокировал бота — отписываем", user_id)
                    self.db.deactivate_subscriber(user_id)
                except Exception:
                    logger.exception("Ошибка рассылки подписчику %s", user_id)

        return {"subscribers": len(subscribers), "messages": total_messages}

    def _filter_fresh(self, vacancies: Iterable[Vacancy]) -> list[Vacancy]:
        return [
            vacancy
            for vacancy in vacancies
            if is_fresh(vacancy, self.settings.max_vacancy_age_hours)
        ]

    def _filter_new_for_user(self, user_id: int, vacancies: Iterable[Vacancy]) -> list[Vacancy]:
        new_items: list[Vacancy] = []
        for vacancy in vacancies:
            if self.db.is_sent_to_subscriber(user_id, vacancy.uid):
                continue
            if self.db.is_sent_to_subscriber_by_dedup(user_id, vacancy.title, vacancy.company):
                continue
            new_items.append(vacancy)
        return new_items

    async def _send_to_user(
        self,
        user_id: int,
        role,
        fresh_vacancies: list[Vacancy],
        total_found: int,
    ) -> int:
        new_vacancies = self._filter_new_for_user(user_id, fresh_vacancies)
        to_post = dedupe_by_title_company(new_vacancies)

        messages, included = format_subscriber_digest(
            role.label,
            to_post,
            total_found,
            self.settings.max_vacancy_age_hours,
        )

        if included == 0:
            logger.info(
                "Подписчик %s [%s]: новых вакансий нет — сообщение не отправляем",
                user_id,
                role.id,
            )
            return 0

        for message in messages:
            await self._safe_send(user_id, message)
            if len(messages) > 1:
                await asyncio.sleep(0.4)

        for vacancy in to_post:
            self.db.mark_sent_to_subscriber(user_id, vacancy)

        logger.info(
            "Подписчик %s [%s]: отправлено %s вакансий",
            user_id,
            role.id,
            included,
        )
        return len(messages)

    async def _safe_send(self, chat_id: int, text: str) -> None:
        network_retries = 0
        while True:
            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=False,
                )
                return
            except TelegramRetryAfter as exc:
                await asyncio.sleep(exc.retry_after + 1)
            except TelegramNetworkError as exc:
                network_retries += 1
                if network_retries > 3:
                    raise
                wait = 10 * network_retries
                logger.warning(
                    "Сеть недоступна (%s), повтор через %s с: %s",
                    network_retries,
                    wait,
                    exc,
                )
                await asyncio.sleep(wait)
