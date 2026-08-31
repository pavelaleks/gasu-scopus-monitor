"""Сводка для отчёта: динамика по годам из уже найденных записей Scopus."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from io import BytesIO

from gasu import is_gasu_name
from rsf import rsf_name_excluded


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


def _author_initials(author: dict) -> str:
    stored = (author.get("initials") or "").strip()
    letters = [ch for ch in stored.replace(".", " ") if ch.isalpha()]
    if letters:
        return "".join(f"{ch.upper()}." for ch in letters)
    given = (author.get("given") or "").replace(".", " ").replace("-", " ").strip()
    parts = [p for p in given.split() if p]
    return "".join(f"{p[0].upper()}." for p in parts)


def author_display_name(author: dict) -> str:
    surname = (author.get("surname") or "").strip()
    initials = _author_initials(author)
    if surname and initials:
        return f"{surname} {initials}"
    return surname


def author_merge_key(author: dict) -> str | None:
    surname = (author.get("surname") or "").strip()
    if not surname:
        return None
    initials = _author_initials(author)
    first = initials[:2].lower() if initials else ""
    return f"{surname.lower()}|{first}"


def report_who_label(records: list[dict], *, university: bool, author_last: str = "") -> str:
    if university:
        return "ГАГУ"
    wanted = (author_last or "").strip().lower()
    if wanted:
        for rec in records:
            for author in rec.get("authors") or []:
                surname = (author.get("surname") or "").strip()
                if surname.lower() == wanted or wanted in surname.lower():
                    name = author_display_name(author)
                    if name:
                        return name
    return (author_last or "").strip() or "Автор"


def report_scope_label(
    records: list[dict],
    *,
    university: bool,
    author_last: str = "",
    year: str | None = None,
) -> str:
    who = report_who_label(records, university=university, author_last=author_last)
    if year:
        return f"{who}, {year}"
    years = sorted({int(rec["year"]) for rec in records if str(rec.get("year") or "").isdigit()})
    if not years:
        return who
    period = str(years[0]) if years[0] == years[-1] else f"{years[0]}–{years[-1]}"
    return f"{who}, {period}"


def author_stats(records: list[dict], *, only_gasu: bool = False, limit: int | None = None) -> list[dict]:
    buckets: dict[str, dict] = {}
    for rec in records:
        quartile = rec.get("scimago_quartile") or "Нет"
        if quartile not in {"Q1", "Q2", "Q3", "Q4"}:
            quartile = "Нет"
        seen: set[str] = set()
        for author in rec.get("authors") or []:
            if only_gasu and author.get("from_gasu") is False:
                continue
            key = author_merge_key(author)
            if not key or key in seen:
                continue
            seen.add(key)
            bucket = buckets.get(key)
            if bucket is None:
                bucket = {
                    "names": Counter(),
                    "n": 0,
                    "Q1": 0,
                    "Q2": 0,
                    "Q3": 0,
                    "Q4": 0,
                    "none": 0,
                }
                buckets[key] = bucket
            bucket["names"][author_display_name(author)] += 1
            bucket["n"] += 1
            if quartile == "Нет":
                bucket["none"] += 1
            else:
                bucket[quartile] += 1
    rows = []
    for bucket in buckets.values():
        name = max(bucket["names"], key=lambda item: (len(item), bucket["names"][item]))
        share = round((bucket["Q1"] + bucket["Q2"]) / bucket["n"] * 100, 1) if bucket["n"] else 0.0
        rows.append(
            {
                "Автор": name,
                "Публикаций": bucket["n"],
                "Q1": bucket["Q1"],
                "Q2": bucket["Q2"],
                "Q3": bucket["Q3"],
                "Q4": bucket["Q4"],
                "Без квартиля": bucket["none"],
                "Доля Q1–Q2": f"{share:g}%",
            }
        )
    rows.sort(key=lambda row: (-row["Публикаций"], -row["Q1"], row["Автор"].lower()))
    if limit is None:
        return rows
    return rows[:limit]


def top_authors(records: list[dict], limit: int = 10) -> list[dict]:
    return author_stats(records, limit=limit)


def rsf_applicants(records: list[dict], min_papers: int) -> tuple[list[dict], bool]:
    """Авторы с числом статей ≥ порога на работах ГАГУ.

    Известных внешних соавторов (from_gasu is False) не считаем, но автора без
    персональной аффилиации в ответе Scopus не отбрасываем — иначе выпадают
    сотрудники вуза вроде Алексеева. Умерших в этот список не включаем.
    """
    skipped_external = any(
        author.get("from_gasu") is False
        for rec in records
        for author in rec.get("authors") or []
    )
    rows = author_stats(records, only_gasu=True)
    eligible = [
        row
        for row in rows
        if int(row["Публикаций"]) >= min_papers and not rsf_name_excluded(str(row.get("Автор") or ""))
    ]
    return eligible, skipped_external


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
    n = len(years)
    width = min(11.0, max(6.4, 0.28 * n))
    fig, ax = plt.subplots(figsize=(width, 2.45), dpi=120)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    bars = ax.bar(range(n), values, color="#3d5a80", width=0.62 if n < 18 else 0.78)
    ax.set_xticks(range(n))
    ax.set_xticklabels([str(year) for year in years])
    if n > 12:
        ax.tick_params(axis="x", labelrotation=60)
        for label in ax.get_xticklabels():
            label.set_horizontalalignment("right")
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
    fig = plt.figure(figsize=(5.8, 2.9), dpi=120)
    fig.patch.set_facecolor("white")
    fig.text(0.5, 0.93, title, ha="center", va="top", fontsize=10)
    ax = fig.add_axes([0.02, 0.06, 0.40, 0.74])
    ax.set_facecolor("white")
    legend_ax = fig.add_axes([0.44, 0.06, 0.54, 0.74])
    legend_ax.set_axis_off()
    if not total:
        ax.text(0.5, 0.5, "Нет данных", ha="center", va="center")
        ax.set_axis_off()
        return fig
    palette = colors or [DONUT_COLORS[i % len(DONUT_COLORS)] for i in range(len(values))]
    wedges, _ = ax.pie(
        values,
        colors=palette,
        startangle=90,
        wedgeprops={"width": 0.48, "edgecolor": "white", "linewidth": 1.2},
    )
    ax.set_aspect("equal")
    labels = []
    for name, count in slices:
        pct = round(count / total * 100)
        labels.append(f"{name} — {count} ({pct}%)")
    legend_ax.legend(
        wedges,
        labels,
        loc="center left",
        frameon=False,
        fontsize=8,
        labelspacing=0.42,
        handlelength=1.0,
        borderaxespad=0,
    )
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


def report_quartile_png(rows: list[dict], title: str = "Квартили журналов SCImago") -> bytes:
    slices = [(row["Квартиль"], int(row["Публикаций"])) for row in rows if int(row["Публикаций"])]
    colors = [QUARTILE_COLORS.get(name, "#adb5bd") for name, _ in slices]
    return report_area_png(slices, title=title, colors=colors)
