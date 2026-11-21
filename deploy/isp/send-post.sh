#!/bin/bash
# Разовая отправка анонса из загруженного релиза с базой и токеном работающего бота.
set -euo pipefail
prod=$(git rev-parse --show-toplevel)
cd "$prod"
if [[ ! -s data/vacancies.db || ! -x .venv/bin/python ]]; then
    echo "Нужна папка работающего бота с data/vacancies.db и .venv/bin/python." >&2
    exit 1
fi
release=$(git rev-parse --verify FETCH_HEAD)
stage=$(mktemp -d)
trap 'rm -rf -- "$stage"' EXIT
post=broadcasts/2026-11-21-resume-match
git archive "$release" bot "$post.html" "$post.mp4" | tar -x -C "$stage"
ln -s "$prod/data" "$stage/data"
if [[ -f .env ]]; then ln -s "$prod/.env" "$stage/.env"; fi
mkdir -p logs
(
    cd "$stage"
    PYTHONIOENCODING=utf-8 "$prod/.venv/bin/python" -m bot.run_once broadcast \
        --file "$post.html" --send --include-starters
) 2>&1 | tee -a "$prod/logs/resume-announcement.log"

# После независимой отправки штатный деплой обновит и новые карточки в polling-боте.
bash deploy/isp/autodeploy.sh
if ! git merge-base --is-ancestor "$release" HEAD; then
    echo "Версия карточек на хостинге пока $(git rev-parse --short HEAD). Лог деплоя:" >&2
    tail -4 logs/autodeploy.log >&2
    exit 1
fi
