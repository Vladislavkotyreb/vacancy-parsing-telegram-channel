# Деплой чат-бота подписок на ISPmanager (reg.ru)

Канал `@prdsvac` **не трогаем** — cron `fetch` в 10:00 остаётся как есть.

## 1. Обновить код

```bash
cd /var/www/u3452280/data/vacancy-bot
git pull
.venv/bin/pip install -r requirements.txt
mkdir -p logs
```

## 2. Cron: рассылка подписчикам (отдельно от канала)

**Планировщик CRON → Создать** (через 1–2 минуты после поста в канал):

- Минуты: `2`
- Часы: `10`
- Команда:

```bash
cd /var/www/u3452280/data/vacancy-bot && PYTHONIOENCODING=utf-8 .venv/bin/python -m bot.run_once subscribers
```

## 3. Cron: watchdog чат-бота (каждые 5 минут)

- Минуты: `*/5`
- Часы: `*`
- Команда:

```bash
bash /var/www/u3452280/data/vacancy-bot/deploy/isp/watchdog.sh
```

## 4. Первый запуск чат-бота

```bash
cd /var/www/u3452280/data/vacancy-bot
nohup .venv/bin/python -m bot.chat_main >> logs/chat-bot.log 2>&1 &
```

## 5. Проверка

- Напиши боту `/start` в личку → выбери роли
- Проверка без отправки: `PYTHONIOENCODING=utf-8 .venv/bin/python -m bot.run_once subscribers-preview`
- Ручная рассылка: `PYTHONIOENCODING=utf-8 .venv/bin/python -m bot.run_once subscribers`
- Логи чат-бота: `tail -f logs/chat-bot.log`
- Проверить процесс: `ps aux | grep chat_main` (не `pgrep` — на reg.ru может не работать)

## Поведение рассылки

- Если **есть новые** вакансии за 72 ч — DM с дайджестом, не больше 30 самых свежих
- Если новых больше 30 — под дайджестом кнопка «Показать остальные N». Её обрабатывает
  чат-бот, поэтому после обновления кода его нужно перезапустить
- Если **новых нет** — уходит «Новых вакансий … нет», не чаще раза в день
- Если роль подписчика не собралась (сбой или ограничение HH) — молчим, а админу
  приходит строка в отчёте
- Повторный ручной запуск в тот же день — без дублей (норма)

## Команды бота для пользователей

| Команда | Описание |
|---------|----------|
| `/start` | Выбор ролей: специальность → вакансии внутри неё |
| `/myrole` | Текущая подписка |
| `/stop` | Отписаться |
| `/stats` | Сводка по подписчикам и каналу (только `TELEGRAM_ADMIN_ID`) |
