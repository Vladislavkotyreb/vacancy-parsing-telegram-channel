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
| **Чат UI** | `/start`, выбор ролей, `/stop` | `python -m bot.chat_main` | watchdog `*/5 * * * *` |

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
  run_once.py           — cron: fetch | subscribers | subscribers-preview | test | status
  chat_main.py          — polling для подписок (/start, кнопки)

  service.py            — КАНАЛ: collect → filter → post → save
  subscriber_service.py — ПОДПИСЧИКИ: collect по роли → DM каждому
  subscriber_collect.py — парсинг HH/careers/GeekJob/GetMatch по роли
  subscriber_formatters.py — HTML для личных дайджестов (без футера канала)

  roles.py              — MVP-роли: product_designer, frontend, backend
  role_filters.py       — regex-фильтры для frontend/backend
  filters.py            — фильтр product designer (только для канала)

  database.py           — SQLite: vacancies, run_log, subscribers, subscriber_sent,
                          users, user_activity (админка)
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

1. `collect_all` — HH, careers, GeekJob, GetMatch с фильтром product designer
2. `filter_new` / `filter_fresh` / dedupe
3. Пост в `TELEGRAM_CHAT_ID`
4. В базу `vacancies` пишутся **только опубликованные** (не все спарсенные)

### Подписчики (MVP)

0. **Флоу выбора ролей не хранит состояние.** Категория лежит в `callback_data`
   (`s2:role:<category>:<role>`, `s2:save:<category>`), отмеченные роли читаются
   из галочек клавиатуры (`_draft_from_keyboard`). FSM и MemoryStorage убраны:
   раньше рестарт `chat_main` обнулял их, и все открытые клавиатуры отваливались
   с «Сначала выбери специальность». Не возвращай FSM — состояние в памяти на
   shared hosting теряется постоянно.
1. Пользователь: `/start` → inline-кнопка роли → `subscribers` table
2. Cron `subscribers`: **сбор один раз на роль за прогон** (`_collect_roles_once`),
   дальше подписчики обслуживаются из кэша (`_merge_for_roles`).
   `collect_for_role` не зависит от пользователя — персонализация начинается
   позже, в `_filter_new_for_user` / `subscriber_sent`. **Не возвращай
   `collect_for_role` внутрь цикла по подписчикам:** один проход по роли — это
   165–390 запросов к источникам, и раньше они умножались на число подписчиков.
   Стережёт `tests/test_subscriber_service.py`
3. Per-user dedup через `subscriber_sent` (отдельно от канала!)
4. Если новых вакансий 0 — **сообщение не отправляется** (тишина)
5. GetMatch только для дизайн-ролей (`uses_getmatch=True` в `roles.py`)

### Роли

Выбор двухшаговый: специальность (`role_categories.py`) → вакансии внутри неё
(`roles.py`), можно отметить несколько.

| Специальность | id ролей | GetMatch | professional_role HH |
|---------------|----------|----------|----------------------|
| Дизайн | `product_designer`, `communication_designer`, `graphic_designer`, `art_director` | да | только `art_director`: 12, 34 |
| Frontend | `frontend_react`, `frontend_vue`, `frontend_angular` | нет | — |
| Backend | `backend_python`, `backend_java`, `backend_go` | нет | — |
| Продукт | `product_manager`, `product_owner` | нет | 73 |
| QA | `qa_manual`, `qa_automation` | нет | 124 |

`hh_professional_roles` нужен там, где по названию не видно отрасли. Для QA
(`124`) это работает отлично — уходит контроль качества на стройке и на
производстве. Для продакта (`73`) эффект частичный, поэтому дополнительно
работает `NON_IT_DOMAIN_EXCLUDE` в `role_filters.py`.

`art_director`: «арт-директор» в РФ — ещё и ведущий программы в баре,
клубе, на концерте. Профобласть 12 («Арт-директор, креативный директор»)
одна режет и нужное — «Арт-директор/Дизайнер по упаковке» лежит в 34
(«Дизайнер, художник»), поэтому заданы обе, а заведения и мероприятия
добиваются `ART_DIRECTOR_EXCLUDE`. Креативный и дизайн-директор в роль
намеренно не входят — это соседние, но другие должности.

`frontend` и `backend` без суффикса — **legacy**: остались в `ROLES` ради уже
подписанных пользователей, но в меню не показываются (нет в `role_categories.py`).

Расширение на fullstack, QA, PM и т.д. — добавить в `roles.py` + `role_filters.py`
+ в нужную категорию в `role_categories.py`.

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

**Основной UI — кнопки меню внизу чата:**

| Кнопка | Действие |
|--------|----------|
| Выбрать роли / Выбрать роли заново | Шаг 1 (специальность) → шаг 2 (мультивыбор вакансий) |
| Мои вакансии | Текущая подписка |
| Прекратить рассылку | Отмена рассылки |

Команды `/start`, `/myrole`, `/stop` оставлены как fallback.
`/stats` и `/users` — админка, только для `TELEGRAM_ADMIN_ID` (без него
команды не отвечают никому). Подробности — в разделе «Админка и метрики».

### Админка и метрики

- **Активный** — что-то сделал в боте (сообщение или нажатие кнопки).
  `TrackActivityMiddleware` в `chat_main.py` пишет одну строку на человека в
  день в `user_activity` (день — по `TIMEZONE`). Отсюда DAU и MAU (30 дней,
  включая сегодня). Служебные апдейты вроде `my_chat_member` не считаются.
- **Охват** — получил хотя бы один дайджест (`subscriber_sent`). Для бота-
  рассылки это главная цифра: подписчик может месяцами читать и ничего не
  нажимать, а прочтения Телеграм боту не сообщает. **Не засчитывай получение
  дайджеста как активность** — иначе DAU станет копией охвата.
- **Отток** — `subscribers.unsubscribed_at` и `unsubscribe_reason`
  (`stop` — отписался сам, `blocked` — заблокировал бота, ловится на
  `TelegramForbiddenError` при рассылке). Повторная подписка их обнуляет.
- **Имена** в `/users`: из апдейтов (активные) и из ответа Телеграма на
  отправку дайджеста (молчаливые подписчики) — `upsert_user_profile`.
- Тексты сообщений **не храним** — только факт действия и профиль.
- Админ исключается из DAU/MAU, охвата и притока.
- Учёт активности начался с выкатки админки — DAU/MAU раньше этой даты
  не восстановить; `/stats` пишет, с какого дня идёт счёт.

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

### Чат-бот (09.08.2026)

1. **Watchdog не мог поднять бота** — `watchdog.sh` писал `echo $! > chat-bot.pid`
   раньше, чем питон стартовал. `_acquire_single_instance` читал файл, видел
   **собственный** pid, `os.kill(pid, 0)` проходил → «уже запущен» → `sys.exit(1)`.
   Ручной запуск работал, запуск через watchdog — всегда самоубийство: бот лежал,
   а в лог каждые 5 минут капало «Чат-бот уже запущен».
   Починено в двух местах: watchdog больше не трогает pid-файл (владелец — сам бот),
   и свой pid в файле больше не считается конфликтом. Тесты — `tests/test_single_instance.py`.
2. **Клавиатуры умирали при рестарте** — FSM жил в `MemoryStorage`, после
   перезапуска нажатие роли давало «Сначала выбери специальность». Убрано
   состояние целиком (см. «Подписчики», п. 0). Тесты — `tests/test_chat_flow.py`,
   в частности `test_keyboard_still_works_after_restart`.
3. **QA и PM тонули в не-IT** — «тестировщик техники», «инженер по качеству
   (дорожное строительство)», «Продакт-менеджер товарного направления»,
   «Product Manager (медицинские изделия, стоматология)». Добавлены
   `hh_professional_roles` и `NON_IT_DOMAIN_EXCLUDE`; этот мусор с живой выдачи
   HH ушёл, пересечений между ролями не осталось.
4. **Рассылка пересобирала всё заново на каждого подписчика** — стоимость была
   (подписчики × их роли) вместо (различных ролей). Десять подписчиков на
   `product_designer` = ~3900 запросов и ~13 минут ради десяти одинаковых
   ответов. Опаснее медленности был тихий отказ: при 403 `_search` обрывает
   обход целиком, роль собирается пустой, а пустая роль внешне неотличима от
   «сегодня новых нет» (DM не отправляется). Теперь сбор кэшируется по роли,
   а несобравшиеся роли уходят админу отдельной строкой в `run_once subscribers`.
5. **Пропуски в паттернах QA и PM** — живая выдача показала незакрытые формы:
   «Автотестировщик», «Тестировщик-автоматизатор», «QA Lead (Manual +
   Automation)», «Менеджер по продукту», «Проектный менеджер». Все добавлены
   в `role_filters.py` и закреплены тестами в `tests/test_role_filters.py`.

---

## Известные ограничения

- **Канал и подписчики** используют одну SQLite БД, но разные таблицы дедупа.
  WAL включён (`PRAGMA journal_mode=WAL`).
- **HH даты** приходят в формате `+0300`; `parse_iso_datetime` нормализует его в `+03:00`.
- **GetMatch** не подходит для dev-ролей (specialization=design).
- **Фильтры frontend/backend** — эвристика по title, возможны false positive/negative.
- **`project_manager` сознательно не добавлен.** Роль была написана и проверена
  на живой выдаче HH — и выброшена: «Руководитель проектов» в РФ доминируют
  стройка, производство и энергетика, а HH держит их под тем же
  `professional_role=107`, что и IT. Даже со словарём предметных областей
  сквозь фильтр проходило ~⅓ мусора вроде «Руководитель проектов (энергетика)».
  Не добавляй её обратно, не решив, чем отделять IT — заголовок и профобласть
  HH для этого не годятся.
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
