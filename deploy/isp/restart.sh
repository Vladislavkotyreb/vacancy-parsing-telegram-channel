#!/usr/bin/env bash
# Ручной перезапуск после git pull. Проверяем PDF и ждём регистрации меню в Telegram.
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p logs
exec 9>logs/bot-control.lock
flock -w 90 9 || { echo "Другой процесс обновляет бота. Повтори после его завершения." >&2; exit 1; }

python=.venv/bin/python
if ! "$python" -c 'import pypdfium2' 2>/dev/null; then
    "$python" -m pip install -r requirements.txt
fi
"$python" -c 'from bot.chat_main import Settings, VacancyDatabase
from bot.resume import parse_resume_profile
from pathlib import Path
VacancyDatabase(Settings.from_env().db_path)
parse_resume_profile("test.pdf", Path("tests/fixtures/designer-resume.pdf").read_bytes())'

lock=logs/chat-bot.lock
if ! flock -n "$lock" true; then
    pid=$(cat logs/chat-bot.pid)
    if ! [[ "$pid" =~ ^[1-9][0-9]*$ ]] ||
       [[ "$(readlink -f "/proc/$pid/cwd")" != "$(pwd -P)" ]] ||
       ! tr '\0' '\n' < "/proc/$pid/cmdline" | grep -Fxq 'bot.chat_main'; then
        echo "Не удалось подтвердить PID работающего чат-бота." >&2
        exit 1
    fi
    kill -TERM "$pid"
    flock -w 90 "$lock" true || { echo "Бот ещё завершает работу." >&2; exit 1; }
fi

log=logs/chat-bot.log
touch "$log"
offset=$(wc -c < "$log")
nohup "$python" -m bot.chat_main </dev/null >> "$log" 2>&1 9>&- &
new_pid=$!
for _ in $(seq 1 180); do
    if ! kill -0 "$new_pid" 2>/dev/null; then
        tail -10 "$log" >&2
        exit 1
    fi
    if tail -c "+$((offset + 1))" "$log" | grep -F "Общее меню резюме зарегистрировано в Telegram, PID $new_pid" >/dev/null; then
        echo "Версия $(git rev-parse --short HEAD). Telegram принял меню для всех личных чатов. Идёт обновление клавиатур."
        exit 0
    fi
    sleep 1
done
echo "Telegram пока не подтвердил регистрацию меню. Проверь logs/chat-bot.log." >&2
exit 1
