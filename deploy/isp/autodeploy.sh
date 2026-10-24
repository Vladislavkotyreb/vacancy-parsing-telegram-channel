#!/bin/bash
# Автодеплой чат-бота подписок с GitHub.
# ISPmanager → Планировщик CRON, каждые 5 минут (*/5 * * * *):
#   bash /var/www/u3452280/data/vacancy-bot/deploy/isp/autodeploy.sh
#
# Сервер сам забирает main, если тесты GitHub Actions на этом коммите прошли, —
# ключей и паролей от сервера в GitHub нет. По шагам:
#   1. не во время рассылок: 09:55–10:40 МСК и пока работает run_once;
#   2. есть новый коммит в origin/main и тесты зелёные → fast-forward;
#   3. код импортируется и база мигрирует — иначе откат на прошлый коммит;
#   4. перезапуск chat_main, итог — сообщением админу в Телеграм.
# Лог: logs/autodeploy.log.

set -u
# Переменные окружения переопределяют умолчания только для проверки скрипта на
# копии (scripts/test_autodeploy.sh); в CRON их не задаём.
BOT_DIR="${BOT_DIR:-/var/www/u3452280/data/vacancy-bot}"
REPO="Vladislavkotyreb/vacancy-parsing-telegram-channel"
CHECKS_URL="${CHECKS_URL:-https://api.github.com/repos/$REPO/commits}"
START_WAIT="${START_WAIT:-20}"
BRANCH="main"
LOG_DIR="$BOT_DIR/logs"
# Коммит, о провале которого уже сообщили: его не пробуем и не пишем повторно.
FAILED_STATE="$LOG_DIR/autodeploy.failed"
PY="$BOT_DIR/.venv/bin/python"

cd "$BOT_DIR" || exit 1
mkdir -p "$LOG_DIR"
exec >> "$LOG_DIR/autodeploy.log" 2>&1

log() { echo "$(TZ=Europe/Moscow date '+%F %T') $*"; }
notify() { PYTHONIOENCODING=utf-8 "$PY" -m bot.admin_notify "$1" || log "не смог написать админу: $1"; }
fail() {  # $1 — коммит, $2 — текст админу
    echo "$1" > "$FAILED_STATE"
    log "$2"
    notify "$2"
}
bot_running() { ps aux 2>/dev/null | grep -v grep | grep -q "bot.chat_main"; }

# Один управляющий процесс за раз: watchdog берёт тот же замок.
if command -v flock >/dev/null 2>&1; then
    exec 9>"$LOG_DIR/bot-control.lock"
    flock -n 9 || exit 0
fi

# Не трогаем бота во время утренней подборки и рассылок. Ищем именно процесс
# python: у отложенной рассылки (bash -c 'sleep … run_once') в строке тоже
# есть «bot.run_once», но она просто ждёт своего часа.
now=$((10#$(TZ=Europe/Moscow date +%H%M)))
if [ "$now" -ge 955 ] && [ "$now" -le 1040 ]; then exit 0; fi
if ps -eo comm=,args= 2>/dev/null | grep -qE "^python[0-9.]* .*bot\.run_once"; then exit 0; fi

git fetch -q origin "$BRANCH" 2>/dev/null || exit 0  # сеть хостинга рвётся — через 5 минут ещё раз
OLD=$(git rev-parse HEAD)
NEW=$(git rev-parse "origin/$BRANCH")
[ "$OLD" = "$NEW" ] && exit 0
[ "$(cat "$FAILED_STATE" 2>/dev/null)" = "$NEW" ] && exit 0
SHORT=$(git rev-parse --short "$NEW")
OLD_SHORT=$(git rev-parse --short "$OLD")
SUBJECT=$(git log -1 --format=%s "$NEW")

# Тесты GitHub Actions на этом коммите. Репозиторий публичный — API без токена.
CHECKS=$(curl -fsS -m 20 "$CHECKS_URL/$NEW/check-runs" 2>/dev/null) || exit 0
VERDICT=$(printf '%s' "$CHECKS" | "$PY" -c '
import json, sys
runs = [r for r in json.load(sys.stdin).get("check_runs", []) if r.get("name") == "tests"]
if not runs or any(r.get("status") != "completed" for r in runs):
    print("pending")
elif all(r.get("conclusion") == "success" for r in runs):
    print("success")
else:
    print("failure")
')
case "$VERDICT" in
    success) ;;
    failure) fail "$NEW" "⛔ $SHORT не выкачен: тесты в GitHub не прошли. Работает $OLD_SHORT"; exit 0 ;;
    *) exit 0 ;;  # тесты ещё идут
esac

log "выкатываю $OLD_SHORT → $SHORT: $SUBJECT"
if ! git merge -q --ff-only "origin/$BRANCH"; then
    fail "$NEW" "⛔ $SHORT не выкачен: на сервере свои изменения, обновить без слияния нельзя. Работает $OLD_SHORT"
    exit 1
fi
if git diff --name-only "$OLD" "$NEW" | grep -qx "requirements.txt"; then
    "$BOT_DIR/.venv/bin/pip" install -q -r requirements.txt || log "pip install не прошёл"
fi

# Код импортируется и база мигрирует — иначе откат.
SMOKE=$(PYTHONIOENCODING=utf-8 "$PY" -c "
import bot.run_once, bot.chat_main
from bot.config import Settings
from bot.database import VacancyDatabase
VacancyDatabase(Settings.from_env().db_path)
" 2>&1)
if [ $? -ne 0 ]; then
    git reset -q --hard "$OLD"
    fail "$NEW" "↩️ $SHORT откачен: код не запускается. Работает $OLD_SHORT
$(printf '%s' "$SMOKE" | tail -3)"
    exit 1
fi

# Перезапуск. 9>&- — чтобы бот не унёс с собой замок.
pkill -f "bot.chat_main"
for _ in $(seq 1 30); do
    bot_running || break
    sleep 1
done
pkill -9 -f "bot.chat_main" 2>/dev/null
rm -f "$LOG_DIR/chat-bot.pid"
nohup "$PY" -m bot.chat_main >> "$LOG_DIR/chat-bot.log" 2>&1 9>&- &
sleep "$START_WAIT"

if bot_running; then
    log "выкатил $SHORT"
    notify "✅ Выкатил $SHORT: $SUBJECT"
else
    log "бот не поднялся после $SHORT"
    notify "⚠️ Выкатил $SHORT, но бот не поднялся — watchdog перезапустит его за 5 минут. Лог: logs/chat-bot.log"
fi
