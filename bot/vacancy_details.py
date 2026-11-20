"""Короткая выдержка и опубликованный способ связаться по поводу вакансии."""
from __future__ import annotations

import html
import re
import textwrap
from typing import Optional

from bs4 import BeautifulSoup


_EMAIL = re.compile(r"(?:mailto:)?([a-z0-9._%+'-]+@(?:[a-z0-9-]+\.)+[a-z]{2,63})", re.I | re.ASCII)
_TELEGRAM = re.compile(r"(?:@|(?:https?://)?t\.me/)([a-z][a-z0-9_]{4,31})/?", re.I | re.ASCII)
_ADDRESS = re.compile(
    r"https?://[^\s<>]+|(?<![\w./@-])(?:t\.me/[^\s<>]+|@\w+(?![\w/]|\.\w)|" + _EMAIL.pattern + ")",
    re.I,
)
_APPLY = re.compile(
    r"\b(?:отклик\w*|контакт(?:ы| для отклика)?|присыла\w*|прислать|пишите|писать|напиш\w*|"
    r"(?:отправ\w*|пришл\w*) (?:резюме|портфолио)|apply|(?:send|email|submit) (?:us |to us )?"
    r"(?:your |a )?(?:cv|resume|résumé|portfolio|application)|applications? (?:to|at)|"
    r"(?:contact|email) (?:our |the )?(?:recruiter|hiring team))\b|\b(?:рекрутер|recruiter|hr)\s*[:—–-]?\s*$", re.I,
)
_OTHER_CONTACT = re.compile(
    r"\b(?:канал\w*|блог\w*|подписыва\w*|подписат\w*|поддержк\w*|support|newsletter|subscribe|channel|"
    r"privacy|fraud\w*|complaints?|accommodat\w*|disabilit\w*|assistance|accessibility|"
    r"мошеннич\w*|конфиденциальност\w*|не (?:пиш\w*|писать|присыла\w*|отправ\w*)|do not|don't)\b", re.I,
)
_TASK = re.compile(r"\b(?:задач|предстоит|обязанност|заниматься|проектир|разрабат|разработк|"
                   r"создав|развив|исследова|отвеча|responsibilit|design|build|develop|implement|lead)\w*", re.I)
_REQUIREMENT = re.compile(r"\b(?:опыт|стаж|требу|необходим|портфолио|владен|знани|умени|"
                          r"experience|portfolio|proficien|require|must)\w*", re.I)
_HIRING = re.compile(r"\b(?:ищем|ищет|нужен|нужна|looking for|hiring)\b", re.I)


def _address(value: str) -> Optional[str]:
    if len(value) <= 254 and (match := _EMAIL.fullmatch(value)):
        return match[1]
    if match := _TELEGRAM.fullmatch(value):
        name = match[1]
        if not name.lower().endswith("bot") and name.lower() not in {"share", "proxy", "login", "iv", "socks"}:
            return "@" + name
    return None


def _paragraphs(value: str) -> list[str]:
    if re.search(r"</?[a-z][\w:-]*(?:\s|/?>)", value, re.I):
        soup = BeautifulSoup(value, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        for link in soup.find_all("a", href=True):
            label = link.get_text(" ", strip=True)
            target = _address(link["href"].strip())
            # У подписанной ссылки берём адрес назначения, а не похожий на контакт текст.
            if _ADDRESS.search(label):
                label = ""
            link.replace_with(f"{label} {target or ''} ")
        for tag in soup.find_all(["br", "p", "li", "div", "h2", "h3", "h4"]):
            tag.insert_after("\n")
        value = soup.get_text()
    else:
        value = html.unescape(value)
    return [line for raw in value.splitlines() if (line := " ".join(raw.split()).strip(" \t•→"))]


def _contact(paragraphs: list[str], contacts) -> Optional[str]:
    if isinstance(contacts, dict):
        for key in ("telegram", "email"):
            value = contacts.get(key)
            if isinstance(value, str):
                value = value.strip()
                if key == "telegram" and re.fullmatch(r"[a-zA-Z]\w{4,31}", value):
                    value = "@" + value
                if address := _address(value):
                    return address
        phones = contacts.get("phones")
        if not isinstance(phones, list):
            phones = []
        for phone in phones:
            if isinstance(phone, dict):
                number = "".join(str(phone.get(k) or "") for k in ("country", "city", "number"))
                digits = re.sub(r"[\s()+-]", "", number)
                if phone.get("country") and phone.get("number") and re.fullmatch(r"[1-9][0-9]{7,14}", digits):
                    return "+" + digits

    previous = ""
    for line in paragraphs:
        for match in _ADDRESS.finditer(line):
            prefix = (previous + " " + line[:match.start()]).strip()
            context = re.split(r"[.!?;]\s+", prefix)[-1][-120:]
            nearby = context + " " + line[match.end():match.end() + 100]
            if _APPLY.search(context) and not _OTHER_CONTACT.search(nearby):
                address = _address(match[0].rstrip(".,;:!?)]}»"))
                if address:
                    return address
        previous = line if line.endswith(":") else ""
    return None


def vacancy_details(*fields, contacts=None, apply_to=None, tags=None) -> tuple[Optional[str], Optional[str]]:
    """Выбираем фразы источника. Для коротких лент запасной вариант — указанные навыки."""
    lines = [line for field in fields if isinstance(field, str) for line in _paragraphs(field)]
    contact = _address(apply_to.strip()) if isinstance(apply_to, str) else None
    contact = contact or _contact(lines, contacts)
    candidates = []
    for line in lines:
        for sentence in re.split(r"(?<=[.!?;])\s+", line):
            sentence = sentence.strip(" \t•→–").rstrip(";")
            if (len(sentence) >= 14 and len(sentence.split()) >= 2 and not sentence.endswith(":")
                    and not _ADDRESS.search(sentence) and not sentence.lower().startswith(("headquarters:", "url:"))):
                candidates.append(sentence)
    # Сохраняем формулировки источника, в том числе «будет плюсом» и «не требуется».
    selected = []
    task = next((s for s in candidates if _TASK.search(s) and not _REQUIREMENT.search(s)), None)
    if not task:
        task = next((s for s in candidates if _HIRING.search(s)), None)
    if task:
        selected.append(task)
    requirement = next((s for s in candidates if s != task and _REQUIREMENT.search(s)), None)
    if requirement:
        selected.append(requirement)
    if not selected and candidates:
        selected.append(candidates[0])
    if selected:
        parts = [textwrap.shorten(s, width=145 if len(selected) > 1 else 285, placeholder="…") for s in selected]
        parts = [p[0].upper() + p[1:] if re.match("[а-яё]", p) else p for p in parts]
        return " ".join(p if p.endswith((".", "!", "?", "…")) else p + "." for p in parts), contact
    if isinstance(tags, list):
        labels = []
        for tag in tags:
            name = (tag.get("title") or tag.get("name")) if isinstance(tag, dict) else tag
            if isinstance(name, str) and name.strip() and name.strip() not in labels:
                labels.append(name.strip())
            if len(labels) == 5:
                break
        if labels:
            return textwrap.shorten("Навыки в вакансии — " + ", ".join(labels), width=225, placeholder="…"), contact
    return None, contact
