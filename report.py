"""Сводка для отчёта: динамика по годам из уже найденных записей Scopus."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from io import BytesIO

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
                "Изменение к предыдущему году": change,
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


def ru_publications(count: int) -> str:
    n = abs(count)
    if 11 <= n % 100 <= 14:
        word = "публикаций"
    else:
        rem = n % 10
        if rem == 1:
            word = "публикация"
        elif rem in {2, 3, 4}:
            word = "публикации"
        else:
            word = "публикаций"
    return f"{count} {word}"


def report_sentence(report: ReportData) -> str:
    if not report.year_rows:
        return f"В выборке {report.total} записей без указанного года публикации."
    if report.distinct_years <= 1:
        return f"За {report.year_label} год: {ru_publications(report.total)}."
    return f"За {report.year_label} годы: {ru_publications(report.total)}."


def build_report_figure(report: ReportData):
    import matplotlib.pyplot as plt

    years = list(report.counts)
    values = [report.counts[year] for year in years]
    fig, ax = plt.subplots(figsize=(6.4, 2.35), dpi=120)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    bars = ax.bar(range(len(years)), values, color="#3d5a80", width=0.62)
    ax.set_xticks(range(len(years)))
    ax.set_xticklabels([str(year) for year in years])
    ax.set_ylabel("Число публикаций")
    ax.set_xlabel("Год публикации")
    ax.set_title("Публикации в Scopus", pad=8, fontsize=11)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="both", labelsize=9)
    ymax = max(values) if values else 0
    ax.set_ylim(0, ymax * 1.18 if ymax else 1)
    ax.yaxis.grid(True, linestyle=":", linewidth=0.6, color="#c8c8c8")
    ax.set_axisbelow(True)
    for bar, value in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            str(value),
            ha="center",
            va="bottom",
            fontsize=8,
        )
    fig.tight_layout(pad=0.4)
    return fig


def report_chart_png(report: ReportData) -> bytes:
    import matplotlib.pyplot as plt

    fig = build_report_figure(report)
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()
