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

    @property
    def uid(self) -> str:
        return f"{self.source}:{self.external_id}"
