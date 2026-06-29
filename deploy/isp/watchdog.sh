#!/bin/bash
# Watchdog: перезапускает чат-бот подписок, если процесс упал.
# Добавь в ISPmanager → Планировщик CRON: */5 * * * *

BOT_DIR="/var/www/u3452280/data/vacancy-bot"
LOG_DIR="$BOT_DIR/logs"

mkdir -p "$LOG_DIR"

if ps aux 2>/dev/null | grep -v grep | grep -q "bot.chat_main"; then
    exit 0
fi

cd "$BOT_DIR" || exit 1
nohup .venv/bin/python -m bot.chat_main >> "$LOG_DIR/chat-bot.log" 2>&1 &
echo $! > "$LOG_DIR/chat-bot.pid"
