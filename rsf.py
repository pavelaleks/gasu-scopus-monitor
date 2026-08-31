"""Окно публикаций для ближайшего конкурса РНФ.

В 2026 году на конкурс 2027 года фонд просит статьи с января 2021.
Это 6 лет назад от года конкурса: для 2028 окна сдвинется на январь 2022.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

RSF_YEARS_BEFORE_CONTEST = 6


@dataclass(frozen=True)
class RsfWindow:
    contest_year: int
    from_year: int
    to_year: int

    @property
    def from_label(self) -> str:
        return f"января {self.from_year}"


def rsf_window(today: date | None = None) -> RsfWindow:
    """Ближайший конкурс — следующий календарный год; статьи с января (год − 6)."""
    today = today or date.today()
    contest_year = today.year + 1
    return RsfWindow(
        contest_year=contest_year,
        from_year=contest_year - RSF_YEARS_BEFORE_CONTEST,
        to_year=today.year,
    )


def record_in_rsf_window(record: dict, window: RsfWindow) -> bool:
    cover = (record.get("cover_date") or "").strip()
    if len(cover) >= 7:
        return f"{window.from_year}-01" <= cover[:7]
    year = str(record.get("year") or "").strip()
    if year.isdigit():
        value = int(year)
        return window.from_year <= value <= window.to_year
    return False
