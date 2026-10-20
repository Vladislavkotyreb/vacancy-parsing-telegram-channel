"""Персональные фильтры подписчика поверх уже собранных вакансий.

Фильтр применяется после общего сбора, а не в запросах к площадкам: сбор
кэшируется один раз на роль и делится между подписчиками, а персонализация
начинается позже. Фильтровать на этапе запроса значило бы собирать заново под
каждую комбинацию настроек.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from bot.models import Vacancy


@dataclass(frozen=True)
class FilterOutcome:
    kept: list[Vacancy] = field(default_factory=list)
    # Считаем причины отсева раздельно: «везде офис» и «площадка не сказала» —
    # разные проблемы, а снаружи оба выглядят как молчание бота.
    dropped_onsite: int = 0
    dropped_unknown: int = 0

    @property
    def dropped_total(self) -> int:
        return self.dropped_onsite + self.dropped_unknown


def apply_remote_filter(
    vacancies: Iterable[Vacancy], *, include_remote: bool
) -> FilterOutcome:
    """include_remote=True — оставить только вакансии с подтверждённой удалёнкой."""
    items = list(vacancies)
    if not include_remote:
        return FilterOutcome(kept=items)

    kept: list[Vacancy] = []
    dropped_onsite = 0
    dropped_unknown = 0

    for vacancy in items:
        if vacancy.is_remote is True:
            kept.append(vacancy)
        elif vacancy.is_remote is False:
            dropped_onsite += 1
        else:
            dropped_unknown += 1

    return FilterOutcome(
        kept=kept,
        dropped_onsite=dropped_onsite,
        dropped_unknown=dropped_unknown,
    )
