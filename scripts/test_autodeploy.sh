#!/bin/bash
# Проверка deploy/isp/autodeploy.sh на копии, без сервера и без GitHub:
# «GitHub» — локальный bare-репозиторий, «сервер» — его клон на коммит назад,
# ответ про тесты GitHub Actions — файлы, отдаваемые через file://.
#   bash scripts/test_autodeploy.sh
# Запускать на чистом дереве: берётся последний коммит текущей ветки.
set -eu
SRC="$(cd "$(dirname "$0")/.." && pwd)"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
pass=0; failed=0
ok()  { echo "  ✓ $1"; pass=$((pass + 1)); }
bad() { echo "  ✗ $1"; failed=$((failed + 1)); }

git clone -q --bare "$SRC" "$T/origin.git"
git clone -q "$T/origin.git" "$T/server"
cd "$T/server"
git reset -q --hard HEAD~1                       # сервер отстаёт на коммит
ln -s "$SRC/.venv" .venv
# TELEGRAM_ADMIN_ID пуст — уведомления молча пропускаются.
printf 'TELEGRAM_BOT_TOKEN=1:test\nTELEGRAM_CHAT_ID=-1\nHH_USER_AGENT=test/1.0\n' > .env
OLD=$(git rev-parse HEAD)

checks() {  # $1 — коммит, $2 — status, $3 — conclusion (JSON)
    mkdir -p "$T/api/$1"
    printf '{"check_runs":[{"name":"tests","status":"%s","conclusion":%s}]}' "$2" "$3" > "$T/api/$1/check-runs"
}
# Код выхода не проверяем: после отката скрипт честно выходит с 1.
run() { BOT_DIR="$T/server" CHECKS_URL="file://$T/api" START_WAIT=2 bash "$SRC/deploy/isp/autodeploy.sh" || true; }
log_has() { grep -q "$1" "$T/server/logs/autodeploy.log" 2>/dev/null; }
NEW=$(git rev-parse origin/main 2>/dev/null || git ls-remote origin -h refs/heads/main | cut -f1)

echo "1. Тесты ещё идут — ничего не трогаем"
checks "$NEW" in_progress null; run
[ "$(git rev-parse HEAD)" = "$OLD" ] && ok "остались на старом коммите" || bad "выкатил без зелёных тестов"

echo "2. Тесты упали — не выкатываем и сообщаем один раз"
checks "$NEW" completed '"failure"'; run
[ "$(git rev-parse HEAD)" = "$OLD" ] && ok "остались на старом коммите" || bad "выкатил с красными тестами"
log_has "тесты в GitHub не прошли" && ok "записал причину" || bad "нет записи о провале"
run
# «не смог написать админу» не считаем: на старом коде стенда может не быть bot.admin_notify.
[ "$(grep 'не прошли' logs/autodeploy.log | grep -vc 'не смог')" = "1" ] && ok "второй раз не повторяется" || bad "повторил сообщение"

echo "3. Тесты зелёные — выкатываем"
rm -f logs/autodeploy.failed
checks "$NEW" completed '"success"'; run
[ "$(git rev-parse HEAD)" = "$NEW" ] && ok "сервер на новом коммите" || bad "не выкатил"
log_has "выкатываю" && ok "записал выкатку" || bad "нет записи о выкатке"

echo "4. Новый коммит не запускается — откат"
WORK="$T/work"; git clone -q "$T/origin.git" "$WORK"
( cd "$WORK" && echo "this is not python" >> bot/regions.py \
  && git -c user.name=t -c user.email=t@t commit -qam "сломанный коммит" && git push -q origin HEAD:main )
BROKEN=$(git -C "$WORK" rev-parse HEAD)
checks "$BROKEN" completed '"success"'; run
[ "$(git rev-parse HEAD)" = "$NEW" ] && ok "откатился на рабочий коммит" || bad "остался на сломанном"
log_has "откачен" && ok "записал откат" || bad "нет записи об откате"
run
[ "$(git rev-parse HEAD)" = "$NEW" ] && ok "сломанный коммит больше не пробует" || bad "снова выкатил сломанный"

pkill -f "$T/server" 2>/dev/null || true
echo "Итого: $pass ок, $failed с ошибкой"
[ "$failed" -eq 0 ]
