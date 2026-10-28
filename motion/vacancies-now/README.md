# Ролик «🔎 Вакансии сейчас»

Анонс кнопки для рассылки: 1080×1350 (4:5 — Телеграм показывает в чате без обрезки), 60 fps, 12.6 с, бесшовный цикл.
Стиль — Telegram-ролики Миши Наера, правила — скилл `.claude/skills/motion-design`.

- `scene.html` — сцена: функция `render(t)`, блок `T` с таймингом.
- `render_part.js` — рендер кадров (2x, с прогревом): `node render_part.js $PWD/scene.html 0 189` (4 потока по 189 кадров),
  затем `ffmpeg -framerate 60 -i frames/f%04d.png -vf scale=1080:1350:flags=lanczos -c:v libx264 -pix_fmt yuv420p -crf 18 -an out.mp4`.
- `shot.js` — стоп-кадры: `node shot.js $PWD/scene.html 2.0 4.0`.
- `export.js` + `gen_jsx.py` — проект After Effects: элементы экрана PNG + скрипт с теми же выражениями.
  `node export.js $PWD/scene.html $PWD/ae/pack/assets/ui && python3 gen_jsx.py` (пути внутри — правь под себя).
- `ae/VacanciesNow_AE.zip` — готовый проект AE: Файл → Сценарии → Запустить файл сценария.
- `assets/` — мокап iPhone 17 из Figma (iOS 27 UI Kit), обои Telegram (`wall.html` + `tg/pattern.svg`), эмодзи Apple, аватар бота.
- `vacancies-now-4x5.mp4` — финальное видео (оно же `broadcasts/2026-10-29-vacancies-now.mp4`).
