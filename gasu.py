"""Идентификация аффилиации ГАГУ в запросах и ответах Scopus.

Поиск опирается на AF-ID: Scopus считает документ принадлежащим организации,
если ГАГУ указан хотя бы у одного автора, в том числе среди нескольких
аффилиаций. Клиент не должен отбрасывать такие записи по урезанному полю
affiliation в Search API.
"""

from __future__ import annotations

AFFILIATION_ID = "60105869"
GASU_PREFERRED_NAME = "Gorno-Altaisk State University"
AFFILIATION_NAMES = [
    "Gorno-Altaisk State University",
    "GORNO ALTAISK STATE UNIV",
    "GORNO-ALTAYSK  STATE UNIV",
    "GORNO-ALTAY STATE UNIV",
    "GASU",
    "Gorno Alta State Univ",
    "Gorno-Altaysk State University",
    "Gorno Altay State Univ",
]
AFFILIATION_NAME_SET = {" ".join(name.strip().lower().split()) for name in AFFILIATION_NAMES}
GASU_NAME_MARKERS = (
    "gorno-altaisk",
    "gorno altaisk",
    "gorno-altaysk",
    "gorno altaysk",
    "gorno-altay state",
    "gorno altay state",
    "gorno alta state",
    "горно-алтайск",
    "горно алтайск",
    "горно-алтайский государственный",
)


def quoted(value: str) -> str:
    cleaned = (value or "").strip().replace('"', "")
    return f'"{cleaned}"'


def gasu_affiliation_clause() -> str:
    """Документы, где ГАГУ есть хотя бы как одна из аффилиаций."""
    names = " OR ".join(f"AFFIL({quoted(name)})" for name in AFFILIATION_NAMES)
    return f"(AF-ID({AFFILIATION_ID}) OR {names})"


def query_targets_gasu(query: str) -> bool:
    return f"AF-ID({AFFILIATION_ID})" in (query or "")


def build_query(
    mode: str,
    last: str,
    orcid: str,
    date_filter: dict | None,
    only_gasu: bool,
) -> str:
    affil_query = gasu_affiliation_clause()

    if mode == "Мониторинг ГАГУ":
        base = affil_query
        if date_filter:
            if date_filter["mode"] == "current":
                year = date_filter["year"]
                base = f"{base} AND PUBYEAR IS {year}"
            else:
                year_start = date_filter["year_start"]
                year_end = date_filter["year_end"]
                base = f"{base} AND PUBYEAR > {year_start - 1} AND PUBYEAR < {year_end + 1}"
        return base

    if orcid:
        base = f"ORCID({quoted(orcid)})"
    else:
        base = f"AUTH({quoted(last)})"

    if date_filter:
        year_start = date_filter["year_start"]
        year_end = date_filter["year_end"]
        base = f"{base} AND PUBYEAR > {year_start - 1} AND PUBYEAR < {year_end + 1}"

    if only_gasu:
        base = f"{base} AND {affil_query}"

    return base


def normalize_affiliation_name(name: str) -> str:
    return " ".join((name or "").strip().lower().split())


def is_gasu_name(name: str) -> bool:
    norm = normalize_affiliation_name(name)
    if not norm:
        return False
    if norm in AFFILIATION_NAME_SET:
        return True
    return any(marker in norm for marker in GASU_NAME_MARKERS)


def affiliation_items(entry: dict) -> list[dict]:
    affil = entry.get("affiliation")
    if isinstance(affil, list):
        return [item for item in affil if isinstance(item, dict)]
    if isinstance(affil, dict):
        return [affil]
    return []


def afids_from_value(value: object) -> set[str]:
    found: set[str] = set()
    if value is None:
        return found
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        text = str(int(value))
        if text.isdigit():
            found.add(text)
        return found
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            found.add(text)
        return found
    if isinstance(value, dict):
        for key in ("$", "@id", "@afid", "id", "afid"):
            if key in value:
                found.update(afids_from_value(value[key]))
        return found
    if isinstance(value, list):
        for item in value:
            found.update(afids_from_value(item))
    return found


def collect_afids(entry: dict) -> set[str]:
    ids: set[str] = set()
    for item in affiliation_items(entry):
        ids.update(afids_from_value(item.get("afid")))
        ids.update(afids_from_value(item.get("affiliation-id")))
    authors = entry.get("author")
    if isinstance(authors, dict):
        authors = [authors]
    if isinstance(authors, list):
        for author in authors:
            if isinstance(author, dict):
                ids.update(afids_from_value(author.get("afid")))
    return ids


def affiliation_names(entry: dict) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for item in affiliation_items(entry):
        name = (
            item.get("affilname")
            or item.get("affiliation-name")
            or item.get("name")
            or ""
        ).strip()
        if not name:
            continue
        key = normalize_affiliation_name(name)
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    affil = entry.get("affiliation")
    if not names and isinstance(affil, str) and affil.strip():
        names.append(affil.strip())
    return names


def has_gasu_affiliation(entry: dict) -> bool:
    if AFFILIATION_ID in collect_afids(entry):
        return True
    return any(is_gasu_name(name) for name in affiliation_names(entry))


def format_affiliations(entry: dict, ensure_gasu: bool = False) -> str:
    names = affiliation_names(entry)
    known_gasu = has_gasu_affiliation(entry) or ensure_gasu
    if known_gasu and not any(is_gasu_name(name) for name in names):
        names = [GASU_PREFERRED_NAME, *names]
    elif any(is_gasu_name(name) for name in names):
        names = sorted(names, key=lambda name: 0 if is_gasu_name(name) else 1)
    return "; ".join(names)
