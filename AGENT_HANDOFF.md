# Handoff: состояние проекта и история изменений

Этот файл — инструкция для следующего агента. Описывает текущее состояние
бота, архитектуру, деплой и что **нельзя ломать**.

---

## Текущее состояние (на 29.06.2026)

### Два независимых режима

| Режим | Назначение | Точка входа | Cron на сервере |
|-------|------------|-------------|-----------------|
| **Канал** | Пост в @prdsvac (продуктовый дизайнер) | `python -m bot.run_once fetch` | `0 10 * * *` |
| **Подписчики** | Личные дайджесты по роли | `python -m bot.run_once subscribers` | `2 10 * * *` |
| **Чат UI** | `/start`, выбор роли, `/stop` | `python -m bot.chat_main` | watchdog `*/5 * * * *` |

**КРИТИЧНО:** логику канала (`service.py`, `run_once fetch`, парсеры канала)
**не менять** без явного запроса. Подписчики — отдельный слой (`subscriber_*`,
`chat_main.py`, таблицы `subscribers` / `subscriber_sent`).

### Где запущен

Хостинг **reg.ru** (ISPmanager), пользователь `u3452280`:

```
/var/www/u3452280/data/vacancy-bot/
```

Python **3.8.6** — нужен `backports.zoneinfo` (см. `requirements.txt`).

### GitHub Actions

Расписание **отключено** — только `workflow_dispatch`. Канал и подписчики
живут на ISPmanager, не на GitHub.

### HH.ru API

`HH_ACCESS_TOKEN` в `.env` на сервере. При `403` — перевыпустить через
`client_credentials` (см. `deploy/isp/README.md` или историю ниже).

---

## Архитектура

```
bot/
  run_once.py           — cron: fetch | subscribers | test | status
  chat_main.py          — polling для подписок (/start, кнопки)
  main.py               — legacy admin-бот (НЕ используется на проде)

  service.py            — КАНАЛ: collect → filter → post → save
  subscriber_service.py — ПОДПИСЧИКИ: collect по роли → DM каждому
  subscriber_collect.py — парсинг HH/Habr/GeekJob/GetMatch по роли
  subscriber_formatters.py — HTML для личных дайджестов (без футера канала)

  roles.py              — MVP-роли: product_designer, frontend, backend
  role_filters.py       — regex-фильтры для frontend/backend
  filters.py            — фильтр product designer (только для канала)

  database.py           — SQLite: vacancies, run_log, subscribers, subscriber_sent
  formatters.py         — HTML для канала (+ футер @prdsvac)

  parsers/              — парсеры канала (product designer only)
data/
  vacancies.db          — общая БД (канал + подписчики, разные таблицы)
logs/
  chat-bot.log          — лог chat_main
  chat-bot.pid          — lock от двойного запуска
deploy/isp/
  watchdog.sh           — перезапуск chat_main если упал
  README.md             — инструкция деплоя подписчиков
```

### Канал (не трогать)

1. `collect_all` — HH, Habr, GeekJob, GetMatch с фильтром product designer
2. `filter_new` / `filter_fresh` / dedupe
3. Пост в `TELEGRAM_CHAT_ID`
4. В базу `vacancies` пишутся **только опубликованные** (не все спарсенные)

### Подписчики (MVP)

1. Пользователь: `/start` → inline-кнопка роли → `subscribers` table
2. Cron `subscribers`: для каждой роли с подписчиками — `collect_for_role`
3. Per-user dedup через `subscriber_sent` (отдельно от канала!)
4. Если новых вакансий 0 — **сообщение не отправляется** (тишина)
5. GetMatch только для `product_designer`

### Роли MVP

| id | label | GetMatch |
|----|-------|----------|
| `product_designer` | продуктового дизайнера | да |
| `frontend` | frontend-разработчика | нет |
| `backend` | backend-разработчика | нет |

Расширение на fullstack, QA, PM и т.д. — добавить в `roles.py` + `role_filters.py`.

---

## Cron на ISPmanager (актуальный)

```
# Канал — 10:00 МСК (НЕ МЕНЯТЬ без запроса пользователя)
0 10 * * *  cd /var/www/u3452280/data/vacancy-bot && PYTHONIOENCODING=utf-8 .venv/bin/python -m bot.run_once fetch

# Подписчики — 10:02 МСК (через 2 мин после канала)
2 10 * * *  cd /var/www/u3452280/data/vacancy-bot && PYTHONIOENCODING=utf-8 .venv/bin/python -m bot.run_once subscribers

# Watchdog chat_main — каждые 5 мин
*/5 * * * * bash /var/www/u3452280/data/vacancy-bot/deploy/isp/watchdog.sh
```

Cron-строки вводятся **в UI ISPmanager**, не в терминал.

---

## Команды для пользователей (chat_main)

| Команда | Действие |
|---------|----------|
| `/start` | Выбор роли (inline-кнопки) |
| `/myrole` | Текущая подписка |
| `/stop` | Отписаться |

Пользователь **обязан** написать `/start` первым — иначе Telegram не даст
слать сообщения в личку.

---

## Диагностика на сервере

```bash
cd /var/www/u3452280/data/vacancy-bot

# Канал вручную
PYTHONIOENCODING=utf-8 .venv/bin/python -m bot.run_once fetch

# Подписчики вручную
PYTHONIOENCODING=utf-8 .venv/bin/python -m bot.run_once subscribers

# Список подписчиков
.venv/bin/python -c "
from bot.config import Settings
from bot.database import VacancyDatabase
print(VacancyDatabase(Settings.from_env().db_path).list_active_subscribers())
"

# Чат-бот запущен?
ps aux | grep chat_main

# Логи чат-бота
tail -30 logs/chat-bot.log
```

---

## Исправленные баги (история)

### Канал

1. **Вечная блокировка вакансий без даты** — сохранять только опубликованные
2. **GetMatch date parse** — `parse_iso_datetime` вместо `fromisoformat`
3. **URL не экранирован** — `escape_html` в href
4. **GitHub cron задержки** — переезд на ISPmanager
5. **TelegramNetworkError** — retry в `_safe_send`
6. **Python 3.8** — `backports.zoneinfo`
7. **remote-job.ru удалён** — дублировал HH

### Подписчики (29.06.2026)

1. **watchdog + pgrep** — на reg.ru `pgrep` не находил процесс; заменено на `ps aux | grep chat_main`
2. **Двойной chat_main** — pid-file lock в `chat_main.py`
3. **Смена роли** — при смене роли очищается `subscriber_sent` для пользователя
4. **Пустая рассылка** — если новых вакансий 0, DM не отправляется (в отличие от канала)
5. **Flood** — пауза 50 ms между подписчиками

---

## Известные ограничения

- **Канал и подписчики** используют одну SQLite БД, но разные таблицы дедупа.
  WAL включён (`PRAGMA journal_mode=WAL`).
- **GetMatch** не подходит для dev-ролей (specialization=design).
- **Фильтры frontend/backend** — эвристика по title, возможны false positive/negative.
- **shared hosting** — `chat_main` может падать; watchdog перезапускает каждые 5 мин.
- **Повторный ручной `subscribers`** после успешной рассылки — новых DM не будет
  (вакансии уже в `subscriber_sent`). Это нормально.

---

## Обновление на сервере

```bash
cd /var/www/u3452280/data/vacancy-bot
git pull
.venv/bin/pip install -r requirements.txt   # если менялся requirements.txt

# Перезапуск chat_main после обновления
pkill -f bot.chat_main || true
nohup .venv/bin/python -m bot.chat_main >> logs/chat-bot.log 2>&1 &
```

---

## Что можно делать дальше (не реализовано)

- Роли: fullstack, graphic designer, QA, product manager
- `/settings` с inline-сменой роли без повторного текста
- Webhook вместо polling (если появится HTTPS endpoint)
- Не слать product_designer подписчикам то, что уже ушло в канал (опционально)
