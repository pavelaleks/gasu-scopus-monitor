"""Сводка для отчёта: динамика по годам из уже найденных записей Scopus."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from gasu import is_gasu_name


@dataclass(frozen=True)
class ReportData:
    total: int
    year_label: str
    unique_journals: int
    counts: dict[int, int]
    year_rows: list[dict]
    top_journals: list[tuple[str, int]]
    external_count: int
    external_share: float | None
    distinct_years: int


def _year(record: dict) -> int | None:
    raw = str(record.get("year") or "").strip()
    if raw.isdigit():
        value = int(raw)
        if 1900 <= value <= 2100:
            return value
    return None


def has_external_affiliation(affiliation: str) -> bool:
    parts = [part.strip() for part in (affiliation or "").split(";") if part.strip()]
    if len(parts) <= 1:
        return False
    return any(not is_gasu_name(part) for part in parts)


def build_report(records: list[dict], top_n: int = 5) -> ReportData:
    years = [_year(rec) for rec in records]
    valid_years = [year for year in years if year is not None]
    counts_raw = Counter(valid_years)
    if valid_years:
        lo, hi = min(valid_years), max(valid_years)
        counts = {year: counts_raw.get(year, 0) for year in range(lo, hi + 1)}
        year_label = str(lo) if lo == hi else f"{lo}–{hi}"
    else:
        counts = {}
        year_label = "—"

    year_rows = []
    previous = None
    for year in sorted(counts):
        current = counts[year]
        change = ""
        if previous is None:
            change = "—"
        elif previous == 0:
            change = "—" if current == 0 else "н/д"
        else:
            delta = round((current - previous) / previous * 100)
            sign = "+" if delta > 0 else ""
            change = f"{sign}{delta}%"
        year_rows.append(
            {
                "Год": year,
                "Публикаций": current,
                "К предыдущему году": change,
            }
        )
        previous = current

    journals = Counter()
    for rec in records:
        name = (rec.get("journal") or "").strip() or "Без названия источника"
        journals[name] += 1

    external_count = sum(1 for rec in records if has_external_affiliation(rec.get("affiliation") or ""))
    total = len(records)
    share = round(external_count / total * 100, 1) if total else None

    return ReportData(
        total=total,
        year_label=year_label,
        unique_journals=len(journals),
        counts=counts,
        year_rows=year_rows,
        top_journals=journals.most_common(top_n),
        external_count=external_count,
        external_share=share,
        distinct_years=len({year for year in valid_years}),
    )


def report_sentence(report: ReportData) -> str:
    if not report.year_rows:
        return f"В выборке {report.total} записей без указанного года публикации."
    last = report.year_rows[-1]
    last_year = last["Год"]
    last_n = last["Публикаций"]
    change = last["К предыдущему году"]
    change_bit = ""
    if change not in {"—", "н/д"}:
        change_bit = f", к {last_year - 1} году это {change}"
    return (
        f"За {report.year_label} найдено {report.total} публикаций. "
        f"В {last_year} году — {last_n}{change_bit}."
    )
