from __future__ import annotations

import re
from typing import Optional

# Порядок важен: более специфичные грейды проверяются первыми.
_GRADE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bhead\s+of\b", re.I), "Head"),
    (re.compile(r"\b(?:design|team|tech|art)?\s*lead\b", re.I), "Lead"),
    (re.compile(r"\bprincipal\b", re.I), "Principal"),
    (re.compile(r"\bstaff\b", re.I), "Staff"),
    (re.compile(r"\b(?:senior|sr\.?|sen\.?)\b", re.I), "Senior"),
    (re.compile(r"\b(?:старш(?:ий|ая|ее|его)|синьор|sinior)\b", re.I), "Senior"),
    (re.compile(r"\b(?:middle|mid\.?|мидл|средн(?:ий|яя|ее|его))\b", re.I), "Middle"),
    (re.compile(r"\b(?:junior|jr\.?|jun\.?|младш(?:ий|ая|ее|его)|джун(?:ior)?)\b", re.I), "Junior"),
    (re.compile(r"\b(?:intern(?:ship)?|trainee|стаж[её]р(?:ка)?)\b", re.I), "Стажёр"),
)


def extract_grade(title: str) -> Optional[str]:
    text = " ".join(title.split())
    if not text:
        return None

    for pattern, label in _GRADE_PATTERNS:
        if pattern.search(text):
            return label

    return None
