"""Превью экранов бота до и после изменений — HTML для проверки перед деплоем.

Экраны строятся настоящим кодом бота (хэндлеры, форматтеры, рассылка) на
тестовых данных во временной базе: Телеграм, HH и сеть не нужны. Скрипт
прогоняет одни и те же сцены на двух версиях кода — «сейчас на сервере»
(--base) и рабочем дереве — и показывает, что изменилось.

    python scripts/preview_bot.py --base 1a85de5 --out preview.html

Сцены — функции с @scene ниже. Новая сцена нужна, когда изменение трогает
экран, которого здесь нет. Сцена должна работать и на старой версии кода:
то, чего там ещё нет, проверяйте через getattr/hasattr — упавшая сцена
показывается как «нет в этой версии».
"""

from __future__ import annotations

import argparse
import asyncio
import html
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import fields
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Optional
from unittest import mock

BOT_USERNAME = "productdesignervacparser228bot"
USER_ID = 100500
SCENES: list[tuple[str, str, Callable]] = []


def scene(scene_id: str, title: str):
    def register(fn):
        SCENES.append((scene_id, title, fn))
        return fn
    return register


# --- имитация Телеграма -------------------------------------------------------

def _markup(markup: Any) -> Optional[dict]:
    if markup is None:
        return None
    if getattr(markup, "inline_keyboard", None) is not None:
        return {"inline": [[b.text for b in row] for row in markup.inline_keyboard]}
    if getattr(markup, "keyboard", None) is not None:
        return {"reply": [[b.text for b in row] for row in markup.keyboard]}
    return None


class Chat:
    """Лента одного чата: сообщения бота в порядке появления, правки — на месте."""

    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, text: str, markup: Any = None, kind: str = "bot") -> dict:
        item = {"kind": kind, "text": text, "markup": _markup(markup)}
        self.items.append(item)
        return item

    def edited(self, item: dict) -> None:
        """Правка показывается там, где её видно в чате, — после нажатия кнопки."""
        self.items.remove(item)
        self.items.append(item)

    def toast(self, text: Optional[str], alert: bool = False) -> None:
        if text:
            self.items.append({"kind": "alert" if alert else "toast", "text": text, "markup": None})


class FakeMessage:
    def __init__(self, chat: Chat, text: str = "", item: Optional[dict] = None, reply_markup: Any = None):
        self.chat_log = chat
        self.text = text
        self.item = item
        self.reply_markup = reply_markup
        self.message_id = 1
        self.chat = SimpleNamespace(id=USER_ID, type="private", username="user", first_name="Аня", last_name=None)
        self.from_user = SimpleNamespace(id=USER_ID, username="user", first_name="Аня", last_name=None, is_bot=False)

    async def answer(self, text: str, **kw: Any) -> "FakeMessage":
        item = self.chat_log.add(text, kw.get("reply_markup"))
        return FakeMessage(self.chat_log, text, item, kw.get("reply_markup"))

    async def edit_text(self, text: str, **kw: Any) -> None:
        self.reply_markup = kw.get("reply_markup")
        self._update(text=text, markup=self.reply_markup)

    async def edit_reply_markup(self, reply_markup: Any = None, **kw: Any) -> None:
        self.reply_markup = reply_markup
        self._update(markup=reply_markup)

    def _update(self, text: Optional[str] = None, markup: Any = None) -> None:
        if self.item is None:
            self.item = self.chat_log.add(text or self.text, markup)
            return
        if text is not None:
            self.item["text"] = text
        self.item["markup"] = _markup(markup)
        self.chat_log.edited(self.item)


def user_says(chat: Chat, text: str) -> FakeMessage:
    chat.add(text, kind="user")
    return FakeMessage(chat, text)


def bot_message(chat: Chat, text: str, markup: Any) -> FakeMessage:
    """Сообщение бота, которое уже висит в чате (с него жмут кнопки)."""
    return FakeMessage(chat, text, chat.add(text, markup), markup)


def press(chat: Chat, message: FakeMessage, data: str, label: str) -> SimpleNamespace:
    chat.add(f"нажата кнопка «{label}»", kind="press")

    async def answer(text: Optional[str] = None, show_alert: bool = False, **kw: Any) -> None:
        chat.toast(text, show_alert)

    return SimpleNamespace(id="cb", data=data, from_user=message.from_user, message=message, answer=answer)


def make_settings(db_path: Path):
    from bot.config import Settings

    values = dict(
        telegram_bot_token="1:preview", telegram_chat_id=-100, hh_user_agent="preview/1.0",
        hh_access_token="", timezone="Europe/Moscow", max_vacancy_age_hours=72,
        db_path=db_path, telegram_admin_id=USER_ID,
    )
    return Settings(**{f.name: values[f.name] for f in fields(Settings) if f.name in values})


def vacancy(n: int, title: str, source: str = "hh.ru", **kw: Any):
    from bot.models import Vacancy

    known = {f.name for f in fields(Vacancy)}
    extra = {k: v for k, v in kw.items() if k in known}
    return Vacancy(
        source=source, external_id=str(n), title=title, company=["Ozon", "Т-Банк", "Авито", "VK"][n % 4],
        url=f"https://example.com/{n}", salary="от 250 000 ₽" if n % 2 else None,
        location="Москва", published_at=datetime.now(timezone.utc) - timedelta(hours=n), **extra,
    )


# --- сцены --------------------------------------------------------------------

@scene("subscribe_done", "Подписка сохранена: «Готово»")
async def subscribe_done(db, settings) -> Chat:
    from bot import chat_main as cm

    chat = Chat()
    msg = bot_message(chat, "<b>Шаг 3 из 3</b> — вакансии (Backend)",
                      cm.vacancy_keyboard("backend", {"backend_go", "backend_python"}))
    await cm.s2_save(press(chat, msg, f"{cm.S2_SAVE}backend", "Продолжить"), db)
    return chat


@scene("my_subscription", "Кнопка «Мои вакансии»")
async def my_subscription(db, settings) -> Chat:
    from bot import chat_main as cm

    db.set_subscriber_roles(USER_ID, ["backend_go", "backend_python"])
    db.set_region(USER_ID, "both")
    if hasattr(db, "set_grades"):
        db.set_grades(USER_ID, ["senior"])
    chat = Chat()
    await cm.send_subscription_info(user_says(chat, "Мои вакансии"), db)
    return chat


@scene("level_pick", "Команда /level: выбор уровня")
async def level_pick(db, settings) -> Chat:
    from bot import chat_main as cm

    chat = Chat()
    await cm.cmd_level(user_says(chat, "/level"), db)
    picker = FakeMessage(chat, item=chat.items[-1], reply_markup=cm.level_keyboard(set()))
    await cm.g_toggle(press(chat, picker, f"{cm.G_TOGGLE}middle", "Middle"))
    await cm.g_toggle(press(chat, picker, f"{cm.G_TOGGLE}senior", "Senior"))
    return chat


@scene("level_saved", "Команда /level: после «Сохранить»")
async def level_saved(db, settings) -> Chat:
    from bot import chat_main as cm

    chat = Chat()
    picker = bot_message(chat, "<b>Уровень вакансий</b>", cm.level_keyboard({"middle", "senior"}))
    await cm.g_save(press(chat, picker, cm.G_SAVE, "Сохранить"), db)
    return chat


@scene("digest", "Утренняя подборка (подписчик Go, уровень Senior)")
async def digest(db, settings) -> Chat:
    from bot.subscriber_service import SubscriberService

    db.set_subscriber_roles(USER_ID, ["backend_go"])
    if hasattr(db, "set_grades"):
        db.set_grades(USER_ID, ["senior"])
    found = [
        vacancy(1, "Senior Go developer"),
        vacancy(2, "Junior Go-разработчик"),
        vacancy(3, "Go-разработчик", source="getmatch.ru"),
        vacancy(4, "Go-разработчик (платежи)", grade="Junior", experience="between1And3"),
        vacancy(5, "Ведущий Golang-разработчик", source="career.habr.com"),
    ]
    chat = Chat()

    async def send_message(chat_id: int, text: str, **kw: Any):
        chat.add(text, kw.get("reply_markup"))
        return SimpleNamespace(chat=SimpleNamespace(type="private", username="user", first_name="Аня", last_name=None))

    bot = SimpleNamespace(
        send_message=send_message,
        get_me=mock.AsyncMock(return_value=SimpleNamespace(username=BOT_USERNAME)),
    )

    async def collect(settings_, role):
        return list(found)

    with mock.patch("bot.subscriber_service.collect_for_role", side_effect=collect):
        await SubscriberService(settings, db, bot).run_daily_digests()
    return chat


@scene("stats", "Команда /stats (админ)")
async def stats(db, settings) -> Chat:
    from bot import chat_main as cm

    for user_id, roles in ((1, ["backend_go"]), (2, ["frontend_react", "frontend"]), (3, ["product_manager"])):
        db.record_activity(user_id, f"u{user_id}", f"Имя{user_id}", None, day=datetime.now().date().isoformat())
        db.set_subscriber_roles(user_id, roles)
    db.record_activity(4, "u4", "Новичок", None, day=datetime.now().date().isoformat())
    if hasattr(db, "remember_came_from"):
        db.remember_came_from(4, "share")
    chat = Chat()
    await cm.cmd_stats(user_says(chat, "/stats"), db, settings)
    return chat


# --- прогон сцен на текущем коде ----------------------------------------------

async def run_scenes() -> dict:
    sys.path.insert(0, os.getcwd())
    from bot.database import VacancyDatabase

    result = {}
    for scene_id, title, fn in SCENES:
        db_path = Path(tempfile.mkdtemp()) / "preview.db"
        try:
            db = VacancyDatabase(db_path)
            chat = await fn(db, make_settings(db_path))
            result[scene_id] = {"title": title, "items": chat.items}
        except Exception as exc:  # чего-то из сцены нет в этой версии кода
            result[scene_id] = {"title": title, "missing": f"{type(exc).__name__}: {exc}"}
    return result


def scenes_for(checkout: Path) -> dict:
    out = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--json"],
        cwd=checkout, capture_output=True, text=True, env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    if out.returncode != 0:
        raise SystemExit(f"Сцены в {checkout} не собрались:\n{out.stderr[-2000:]}")
    return json.loads(out.stdout.strip().splitlines()[-1])


# --- HTML ---------------------------------------------------------------------

CSS = """
:root { --bg:#eef2f5; --surface:#fff; --chat:#dce6ee; --fg:#17212b; --muted:#5e6d7a; --line:#d0d9e1;
  --accent:#2a73b8; --bubble:#fff; --mine:#e1f0d7; --new:#1d7a4c; --new-soft:#dff3e7; --chg:#9a5b00; --chg-soft:#fbefd9;
  --gone:#a3362d; --gone-soft:#f8e1de; --f:"Onest","Segoe UI",system-ui,sans-serif; --mono:"JetBrains Mono",ui-monospace,Menlo,monospace }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg:#0f151b; --surface:#17202a; --chat:#0b1116; --fg:#e3eaf0;
  --muted:#93a2af; --line:#283541; --accent:#5ea8e8; --bubble:#1d2934; --mine:#23361f; --new:#5cc48e; --new-soft:#173327;
  --chg:#e3a54a; --chg-soft:#3a2b14; --gone:#ef8478; --gone-soft:#3d1d1a; color-scheme:dark } }
:root[data-theme="dark"] { --bg:#0f151b; --surface:#17202a; --chat:#0b1116; --fg:#e3eaf0; --muted:#93a2af; --line:#283541;
  --accent:#5ea8e8; --bubble:#1d2934; --mine:#23361f; --new:#5cc48e; --new-soft:#173327; --chg:#e3a54a; --chg-soft:#3a2b14;
  --gone:#ef8478; --gone-soft:#3d1d1a; color-scheme:dark }
* { box-sizing:border-box }
body { background:var(--bg); color:var(--fg); font-family:var(--f); font-size:15px; line-height:1.45;
  padding-left:max(16px, env(safe-area-inset-left, 0px)); padding-right:max(16px, env(safe-area-inset-right, 0px)); padding-block:24px 48px }
main { max-width:1100px; margin:0 auto; display:flex; flex-direction:column; gap:22px }
h1 { font-size:26px; margin:0; text-wrap:balance } h2 { font-size:18px; margin:0 }
.lead { color:var(--muted); margin:6px 0 0; max-width:70ch }
.mono { font-family:var(--mono); font-size:12.5px }
.summary { display:flex; gap:8px; flex-wrap:wrap }
.scene { background:var(--surface); border:1px solid var(--line); border-radius:14px; padding:16px; display:flex; flex-direction:column; gap:12px }
.scene-head { display:flex; gap:10px; align-items:center; flex-wrap:wrap }
.pill { font-size:12px; font-weight:600; padding:2px 10px; border-radius:999px }
.pill.changed { background:var(--chg-soft); color:var(--chg) } .pill.new { background:var(--new-soft); color:var(--new) }
.pill.same { background:var(--chat); color:var(--muted) } .pill.gone { background:var(--gone-soft); color:var(--gone) }
.cols { display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:12px }
.cols.one { grid-template-columns:minmax(0, 560px) }
@media (max-width:760px) { .cols { grid-template-columns:1fr } }
.col { min-width:0; display:flex; flex-direction:column; gap:6px }
.col-label { font-size:12px; font-weight:600; letter-spacing:.06em; text-transform:uppercase; color:var(--muted) }
.chat { background:var(--chat); border-radius:12px; padding:12px; display:flex; flex-direction:column; gap:6px; min-width:0 }
.msg { background:var(--bubble); border-radius:12px 12px 12px 4px; padding:9px 12px; white-space:pre-wrap; overflow-wrap:anywhere; font-size:14px; max-width:100% }
.msg a { color:var(--accent) }
.user { align-self:flex-end; background:var(--mine); border-radius:12px 12px 4px 12px; padding:7px 12px; font-size:14px }
.press, .toast { align-self:center; font-size:12px; color:var(--muted) }
.toast { background:var(--surface); border-radius:10px; padding:3px 10px }
.alert { align-self:center; font-size:13px; background:var(--gone-soft); color:var(--gone); border-radius:10px; padding:4px 10px }
.kb { display:flex; flex-direction:column; gap:4px }
.kb-row { display:flex; gap:4px }
.kb span { flex:1; text-align:center; font-size:13px; font-weight:500; border:1px solid var(--line); border-radius:8px; padding:7px 6px; background:var(--surface) }
.reply span { background:var(--bg) }
.missing { color:var(--muted); font-style:italic; font-size:14px; padding:8px 0 }
details > summary { cursor:pointer; color:var(--muted); font-size:14px }
"""


def _render_chat(data: dict) -> str:
    if "missing" in data:
        return '<div class="missing">Этого экрана в этой версии нет</div>'
    parts = []
    for item in data["items"]:
        kind, text = item["kind"], item["text"]
        if kind == "user":
            parts.append(f'<div class="user">{html.escape(text)}</div>')
        elif kind == "press":
            parts.append(f'<div class="press">↳ {html.escape(text)}</div>')
        elif kind in ("toast", "alert"):
            parts.append(f'<div class="{kind}">{html.escape(text)}</div>')
        else:
            # Текст — HTML Телеграма, собранный кодом бота из тестовых данных.
            parts.append(f'<div class="msg">{text}</div>')
        markup = item.get("markup")
        if markup:
            kind_kb = "inline" if "inline" in markup else "reply"
            rows = "".join(
                '<div class="kb-row">' + "".join(f"<span>{html.escape(b)}</span>" for b in row) + "</div>"
                for row in markup[kind_kb]
            )
            parts.append(f'<div class="kb {"reply" if kind_kb == "reply" else ""}">{rows}</div>')
    return '<div class="chat">' + "".join(parts) + "</div>"


def build_html(base: dict, head: dict, base_label: str, head_label: str) -> str:
    cards, counts = [], {"changed": 0, "new": 0, "same": 0, "gone": 0}
    for scene_id, title, _ in SCENES:
        before, after = base.get(scene_id, {"missing": "-"}), head[scene_id]
        if "missing" in after and "missing" not in before:
            status, label = "gone", "пропало"
        elif "missing" in before and "missing" not in after:
            status, label = "new", "новое"
        elif before == after:
            status, label = "same", "без изменений"
        else:
            status, label = "changed", "изменилось"
        counts[status] += 1
        head_html = (f'<div class="scene-head"><h2>{html.escape(title)}</h2>'
                     f'<span class="pill {status}">{label}</span></div>')
        if status == "same":
            body = f'<details><summary>Показать</summary><div class="cols one">{_render_chat(after)}</div></details>'
        elif status == "new":
            body = f'<div class="cols one"><div class="col"><div class="col-label">После деплоя</div>{_render_chat(after)}</div></div>'
        else:
            body = ('<div class="cols">'
                    f'<div class="col"><div class="col-label">Сейчас · {html.escape(base_label)}</div>{_render_chat(before)}</div>'
                    f'<div class="col"><div class="col-label">После деплоя · {html.escape(head_label)}</div>{_render_chat(after)}</div>'
                    "</div>")
        cards.append(f'<section class="scene">{head_html}{body}</section>')
    order = {"changed": 0, "new": 1, "gone": 2, "same": 3}
    cards.sort(key=lambda c: min(order[s] for s in order if f'pill {s}"' in c))
    summary = " ".join(
        f'<span class="pill {k}">{label}: {counts[k]}</span>'
        for k, label in (("changed", "изменилось"), ("new", "новое"), ("gone", "пропало"), ("same", "без изменений"))
        if counts[k]
    )
    return f"""<title>Превью бота перед деплоем</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Onest:wght@400;500;600;700&family=JetBrains+Mono&display=swap">
<style>{CSS}</style>
<main>
  <header>
    <h1>Что увидят пользователи после деплоя</h1>
    <p class="lead">Экраны собраны настоящим кодом бота на тестовых данных. Слева — версия <span class="mono">{html.escape(base_label)}</span>, справа — <span class="mono">{html.escape(head_label)}</span>.</p>
  </header>
  <div class="summary">{summary}</div>
  {''.join(cards)}
</main>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="origin/main", help="версия, которая сейчас на сервере (коммит или ветка)")
    parser.add_argument("--out", default="preview.html")
    parser.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.json:
        print(json.dumps(asyncio.run(run_scenes()), ensure_ascii=False))
        return

    repo = Path(__file__).resolve().parent.parent
    base_dir = Path(tempfile.mkdtemp()) / "base"
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", "--detach", str(base_dir), args.base], check=True)
    try:
        base = scenes_for(base_dir)
    finally:
        subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(base_dir)], check=False)
    head = scenes_for(repo)

    def label(ref: str) -> str:
        short = subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", ref], capture_output=True, text=True).stdout.strip()
        return short or ref

    dirty = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--", "bot"], capture_output=True, text=True).stdout.strip()
    head_label = label("HEAD") + (" + незакоммиченное" if dirty else "")
    Path(args.out).write_text(build_html(base, head, label(args.base), head_label), encoding="utf-8")
    changed = [sid for sid, _, _ in SCENES if base.get(sid) != head[sid]]
    print(f"{args.out}: изменилось сцен {len(changed)} из {len(SCENES)} ({', '.join(changed) or 'нет'})")


if __name__ == "__main__":
    main()
