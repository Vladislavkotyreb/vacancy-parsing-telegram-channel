#!/bin/bash
# Watchdog: перезапускает чат-бот подписок, если процесс упал.
# Добавь в ISPmanager → Планировщик CRON: */5 * * * *

BOT_DIR="/var/www/u3452280/data/vacancy-bot"
LOG_DIR="$BOT_DIR/logs"

mkdir -p "$LOG_DIR"

if ps aux 2>/dev/null | grep -v grep | grep -q "bot.chat_main"; then
    exit 0
fi

# Общий замок с autodeploy.sh: пока идёт выкатка, бота перезапускает она. Без
# замка оба скрипта поднимали по копии — вторая видела первую и выходила с
# ошибкой (24.10.2026).
if command -v flock >/dev/null 2>&1; then
    exec 9>"$LOG_DIR/bot-control.lock"
    flock -n 9 || exit 0
fi

cd "$BOT_DIR" || exit 1

# pid-файл пишет сам chat_main (_acquire_single_instance). Watchdog его не трогает:
# если записать сюда $!, бот на старте прочитает собственный pid, решит, что уже
# запущен, и сразу выйдет — тогда watchdog не сможет поднять его никогда.
# 9>&- — чтобы бот не унёс с собой замок и не заблокировал автодеплой навсегда.
nohup .venv/bin/python -m bot.chat_main >> "$LOG_DIR/chat-bot.log" 2>&1 9>&- &
