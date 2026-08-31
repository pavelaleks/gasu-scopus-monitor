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


def _save_figure_png(fig) -> bytes:
    import matplotlib.pyplot as plt

    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def report_chart_png(report: ReportData) -> bytes:
    return _save_figure_png(build_report_figure(report))


DONUT_COLORS = [
    "#3d5a80",
    "#ee6c4d",
    "#98c1d9",
    "#6a994e",
    "#f2cc8f",
    "#bc4749",
    "#81b29a",
    "#293241",
    "#e07a5f",
    "#e0fbfc",
]


def build_area_figure(
    slices: list[tuple[str, int]],
    title: str = "Области знаний Scopus",
    colors: list[str] | None = None,
):
    import matplotlib.pyplot as plt

    values = [count for _, count in slices]
    total = sum(values)
    fig, ax = plt.subplots(figsize=(6.4, 2.8), dpi=120)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    if not total:
        ax.text(0.5, 0.5, "Нет данных", ha="center", va="center")
        ax.set_axis_off()
        fig.tight_layout(pad=0.4)
        return fig
    palette = colors or [DONUT_COLORS[i % len(DONUT_COLORS)] for i in range(len(values))]
    ax.pie(
        values,
        colors=palette,
        startangle=90,
        wedgeprops={"width": 0.48, "edgecolor": "white", "linewidth": 1.2},
    )
    legend = []
    for name, count in slices:
        pct = round(count / total * 100)
        legend.append(f"{name} — {count} ({pct}%)")
    ax.legend(
        legend,
        loc="center left",
        bbox_to_anchor=(1.02, 0.5),
        frameon=False,
        fontsize=8,
        labelspacing=0.45,
    )
    ax.set_title(title, fontsize=11, pad=8)
    fig.tight_layout(pad=0.35)
    return fig


def report_area_png(
    slices: list[tuple[str, int]],
    title: str = "Области знаний Scopus",
    colors: list[str] | None = None,
) -> bytes:
    return _save_figure_png(build_area_figure(slices, title=title, colors=colors))


QUARTILE_COLORS = {
    "Q1": "#2d6a4f",
    "Q2": "#74c69d",
    "Q3": "#e9c46a",
    "Q4": "#e76f51",
    "Нет": "#adb5bd",
}


def report_quartile_png(rows: list[dict]) -> bytes:
    slices = [(row["Квартиль"], int(row["Публикаций"])) for row in rows if int(row["Публикаций"])]
    colors = [QUARTILE_COLORS.get(name, "#adb5bd") for name, _ in slices]
    return report_area_png(slices, title="Квартили журналов SCImago", colors=colors)
