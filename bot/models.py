from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Vacancy:
    source: str
    external_id: str
    title: str
    company: str
    url: str
    salary: Optional[str] = None
    location: Optional[str] = None
    published_at: Optional[datetime] = None
    work_format: Optional[str] = None
    grade: Optional[str] = None
    # Требуемый опыт HH (noExperience / between1And3 / …). Для фильтра по
    # уровню: «1–3 года» — это и Junior, и Middle, а grade хранит одно из них.
    experience: Optional[str] = None

    @property
    def uid(self) -> str:
        return f"{self.source}:{self.external_id}"
