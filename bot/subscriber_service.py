from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import Message
from aiogram.exceptions import TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter

from bot.config import Settings
from bot.database import VacancyDatabase
from bot.dates import dedupe_by_title_company, is_fresh
from bot.models import Vacancy
from bot.roles import get_role
from bot.russian import format_digest_roles_label
from bot.subscriber_collect import SourceLimited, collect_for_role
from bot.subscriber_formatters import format_empty_notice, format_subscriber_digest

logger = logging.getLogger(__name__)


@dataclass
class DigestStats:
    subscribers: int = 0
    messages: int = 0
    roles_collected: int = 0
    # Роли, сбор которых упал. Без этого списка провал сбора снаружи неотличим
    # от «сегодня новых вакансий нет»: и там и там подписчику не уходит DM.
    failed_roles: list[str] = field(default_factory=list)
    # Роли, на которых HH ответил 403: подписчики получили неполную подборку.
    # Раньше такая роль тихо собиралась пустой — снаружи это не было видно.
    limited_roles: list[str] = field(default_factory=list)
    # Сколько подписчиков получили «новых вакансий нет».
    empty_notices: int = 0


class SubscriberService:
    def __init__(self, settings: Settings, db: VacancyDatabase, bot: Bot) -> None:
        self.settings = settings
        self.db = db
        self.bot = bot

    async def run_daily_digests(self) -> DigestStats:
        subscribers = self.db.list_active_subscribers()
        if not subscribers:
            logger.info("Подписчиков нет — рассылка пропущена")
            return DigestStats()

        cache, failed_roles, limited_roles = await self._collect_roles_once(
            self._needed_roles(subscribers)
        )
        stats = DigestStats(
            subscribers=len(subscribers),
            roles_collected=len(cache),
            failed_roles=failed_roles,
            limited_roles=limited_roles,
        )

        for row in subscribers:
            user_id = int(row["user_id"])
            role_ids = self._roles_of(row)
            if not role_ids:
                logger.warning("Подписчик %s без ролей — пропуск", user_id)
                continue

            try:
                vacancies, fresh = self._merge_for_roles(cache, role_ids)
                logger.info(
                    "Подписчик %s roles=%s: найдено=%s, свежих=%s",
                    user_id,
                    ",".join(role_ids),
                    len(vacancies),
                    len(fresh),
                )
                sent, empty_notice = await self._send_to_user(
                    user_id,
                    role_ids,
                    fresh,
                    len(vacancies),
                    roles_complete=self._roles_complete(
                        role_ids, cache, failed_roles, limited_roles
                    ),
                )
                stats.messages += sent
                stats.empty_notices += int(empty_notice)
                await asyncio.sleep(0.05)
            except TelegramForbiddenError:
                logger.warning("Подписчик %s заблокировал бота — отписываем", user_id)
                self.db.deactivate_subscriber(user_id, reason="blocked")
            except Exception:
                logger.exception("Ошибка рассылки подписчику %s", user_id)

        return stats

    async def preview_digests(self) -> None:
        """Проверка без отправки: что получит каждый подписчик."""
        subscribers = self.db.list_active_subscribers()
        if not subscribers:
            logger.info("PREVIEW: подписчиков нет")
            return

        logger.info("PREVIEW: активных подписчиков=%s", len(subscribers))

        cache, failed, limited = await self._collect_roles_once(self._needed_roles(subscribers))
        if failed or limited:
            logger.warning("PREVIEW: не собрались=%s, HH ограничил=%s", failed, limited)

        for row in subscribers:
            user_id = int(row["user_id"])
            role_ids = self._roles_of(row)
            if not role_ids:
                logger.info("PREVIEW user=%s: роли не заданы", user_id)
                continue

            vacancies, fresh = self._merge_for_roles(cache, role_ids)
            label = format_digest_roles_label(role_ids)
            logger.info(
                "PREVIEW user=%s roles=%s %s: собрано=%s, свежих=%s",
                user_id,
                ",".join(role_ids),
                label,
                len(vacancies),
                len(fresh),
            )

            new_vacancies = self._filter_new_for_user(user_id, fresh)
            to_post = dedupe_by_title_company(new_vacancies)
            complete = self._roles_complete(role_ids, cache, failed, limited)
            if not to_post and complete and self.db.empty_notice_day(user_id) != self._today():
                logger.info("PREVIEW user=%s: новых вакансий нет — уйдёт «новых нет»", user_id)
            elif not to_post:
                logger.info(
                    "PREVIEW user=%s: новых вакансий нет — промолчим (%s)",
                    user_id,
                    "роль не собралась целиком" if not complete else "сегодня уже писали",
                )
            if to_post:
                titles = "; ".join(v.title[:50] for v in to_post[:5])
                extra = f" (+{len(to_post) - 5})" if len(to_post) > 5 else ""
                logger.info(
                    "PREVIEW user=%s: отправим %s вакансий — %s%s",
                    user_id,
                    len(to_post),
                    titles,
                    extra,
                )

    @staticmethod
    def _roles_complete(
        role_ids: list[str],
        cache: dict[str, list[Vacancy]],
        failed: list[str],
        limited: list[str],
    ) -> bool:
        """Все роли подписчика собраны целиком — только тогда можно честно сказать
        «новых вакансий нет». Сбой, ограничение HH или неизвестная роль — нельзя."""
        return all(
            role_id in cache and role_id not in failed and role_id not in limited
            for role_id in role_ids
        )

    def _today(self) -> str:
        return datetime.now(ZoneInfo(self.settings.timezone)).date().isoformat()

    @staticmethod
    def _roles_of(row: dict) -> list[str]:
        """Роли подписчика: новая таблица subscriber_roles, иначе legacy-колонка."""
        roles = row.get("roles") or []
        if not roles and row.get("role"):
            roles = [row["role"]]
        return roles

    def _needed_roles(self, subscribers: list[dict]) -> list[str]:
        """Различные роли всех подписчиков, в порядке первого появления."""
        seen: dict[str, None] = {}
        for row in subscribers:
            for role_id in self._roles_of(row):
                seen.setdefault(role_id, None)
        return list(seen)

    async def _collect_roles_once(
        self, role_ids: list[str]
    ) -> tuple[dict[str, list[Vacancy]], list[str], list[str]]:
        """Один сбор на роль за прогон, а не на каждого подписчика.

        `collect_for_role` не зависит от пользователя — персонализация начинается
        позже, в `_filter_new_for_user`. Поэтому подписчики с одной ролью могут
        делить результат, и повторные обходы источников были чистой потерей.
        """
        cache: dict[str, list[Vacancy]] = {}
        failed: list[str] = []
        limited: list[str] = []

        for role_id in role_ids:
            role = get_role(role_id)
            if not role:
                logger.warning("Неизвестная роль подписчиков: %s — пропуск", role_id)
                continue
            try:
                vacancies = await collect_for_role(self.settings, role)
            except SourceLimited as exc:
                # Отдаём то, что успело собраться, но помечаем роль для админа.
                logger.warning("Роль %s: %s, собрано %s", role_id, exc, len(exc.vacancies))
                limited.append(role_id)
                cache[role_id] = exc.vacancies
                continue
            except Exception:
                # Сбойный источник у одной роли не должен лишать дайджеста всех
                # остальных подписчиков.
                logger.exception("Не удалось собрать вакансии для роли %s", role_id)
                failed.append(role_id)
                cache[role_id] = []
                continue
            cache[role_id] = vacancies
            logger.info("Роль %s: собрано %s вакансий", role_id, len(vacancies))

        logger.info(
            "Сбор завершён: ролей=%s, со сбоем=%s, HH ограничил=%s",
            len(cache),
            len(failed),
            len(limited),
        )
        return cache, failed, limited

    def _merge_for_roles(
        self, cache: dict[str, list[Vacancy]], role_ids: list[str]
    ) -> tuple[list[Vacancy], list[Vacancy]]:
        merged: dict[str, Vacancy] = {}
        for role_id in role_ids:
            for vacancy in cache.get(role_id, []):
                merged[vacancy.uid] = vacancy

        vacancies = list(merged.values())
        fresh = self._filter_fresh(vacancies)
        return vacancies, fresh

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
        role_ids: list[str],
        fresh_vacancies: list[Vacancy],
        total_found: int,
        roles_complete: bool = True,
    ) -> tuple[int, bool]:
        """(сколько сообщений ушло, было ли это «новых нет»)."""
        new_vacancies = self._filter_new_for_user(user_id, fresh_vacancies)
        to_post = dedupe_by_title_company(new_vacancies)
        role_label = format_digest_roles_label(role_ids)

        messages, included = format_subscriber_digest(
            role_label,
            to_post,
            total_found,
            self.settings.max_vacancy_age_hours,
        )

        if included == 0:
            return await self._send_empty_notice(
                user_id, role_ids, format_empty_notice(role_ids), roles_complete
            )

        delivered: Optional[Message] = None
        for message in messages:
            delivered = await self._safe_send(user_id, message) or delivered
            if len(messages) > 1:
                await asyncio.sleep(0.4)

        for vacancy in to_post:
            self.db.mark_sent_to_subscriber(user_id, vacancy)

        self._remember_profile(user_id, delivered)

        logger.info(
            "Подписчик %s roles=%s: отправлено %s вакансий",
            user_id,
            ",".join(role_ids),
            included,
        )
        return len(messages), False

    async def _send_empty_notice(
        self, user_id: int, role_ids: list[str], text: str, roles_complete: bool
    ) -> tuple[int, bool]:
        """«Новых вакансий нет» — раз в день и только когда это правда."""
        roles = ",".join(role_ids)
        if not roles_complete:
            # Роль не собралась или HH её ограничил: вакансии могли быть, просто
            # мы их не увидели. Промолчим — админ узнает об этом из отчёта.
            logger.info("Подписчик %s roles=%s: новых нет, но сбор неполный — молчим", user_id, roles)
            return 0, False

        today = self._today()
        if self.db.empty_notice_day(user_id) == today:
            logger.info("Подписчик %s roles=%s: «новых нет» сегодня уже уходило", user_id, roles)
            return 0, False

        delivered = await self._safe_send(user_id, text)
        self.db.mark_empty_notice(user_id, today)
        self._remember_profile(user_id, delivered)
        logger.info("Подписчик %s roles=%s: новых нет — отправили уведомление", user_id, roles)
        return 1, True

    def _remember_profile(self, user_id: int, delivered: Optional[Message]) -> None:
        """Имя и username из ответа Телеграма на рассылку — для /users.

        Большинство подписчиков после подписки в боте ничего не нажимают, и
        другого способа узнать их имена без лишних запросов нет. Отметкой
        активности это не считается: получить дайджест — не значит им пользоваться.
        """
        chat = getattr(delivered, "chat", None)
        if chat is None or getattr(chat, "type", None) != "private":
            return
        try:
            self.db.upsert_user_profile(
                user_id, chat.username, chat.first_name, chat.last_name
            )
        except Exception:
            logger.exception("Не удалось сохранить профиль подписчика %s", user_id)

    async def _safe_send(self, chat_id: int, text: str) -> Optional[Message]:
        network_retries = 0
        while True:
            try:
                return await self.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=False,
                )
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
