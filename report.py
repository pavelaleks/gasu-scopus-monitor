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
    authid = (author.get("authid") or "").strip()
    if authid.isdigit():
        return f"id|{authid}"
    surname = (author.get("surname") or "").strip()
    if not surname:
        return None
    initials = _author_initials(author)
    first = next((ch.lower() for ch in initials if ch.isalpha()), "")
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
                    "authid": "",
                    "orcid": "",
                    "h_index": None,
                    "documents": None,
                    "cited_by": None,
                    "profile_affil": "",
                }
                buckets[key] = bucket
            bucket["names"][author_display_name(author)] += 1
            bucket["n"] += 1
            if author.get("authid"):
                bucket["authid"] = author.get("authid") or ""
            if author.get("orcid"):
                bucket["orcid"] = author.get("orcid") or ""
            if author.get("profile_affil"):
                bucket["profile_affil"] = author.get("profile_affil") or ""
            for key in ("h_index", "documents", "cited_by"):
                if author.get(key) is not None:
                    bucket[key] = author.get(key)
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
                "Author ID": bucket.get("authid") or "",
                "ORCID": bucket.get("orcid") or "",
                "h-индекс": "" if bucket.get("h_index") is None else bucket.get("h_index"),
                "Документов": "" if bucket.get("documents") is None else bucket.get("documents"),
                "Цитирований": "" if bucket.get("cited_by") is None else bucket.get("cited_by"),
                "Аффилиация": bucket.get("profile_affil") or "",
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


def _empty_author_bucket() -> dict:
    return {
        "names": Counter(),
        "authid": "",
        "flags": set(),
        "gasu_n": 0,
        "Q1": 0,
        "Q2": 0,
        "Q3": 0,
        "Q4": 0,
        "none": 0,
        "surname": "",
        "given": "",
        "initials": "",
        "sample_scopus_id": "",
        "orcid": "",
        "h_index": None,
        "documents": None,
        "cited_by": None,
        "citations": None,
        "profile_affil": "",
    }


def _add_quartile(bucket: dict, record: dict) -> None:
    quartile = record.get("scimago_quartile") or "Нет"
    if quartile not in {"Q1", "Q2", "Q3", "Q4"}:
        bucket["none"] += 1
    else:
        bucket[quartile] += 1


def _candidate_row(bucket: dict, *, account: str) -> dict:
    name = max(bucket["names"], key=lambda item: (len(item), bucket["names"][item]))
    total = int(bucket.get("total") or bucket["gasu_n"])
    gasu_n = int(bucket["gasu_n"])
    parts = name.split(None, 1)
    return {
        "Автор": name,
        "authid": bucket.get("authid") or "",
        "surname": bucket.get("surname") or (parts[0] if parts else ""),
        "given": bucket.get("given") or "",
        "initials": bucket.get("initials") or (parts[1] if len(parts) > 1 else ""),
        "sample_scopus_id": bucket.get("sample_scopus_id") or "",
        "ORCID": bucket.get("orcid") or "",
        "h-индекс": "" if bucket.get("h_index") is None else bucket.get("h_index"),
        "Документов": "" if bucket.get("documents") is None else bucket.get("documents"),
        "Цитирований": "" if bucket.get("cited_by") is None else bucket.get("cited_by"),
        "Аффилиация": bucket.get("profile_affil") or "",
        "Всего Scopus": total,
        "С ГАГУ": gasu_n,
        "Q1": bucket["Q1"],
        "Q2": bucket["Q2"],
        "Q3": bucket["Q3"],
        "Q4": bucket["Q4"],
        "Без квартиля": bucket["none"],
        "Учёт": account,
    }


def _merge_author_bucket(dest: dict, src: dict) -> None:
    dest["names"].update(src["names"])
    dest["gasu_n"] += src["gasu_n"]
    dest["Q1"] += src["Q1"]
    dest["Q2"] += src["Q2"]
    dest["Q3"] += src["Q3"]
    dest["Q4"] += src["Q4"]
    dest["none"] += src["none"]
    dest["flags"].update(src["flags"])
    if src.get("authid") and not dest.get("authid"):
        dest["authid"] = src["authid"]
    if src.get("surname") and not dest.get("surname"):
        dest["surname"] = src["surname"]
    if src.get("given") and not dest.get("given"):
        dest["given"] = src["given"]
    if src.get("initials") and not dest.get("initials"):
        dest["initials"] = src["initials"]
    if src.get("sample_scopus_id") and not dest.get("sample_scopus_id"):
        dest["sample_scopus_id"] = src["sample_scopus_id"]
    if src.get("orcid") and not dest.get("orcid"):
        dest["orcid"] = src["orcid"]
    if src.get("profile_affil") and not dest.get("profile_affil"):
        dest["profile_affil"] = src["profile_affil"]
    for key in ("h_index", "documents", "cited_by", "citations"):
        if dest.get(key) is None and src.get(key) is not None:
            dest[key] = src[key]


def _coalesce_author_buckets(buckets: dict[str, dict]) -> None:
    """Склеить одного человека: с ID и без, «Alekseev P.» и «Alekseev P.V.»."""
    by_surname: dict[str, list[str]] = {}
    for key, bucket in buckets.items():
        if not bucket["names"]:
            continue
        name = max(bucket["names"], key=lambda item: (len(item), bucket["names"][item]))
        surname = name.split()[0].lower()
        by_surname.setdefault(surname, []).append(key)
    for keys in by_surname.values():
        id_keys = [key for key in keys if key.startswith("id|")]
        other = [key for key in keys if not key.startswith("id|")]
        if len(id_keys) == 1 and other:
            dest = buckets[id_keys[0]]
            for src_key in other:
                _merge_author_bucket(dest, buckets.pop(src_key))
            continue
        if id_keys:
            continue
        initials = {key.split("|", 1)[-1] for key in keys if "|" in key}
        initials.discard("")
        if len(keys) > 1 and len(initials) <= 1:
            dest_key = next((key for key in keys if key.split("|", 1)[-1]), keys[0])
            dest = buckets[dest_key]
            for src_key in keys:
                if src_key != dest_key:
                    _merge_author_bucket(dest, buckets.pop(src_key))


def rsf_candidates(gasu_records: list[dict]) -> list[dict]:
    """Кто связан с ГАГУ: есть хотя бы в одной статье вуза. Аффилиацию автора не фильтруем."""
    buckets: dict[str, dict] = {}
    for rec in gasu_records:
        seen: set[str] = set()
        for author in rec.get("authors") or []:
            name = author_display_name(author)
            if rsf_name_excluded(name) or rsf_name_excluded(author.get("surname") or ""):
                continue
            key = author_merge_key(author)
            if not key or key in seen:
                continue
            seen.add(key)
            bucket = buckets.get(key)
            if bucket is None:
                bucket = _empty_author_bucket()
                buckets[key] = bucket
            bucket["names"][name or (author.get("surname") or "")] += 1
            if author.get("surname") and not bucket.get("surname"):
                bucket["surname"] = (author.get("surname") or "").strip()
            if author.get("given"):
                bucket["given"] = (author.get("given") or "").strip()
            if author.get("initials"):
                bucket["initials"] = (author.get("initials") or "").strip()
            authid = (author.get("authid") or "").strip()
            if authid.isdigit():
                bucket["authid"] = authid
            if author.get("orcid") and not bucket.get("orcid"):
                bucket["orcid"] = author.get("orcid") or ""
            if author.get("profile_affil") and not bucket.get("profile_affil"):
                bucket["profile_affil"] = author.get("profile_affil") or ""
            for key in ("h_index", "documents", "cited_by", "citations"):
                if bucket.get(key) is None and author.get(key) is not None:
                    bucket[key] = author.get(key)
            sid = (rec.get("scopus_id") or "").strip()
            if sid and not bucket.get("sample_scopus_id"):
                bucket["sample_scopus_id"] = sid
            bucket["flags"].add(author.get("from_gasu"))
            bucket["gasu_n"] += 1
            _add_quartile(bucket, rec)
    _coalesce_author_buckets(buckets)
    rows = []
    for bucket in buckets.values():
        bucket["total"] = bucket["gasu_n"]
        rows.append(_candidate_row(bucket, account="только статьи с ГАГУ"))
    rows.sort(key=lambda row: (-row["Всего Scopus"], -row["С ГАГУ"], row["Автор"].lower()))
    return rows


def apply_author_total(candidate: dict, total: int, account: str = "все статьи автора") -> dict:
    """Число всех статей Scopus в окне (ответ API), без фильтра по аффилиации."""
    known_gasu = int(candidate.get("С ГАГУ") or 0)
    candidate["Всего Scopus"] = max(int(total), known_gasu)
    candidate["Учёт"] = account
    return candidate


def rsf_eligibility_rows(candidates: list[dict], min_papers: int) -> list[dict]:
    hide = {"surname", "given", "initials", "sample_scopus_id"}
    order = (
        "Автор",
        "Author ID",
        "ORCID",
        "h-индекс",
        "Документов",
        "Цитирований",
        "Аффилиация",
        "Всего Scopus",
        "С ГАГУ",
        "Q1",
        "Q2",
        "Q3",
        "Q4",
        "Без квартиля",
        "Учёт",
    )
    rows = []
    for row in candidates:
        if int(row.get("Всего Scopus") or 0) < min_papers:
            continue
        if rsf_name_excluded(str(row.get("Автор") or "")):
            continue
        display = {k: v for k, v in row.items() if k not in hide}
        authid = display.pop("authid", "") or ""
        display["Author ID"] = authid
        rows.append({key: display.get(key, "") for key in order})
    rows.sort(key=lambda row: (-int(row["Всего Scopus"] or 0), -int(row["С ГАГУ"] or 0), str(row["Автор"]).lower()))
    return rows


def rsf_applicants(records: list[dict], min_papers: int) -> tuple[list[dict], bool]:
    """Запасной путь без добора по Author ID: порог по статьям ГАГУ."""
    return rsf_eligibility_rows(rsf_candidates(records), min_papers), False


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
