# Telegram-бот: вакансии продуктового дизайнера

Бот парсит вакансии **продуктового дизайнера** с крупнейших русскоязычных площадок РФ и СНГ и публикует **новые** вакансии **каждый день в 12:00** (по умолчанию — Москва).

## Источники

| Площадка | Покрытие |
|----------|----------|
| **HeadHunter (hh.ru)** | Россия, Беларусь, Казахстан, Узбекистан, Кыргызстан, Армения, Азербайджан, Молдова, Грузия, Таджикистан |
| **Habr Career** | IT-вакансии, русскоязычные |
| **GeekJob** | IT, удалёнка, РФ/СНГ |
| **GetMatch** | Продуктовые и дизайн-вакансии, `language=ru` |
| **Djinni** | IT-вакансии, Украина и удалёнка, категория Design |
| **DOU** | IT-вакансии, категория Design (Украина, СНГ, remote) |
| **Remote-job.ru** | Удалённая работа, РФ и СНГ |

Фильтр оставляет только роли продуктового/UI/UX дизайна и отсекает аналитиков, менеджеров, motion/графику и т.п.

## Быстрый старт

### 1. Создайте бота

1. Откройте [@BotFather](https://t.me/BotFather) в Telegram.
2. Команда `/newbot` → сохраните **токен**.

### 2. Создайте канал или группу

1. Создайте канал (например, «Product Design Jobs RU»).
2. Добавьте бота **администратором** с правом публикации.
3. Узнайте `chat_id`:
   - для канала: перешлите любой пост канала боту [@userinfobot](https://t.me/userinfobot) или [@RawDataBot](https://t.me/RawDataBot);
   - ID канала выглядит как `-1001234567890`.

### 3. Настройте окружение

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
HH_USER_AGENT=ProductDesignerVacancyBot/1.0 (your@email.com)
TIMEZONE=Europe/Moscow
```

> **Важно:** для HH.ru API обязателен корректный `User-Agent` с контактным email ([документация](https://github.com/hhru/api)).

### 4. Запуск

```bash
source .venv/bin/activate
python -m bot.main
```

Бот:
- слушает команды в личке (`/start`, `/status`, `/fetch`);
- каждый день в **12:00** парсит площадки и постит новые вакансии в канал.

### 5. Автозапуск (macOS, launchd)

```bash
# Пример plist — замените пути на свои
cat > ~/Library/LaunchAgents/com.productdesign.vacancybot.plist <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.productdesign.vacancybot</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/vladislavkotyrev/Desktop/тг бот парсер вакансий/.venv/bin/python</string>
    <string>-m</string>
    <string>bot.main</string>
  </array>
  <key>WorkingDirectory</key>
  <string>/Users/vladislavkotyrev/Desktop/тг бот парсер вакансий</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
</dict>
</plist>
EOF

launchctl load ~/Library/LaunchAgents/com.productdesign.vacancybot.plist
```

### 6. Деплой без карты — GitHub Actions (бесплатно)

Автопостинг каждый день в 12:00, карта не нужна: **[deploy/github/README.md](deploy/github/README.md)**

### 7. Деплой 24/7 на Google Cloud (Always Free)

Инструкция: **[deploy/gcp/README.md](deploy/gcp/README.md)**

### 8. Деплой 24/7 на Oracle Cloud

Инструкция: **[deploy/oracle/README.md](deploy/oracle/README.md)**

## Команды бота

| Команда | Описание |
|---------|----------|
| `/start` | Приветствие и описание |
| `/status` | Статистика последнего прогона |
| `/fetch` | Ручной запуск парсинга и публикации |

## Структура проекта

```
bot/
  main.py          — точка входа, планировщик, команды
  config.py        — настройки и регионы HH
  database.py      — SQLite, дедупликация
  filters.py       — фильтр «продуктовый дизайнер»
  formatters.py    — формат сообщений Telegram
  service.py       — оркестрация парсеров
  parsers/
    hh.py          — HeadHunter API
    habr.py        — Habr Career
    geekjob.py     — GeekJob JSON API
    getmatch.ru    — GetMatch API
data/
  vacancies.db     — база (создаётся автоматически)
```

## Примечания

- Публикуются только **новые** вакансии (по `source + id`).
- Лимит за один прогон — `MAX_POSTS_PER_RUN` (по умолчанию 30), чтобы не флудить канал.
- При первом запуске `/fetch` сохранит все найденные вакансии в базу; в канал уйдут только те, что ещё не были известны.
