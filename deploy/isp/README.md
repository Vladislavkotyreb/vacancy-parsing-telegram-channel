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

- Напиши боту `/start` в личку → выбери роль
- Ручная рассылка: `PYTHONIOENCODING=utf-8 .venv/bin/python -m bot.run_once subscribers`
- Логи чат-бота: `tail -f logs/chat-bot.log`
- Проверить процесс: `ps aux | grep chat_main` (не `pgrep` — на reg.ru может не работать)

## Поведение рассылки

- Если **есть новые** вакансии за 72 ч — DM с дайджestом
- Если **новых нет** — сообщение **не отправляется** (тишина)
- Повторный ручной запуск после успешной рассылки — снова тишина (норма)

## Команды бота для пользователей

| Команда | Описание |
|---------|----------|
| `/start` | Выбор роли (Product Designer / Frontend / Backend) |
| `/myrole` | Текущая подписка |
| `/stop` | Отписаться |
