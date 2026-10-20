# Telegram-бот: парсер вакансий

Один проект — два независимых продукта:

| Продукт | Что делает | Точка входа |
|---------|------------|-------------|
| **Канал** [@prdsvac](https://t.me/prdsvac) | ежедневный дайджест вакансий продуктового дизайнера | `python -m bot.run_once fetch` |
| **Подписки** | личные дайджесты в ЛС по выбранным ролям | `python -m bot.run_once subscribers` |
| **Чат-бот** | UI подписки: выбор ролей, отписка, `/stats` | `python -m bot.chat_main` |

Публикуются только вакансии, появившиеся за последние **72 часа** (`MAX_VACANCY_AGE_HOURS`).
Прод крутится на reg.ru (ISPmanager): канал в 10:00 МСК, рассылка подписчикам в 10:02.

## Источники

| Площадка | Покрытие |
|----------|----------|
| **HeadHunter (hh.ru)** | Россия, Беларусь, Казахстан, Узбекистан, Кыргызстан, Армения, Азербайджан, Молдова, Грузия, Таджикистан + прямой поиск по 11 работодателям бигтеха |
| **Карьерные сайты** | `rabota.sber.ru` (HTML-парсинг) |
| **GeekJob** | IT, удалёнка, РФ/СНГ |
| **GetMatch** | `specialization=design`, `language=ru` — только для дизайн-ролей |

## Роли

Подписчик выбирает специальность, затем одну или несколько вакансий внутри неё
(`bot/role_categories.py`, `bot/roles.py`):

| Специальность | Вакансии |
|---------------|----------|
| Дизайн | UX/UI \| Продуктовый дизайнер, Коммуникационный дизайнер, Графический дизайнер, Арт-директор |
| Frontend | React, Vue, Angular |
| Backend | Python, Java, Go |
| Продукт | Product Manager, Product Owner |
| QA | Ручное тестирование, Автоматизация |

В **канал** уходит только `product_designer` — фильтр `bot/filters.py`, он отсекает
аналитиков, менеджеров, motion/графику и смежные роли. Для остальных ролей —
regex-фильтры в `bot/role_filters.py`.

Для ролей, где по названию не видно отрасли («Тестировщик», «Руководитель
проектов» одинаково частые в IT, на стройке и на производстве), дополнительно
задан `hh_professional_roles` — профобласть в поиске HH.

Выбор ролей не хранит состояние: категория едет в `callback_data` кнопки, а
отмеченные вакансии читаются из галочек самой клавиатуры. Поэтому перезапуск
`chat_main` не ломает уже открытые у пользователей клавиатуры.

## Локальный запуск

```bash
cd "/Users/vladislavkotyrev/Desktop/тг бот парсер вакансий"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Отредактируйте `.env`:

```env
TELEGRAM_BOT_TOKEN=ваш_токен
TELEGRAM_CHAT_ID=-1001234567890
TELEGRAM_ADMIN_ID=ваш_telegram_id
HH_USER_AGENT=ProductDesignerVacancyBot/1.0 (your@email.com)
HH_ACCESS_TOKEN=
TIMEZONE=Europe/Moscow
MAX_VACANCY_AGE_HOURS=72
```

> **HH.ru API:** обязателен корректный `User-Agent` с контактным email. Если анонимные
> запросы получают `403` — зарегистрируйте приложение на [dev.hh.ru](https://dev.hh.ru/admin)
> и добавьте `HH_ACCESS_TOKEN` ([документация](https://github.com/hhru/api)).

Режимы `bot.run_once`:

```bash
python -m bot.run_once fetch                # спарсить и опубликовать в канал
python -m bot.run_once subscribers          # разослать дайджесты подписчикам
python -m bot.run_once subscribers-preview  # что ушло бы подписчикам, без отправки
python -m bot.run_once test                 # тестовый пост в канал на моках
python -m bot.run_once status               # статистика последнего прогона
```

Чат-бот подписок (polling, держит один процесс через pid-lock в `logs/chat-bot.pid`):

```bash
python -m bot.chat_main
```

> Одновременно с ботом нельзя запускать второй polling-процесс на том же токене —
> Telegram отдаёт `getUpdates` только одному потребителю.

## Тесты

```bash
python -m pytest tests/ -q
```

## Деплой

Прод — reg.ru / ISPmanager: **[deploy/isp/README.md](deploy/isp/README.md)** (cron,
watchdog, обновление кода).

GitHub Actions (`.github/workflows/daily-vacancies.yml`) оставлен **только на ручной
запуск** (`workflow_dispatch`): расписание отключено, чтобы у GitHub и сервера не
разъезжались базы дедупликации.

## Команды чат-бота

Основной UI — кнопки меню внизу чата: «Мои вакансии», «Прекратить рассылку»,
«Выбрать роли». Команды оставлены как fallback:

| Команда | Описание |
|---------|----------|
| `/start` | Приветствие и запуск выбора ролей |
| `/myrole` | Текущая подписка |
| `/stop` | Отписаться |
| `/stats` | Статистика (только для `TELEGRAM_ADMIN_ID`) |

Пользователь **обязан** написать `/start` первым — иначе Telegram не даст боту
писать ему в личку.

## Структура проекта

```
bot/
  run_once.py               — cron: fetch | subscribers | subscribers-preview | test | status
  chat_main.py              — polling-бот подписок (FSM: специальность → вакансии)

  service.py                — КАНАЛ: collect → filter → post → save
  subscriber_service.py     — ПОДПИСЧИКИ: сбор по ролям → DM каждому
  subscriber_collect.py     — парсинг источников под конкретную роль
  subscriber_formatters.py  — HTML личных дайджестов (без футера канала)
  formatters.py             — HTML канала (+ футер @prdsvac), пагинация по 4096 символов

  config.py                 — настройки, регионы HH, список работодателей и карьерных сайтов
  roles.py / role_categories.py — роли и их группировка в меню
  filters.py                — фильтр product designer (канал)
  role_filters.py           — regex-фильтры остальных ролей
  grades.py                 — грейд из названия / опыта HH
  dates.py                  — парсинг дат, свежесть, дедуп по названию+компании
  source_priority.py        — приоритет источников при дедупе
  database.py               — SQLite: vacancies, run_log, subscribers, subscriber_roles, subscriber_sent
  stats.py                  — сводка для /stats
  russian.py                — склонения в текстах
  parsers/                  — hh, bigtech, geekjob, getmatch
data/
  vacancies.db              — общая база (создаётся автоматически, WAL)
logs/
  chat-bot.log / chat-bot.pid
deploy/isp/                 — прод: cron-инструкции и watchdog
scripts/                    — разовые проверки
```

## Как работает дедупликация

Три слоя, чтобы одна вакансия не ушла дважды:

1. `uid = source:external_id` — точное совпадение внутри площадки.
2. `dedup_key` — нормализованные `название|компания`, ловит кросс-площадочные дубли.
   При конфликте побеждает источник с более высоким приоритетом (`source_priority.py`).
3. Раздельные хранилища: канал помнит опубликованное в таблице `vacancies`,
   подписчики — в `subscriber_sent` (по каждому пользователю отдельно).

В `vacancies` пишутся **только опубликованные** вакансии. Иначе вакансия, впервые
увиденная без даты публикации, навсегда блокировала бы себя по `dedup_key`.

## Поведение рассылок

- **Канал:** если новых вакансий нет — всё равно уходит уведомление «новых нет».
- **Подписчики:** если новых нет — сообщение **не отправляется** (тишина).
- Повторный ручной `subscribers` после успешной рассылки новых DM не даст —
  вакансии уже в `subscriber_sent`. Это нормально.
- Длинные дайджесты автоматически делятся на несколько сообщений Telegram.
- При смене ролей `subscriber_sent` пользователя очищается — новая подписка
  начинается с чистого листа.

Подробности архитектуры, история багов и что нельзя ломать — в
[AGENT_HANDOFF.md](AGENT_HANDOFF.md).
