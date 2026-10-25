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
from aiogram.types import InlineKeyboardMarkup, Message
from aiogram.exceptions import TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter

from bot.config import Settings
from bot.database import VacancyDatabase
from bot.cross_source import dedupe_across_sources
from bot.dates import ensure_aware, is_fresh
from bot.regions import for_region
from bot.grade_filter import filter_by_levels
from bot.digest_more import more_keyboard
from bot.models import Vacancy
from bot.roles import get_role
from bot.russian import format_digest_roles_label
from bot.subscriber_collect import SourceLimited, collect_for_role, shared_feeds
from bot.subscriber_formatters import SHARE_START, format_empty_notice, format_subscriber_digest

logger = logging.getLogger(__name__)

# Больше — не в один день. У нового подписчика «новые» — все вакансии за 72 ч:
# у продакт-менеджера их ~240, это ~20 сообщений подряд и повод отписаться.
# Отправляем самые свежие; остальные — по кнопке «Показать остальные»
# (bot/digest_more.py), а кто не нажал, получит их в следующие дни, пока не устареют.
MAX_VACANCIES_PER_DIGEST = 30


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
        # Ссылка на бота с меткой для строки «переслать коллеге» в конце подборки.
        self.share_url: Optional[str] = None

    async def run_daily_digests(self) -> DigestStats:
        subscribers = self.db.list_active_subscribers()
        if not subscribers:
            logger.info("Подписчиков нет — рассылка пропущена")
            return DigestStats()

        cache, failed_roles, limited_roles = await self._collect_roles_once(
            self._needed_roles(subscribers)
        )
        self.share_url = await self._share_url()
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
                region = self.db.get_region(user_id)
                levels = self.db.get_grades(user_id)
                vacancies, fresh = self._merge_for_roles(cache, role_ids, region, levels)
                logger.info(
                    "Подписчик %s roles=%s region=%s levels=%s: найдено=%s, свежих=%s",
                    user_id,
                    ",".join(role_ids),
                    region,
                    ",".join(levels) or "all",
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
                    region=region,
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

            region = self.db.get_region(user_id)
            levels = self.db.get_grades(user_id)
            vacancies, fresh = self._merge_for_roles(cache, role_ids, region, levels)
            label = format_digest_roles_label(role_ids)
            logger.info(
                "PREVIEW user=%s roles=%s region=%s levels=%s %s: собрано=%s, свежих=%s",
                user_id,
                ",".join(role_ids),
                region,
                ",".join(levels) or "all",
                label,
                len(vacancies),
                len(fresh),
            )

            all_new = dedupe_across_sources(self.db.unsent_to_subscriber(user_id, fresh))
            to_post = self._limit_freshest(all_new)
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
                rest = len(all_new) - len(to_post)
                button = f", кнопка «Показать остальные {rest}»" if rest else ""
                logger.info(
                    "PREVIEW user=%s: отправим %s вакансий (новых всего %s%s) — %s%s",
                    user_id,
                    len(to_post),
                    len(all_new),
                    button,
                    titles,
                    extra,
                )

    @staticmethod
    def _limit_freshest(vacancies: list[Vacancy]) -> list[Vacancy]:
        """Не больше MAX_VACANCIES_PER_DIGEST самых свежих; порядок показа прежний."""
        if len(vacancies) <= MAX_VACANCIES_PER_DIGEST:
            return vacancies
        freshest = sorted(
            vacancies,
            key=lambda v: ensure_aware(v.published_at).timestamp() if v.published_at else 0,
            reverse=True,
        )[:MAX_VACANCIES_PER_DIGEST]
        keep = {v.uid for v in freshest}
        return [v for v in vacancies if v.uid in keep]

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
        позже, в `db.unsent_to_subscriber`. Поэтому подписчики с одной ролью могут
        делить результат, и повторные обходы источников были чистой потерей.
        """
        cache: dict[str, list[Vacancy]] = {}
        failed: list[str] = []
        limited: list[str] = []

        # GetMatch отдаёт все IT-вакансии одной лентой — качаем её раз на прогон.
        with shared_feeds():
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

    async def _share_url(self) -> Optional[str]:
        """Ссылка на бота с меткой. Не узнали имя бота — подборка уйдёт без строки."""
        try:
            me = await self.bot.get_me()
        except Exception as exc:
            logger.warning("Не узнал имя бота для ссылки «переслать коллеге»: %r", exc)
            return None
        return f"https://t.me/{me.username}?start={SHARE_START}" if me.username else None

    def _merge_for_roles(
        self,
        cache: dict[str, list[Vacancy]],
        role_ids: list[str],
        region: str = "cis",
        levels: Optional[list[str]] = None,
    ) -> tuple[list[Vacancy], list[Vacancy]]:
        """Вакансии ролей подписчика с площадок его региона (СНГ / мир / оба)
        и его уровня. Вакансии с неизвестным уровнем остаются (bot/grade_filter.py)."""
        merged: dict[str, Vacancy] = {}
        for role_id in role_ids:
            for vacancy in for_region(cache.get(role_id, []), region):
                merged[vacancy.uid] = vacancy

        vacancies = filter_by_levels(list(merged.values()), levels or [])
        fresh = self._filter_fresh(vacancies)
        return vacancies, fresh

    def _filter_fresh(self, vacancies: Iterable[Vacancy]) -> list[Vacancy]:
        return [
            vacancy
            for vacancy in vacancies
            if is_fresh(vacancy, self.settings.max_vacancy_age_hours)
        ]

    async def _send_to_user(
        self,
        user_id: int,
        role_ids: list[str],
        fresh_vacancies: list[Vacancy],
        total_found: int,
        roles_complete: bool = True,
        region: str = "cis",
    ) -> tuple[int, bool]:
        """(сколько сообщений ушло, было ли это «новых нет»)."""
        all_new = dedupe_across_sources(self.db.unsent_to_subscriber(user_id, fresh_vacancies))
        to_post = self._limit_freshest(all_new)
        role_label = format_digest_roles_label(role_ids)

        # Остаток — для кнопки «Показать остальные». Пустой список стирает
        # прежний, чтобы старая кнопка не отдала то, что уже ушло подборкой.
        posted = {v.uid for v in to_post}
        overflow = [v for v in all_new if v.uid not in posted]
        today = self._today()
        self.db.replace_digest_overflow(user_id, today, overflow)
        more = more_keyboard(len(overflow), today) if overflow else None

        messages, included = format_subscriber_digest(
            role_label,
            to_post,
            total_found,
            self.settings.max_vacancy_age_hours,
            total_new=len(all_new),
            region=region,
            share_url=self.share_url,
        )

        if included == 0:
            return await self._send_empty_notice(
                user_id, role_ids, format_empty_notice(role_ids), roles_complete
            )

        delivered: Optional[Message] = None
        for index, message in enumerate(messages):
            is_last = index == len(messages) - 1
            markup = more if is_last else None
            delivered = await self._safe_send(user_id, message, markup) or delivered
            if len(messages) > 1:
                await asyncio.sleep(0.4)

        for vacancy in to_post:
            self.db.mark_sent_to_subscriber(user_id, vacancy)

        self._remember_profile(user_id, delivered)

        logger.info(
            "Подписчик %s roles=%s: отправлено %s вакансий, по кнопке ещё %s",
            user_id,
            ",".join(role_ids),
            included,
            len(overflow),
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

    async def _safe_send(
        self, chat_id: int, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None
    ) -> Optional[Message]:
        network_retries = 0
        while True:
            try:
                return await self.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=False,
                    reply_markup=reply_markup,
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
