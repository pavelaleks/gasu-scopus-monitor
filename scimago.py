"""Квартиль и SJR журнала по ISSN из открытого дампа SCImago (sjrdata)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from subjects import normalize_issn

DATA_DIR = Path(__file__).with_name("data")
SLIM_PATH = DATA_DIR / "scimago_issn.parquet"
META_PATH = DATA_DIR / "scimago_meta.json"
RDA_URL = "https://github.com/ikashnitsky/sjrdata/raw/refs/heads/master/data/sjr_journals.rda"
RDA_PATH = DATA_DIR / "sjr_journals.rda"
MIN_YEAR = 2018
REFRESH_MONTH_DAYS = ((6, 20), (12, 20))
QUARTILES = ("Q1", "Q2", "Q3", "Q4")
UNKNOWN_QUARTILE = "Нет"


@dataclass(frozen=True)
class ScimagoHit:
    quartile: str
    sjr: float | None
    sjr_year: int
    matched: bool


def split_issns(raw) -> list[str]:
    text = "" if raw is None or (isinstance(raw, float) and pd.isna(raw)) else str(raw)
    found: list[str] = []
    seen: set[str] = set()
    for part in text.replace(";", ",").split(","):
        issn = normalize_issn(part)
        if issn and issn not in seen:
            seen.add(issn)
            found.append(issn)
    return found


def _clean_quartile(value) -> str:
    text = str(value or "").strip().upper()
    if text in QUARTILES:
        return text
    return ""


def _clean_sjr(value) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, str):
        text = value.strip().replace(",", ".")
        if not text or text == "-":
            return None
        try:
            return round(float(text), 3)
        except ValueError:
            return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number):
        return None
    return round(number, 3)


def slim_from_frame(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.copy()
    work.columns = [str(name).lower().replace(" ", "_") for name in work.columns]
    if "year" not in work.columns or "issn" not in work.columns:
        raise ValueError("В дампе SCImago нет колонок year/issn.")
    work["year"] = pd.to_numeric(work["year"], errors="coerce")
    work = work[work["year"] >= MIN_YEAR]
    work["quartile"] = (
        work["sjr_best_quartile"].map(_clean_quartile) if "sjr_best_quartile" in work.columns else ""
    )
    if "sjr" in work.columns:
        work["sjr"] = work["sjr"].map(_clean_sjr)
    else:
        work["sjr"] = None
    work["issn_list"] = work["issn"].map(split_issns)
    work = work.explode("issn_list")
    work["issn"] = work["issn_list"]
    work = work[work["issn"].notna() & (work["issn"] != "")]
    work = work[(work["quartile"] != "") | work["sjr"].notna()]
    slim = work[["issn", "year", "quartile", "sjr"]].drop_duplicates(subset=["issn", "year"], keep="last")
    slim["year"] = slim["year"].astype("int16")
    return slim.sort_values(["issn", "year"]).reset_index(drop=True)


class ScimagoIndex:
    def __init__(self, slim: pd.DataFrame):
        self.slim = slim
        self.max_year = int(slim["year"].max()) if not slim.empty else 0
        self._by_issn: dict[str, dict[int, tuple[str, float | None]]] = {}
        for row in slim.itertuples(index=False):
            years = self._by_issn.setdefault(row.issn, {})
            years[int(row.year)] = (str(row.quartile or ""), None if pd.isna(row.sjr) else float(row.sjr))

    def lookup(self, issns: list[str], paper_year: int | None) -> ScimagoHit | None:
        if not issns or not self._by_issn:
            return None
        for issn in issns:
            years = self._by_issn.get(issn)
            if not years:
                continue
            if paper_year and paper_year in years:
                quartile, sjr = years[paper_year]
                return ScimagoHit(quartile=quartile or UNKNOWN_QUARTILE, sjr=sjr, sjr_year=paper_year, matched=True)
            if paper_year and paper_year > self.max_year and self.max_year in years:
                quartile, sjr = years[self.max_year]
                return ScimagoHit(
                    quartile=quartile or UNKNOWN_QUARTILE,
                    sjr=sjr,
                    sjr_year=self.max_year,
                    matched=False,
                )
        return None


def load_slim(path: Path = SLIM_PATH) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["issn", "year", "quartile", "sjr"])
    return pd.read_parquet(path)


def save_slim(frame: pd.DataFrame, path: Path = SLIM_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    max_year = int(frame["year"].max()) if not frame.empty else 0
    META_PATH.write_text(
        json.dumps(
            {
                "built_at": datetime.now(timezone.utc).date().isoformat(),
                "max_year": max_year,
                "source": "sjrdata",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def load_meta() -> dict:
    if META_PATH.exists():
        try:
            payload = json.loads(META_PATH.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def next_refresh_date(today: date | None = None) -> date:
    today = today or date.today()
    for month, day in REFRESH_MONTH_DAYS:
        candidate = date(today.year, month, day)
        if candidate > today:
            return candidate
    month, day = REFRESH_MONTH_DAYS[0]
    return date(today.year + 1, month, day)


def format_ru_date(value: date | None) -> str:
    if value is None:
        return "—"
    return value.strftime("%d.%m.%Y")


def lookup_built_on() -> date | None:
    raw = str(load_meta().get("built_at") or "")[:10]
    if raw:
        try:
            return date.fromisoformat(raw)
        except ValueError:
            pass
    return None


def download_rda(url: str = RDA_URL, dest: Path = RDA_PATH) -> Path:
    import requests

    dest.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(url, timeout=180, stream=True)
    response.raise_for_status()
    with dest.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=1024 * 256):
            if chunk:
                handle.write(chunk)
    return dest


def frame_from_rda(path: Path = RDA_PATH) -> pd.DataFrame:
    import rdata

    parsed = rdata.parser.parse_file(path)
    converted = rdata.conversion.convert(parsed)
    if isinstance(converted, dict):
        frame = next(iter(converted.values()))
    else:
        frame = converted
    if not isinstance(frame, pd.DataFrame):
        frame = pd.DataFrame(frame)
    return frame


def build_slim(rda_path: Path | None = None, *, refresh: bool = False) -> pd.DataFrame:
    source = rda_path or RDA_PATH
    if refresh or not source.exists():
        download_rda(dest=source)
    slim = slim_from_frame(frame_from_rda(source))
    save_slim(slim)
    return slim


_INDEX: ScimagoIndex | None = None


def get_index(slim: pd.DataFrame | None = None) -> ScimagoIndex:
    global _INDEX
    if slim is not None:
        _INDEX = ScimagoIndex(slim)
        return _INDEX
    if _INDEX is None:
        _INDEX = ScimagoIndex(load_slim())
    return _INDEX


def attach_scimago(records: list[dict], index: ScimagoIndex | None = None) -> None:
    lookup = index or get_index()
    for rec in records:
        year_raw = str(rec.get("year") or "").strip()
        paper_year = int(year_raw) if year_raw.isdigit() else None
        hit = lookup.lookup(rec.get("issns") or [], paper_year)
        if hit is None:
            rec["scimago_quartile"] = UNKNOWN_QUARTILE
            rec["scimago_sjr"] = ""
            rec["scimago_year"] = ""
            rec["scimago_matched"] = False
            continue
        rec["scimago_quartile"] = hit.quartile
        rec["scimago_sjr"] = "" if hit.sjr is None else hit.sjr
        rec["scimago_year"] = hit.sjr_year
        rec["scimago_matched"] = hit.matched


def format_quartile_cell(record: dict) -> str:
    quartile = record.get("scimago_quartile") or UNKNOWN_QUARTILE
    year = record.get("scimago_year")
    if quartile == UNKNOWN_QUARTILE or not year:
        return UNKNOWN_QUARTILE
    if record.get("scimago_matched"):
        return str(quartile)
    return f"{quartile} ({year})"


def quartile_share_rows(records: list[dict], year: str | None = None) -> list[dict]:
    from collections import Counter

    subset = records
    if year:
        subset = [rec for rec in records if str(rec.get("year") or "") == str(year)]
    counts = Counter()
    for rec in subset:
        value = rec.get("scimago_quartile") or UNKNOWN_QUARTILE
        if value not in QUARTILES:
            value = UNKNOWN_QUARTILE
        counts[value] += 1
    total = len(subset)
    rows = []
    for label in QUARTILES:
        current = counts.get(label, 0)
        share = round(current / total * 100, 1) if total else 0.0
        rows.append({"Квартиль": label, "Публикаций": current, "Доля": f"{share:g}%"})
    unknown = counts.get(UNKNOWN_QUARTILE, 0)
    if unknown:
        share = round(unknown / total * 100, 1) if total else 0.0
        rows.append({"Квартиль": UNKNOWN_QUARTILE, "Публикаций": unknown, "Доля": f"{share:g}%"})
    return rows


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Rebuild the SCImago ISSN lookup from sjrdata.")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Download the sjrdata dump again even if a local copy exists.",
    )
    args = parser.parse_args()
    print("Building SCImago ISSN lookup from sjrdata...")
    slim = build_slim(refresh=args.refresh)
    print(f"Saved {len(slim)} rows, years {int(slim['year'].min())}–{int(slim['year'].max())} -> {SLIM_PATH}")
