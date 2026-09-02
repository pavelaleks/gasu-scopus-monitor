"""Идентификация аффилиации ГАГУ в запросах и ответах Scopus.

Точность важнее полноты: короткий AFFIL("GASU") и непроверенный AF-ID
подмешивали сотни чужих статей (Innopolis, МФТИ и т.д.).

Документ относится к ГАГУ, только если в ответе есть узнаваемое название
или город Горно-Алтайска — не потому что совпал какой-то affiliation id.
Scopus индексирует все аффилиации документа, поэтому AFFILORG по полному
имени находит и случаи «ГАГУ — одна из нескольких организаций».
"""

from __future__ import annotations

import re
from urllib.parse import quote

# Исторический id из первой версии приложения. Не используем в запросе:
# по нему Scopus отдавал чужие организации, а код ещё и подписывал их как ГАГУ.
AFFILIATION_ID = "60105869"
GASU_FOUNDED_YEAR = 1993
GASU_PREFERRED_NAME = "Gorno-Altaisk State University"
AFFILIATION_NAMES = [
    "Gorno-Altaisk State University",
    "Gorno-Altaysk State University",
    "Gorno-Altai State University",
    "Gorno-Altaisk State Univ",
    "Gorno-Altaysk State Univ",
    "GORNO ALTAISK STATE UNIV",
    "GORNO-ALTAYSK STATE UNIV",
    "Горно-Алтайский государственный университет",
]
AFFILIATION_NAME_SET = {" ".join(name.strip().lower().split()) for name in AFFILIATION_NAMES} | {
    "gasu",
}
GASU_NAME_MARKERS = (
    "gorno-altaisk state",
    "gorno altaisk state",
    "gorno-altaysk state",
    "gorno altaysk state",
    "gorno-altai state",
    "gorno altai state",
    "gorno-altay state univ",
    "gorno altay state univ",
    "gorno alta state univ",
    "горно-алтайский государственный университет",
    "горно алтайский государственный университет",
    "горно-алтайск. гос",
)
GASU_CITY_MARKERS = (
    "gorno-altaysk",
    "gorno-altaisk",
    "gorno altaysk",
    "gorno altaisk",
    "горно-алтайск",
    "горно алтайск",
)
UNIVERSITY_TOKENS = ("univ", "university", "университет", "госуниверситет")


SCOPUS_SEARCH_CAP = 5000


def quoted(value: str) -> str:
    cleaned = (value or "").strip().replace('"', "")
    return f'"{cleaned}"'


def more_scopus_pages(
    *,
    page_len: int,
    page_size: int,
    next_start: int,
    reported_total: int | None,
    hard_cap: int = SCOPUS_SEARCH_CAP,
) -> bool:
    """Нужна ли следующая страница Scopus Search.

    COMPLETE-выдача часто ставит totalResults равным размеру первой страницы
    (25). Тогда цикл «start >= total» обрывался на самых новых статьях —
    за «последние 5 лет» оставался только текущий год.
    """
    if page_len <= 0 or page_len < page_size:
        return False
    if next_start >= hard_cap:
        return False
    if reported_total and reported_total > page_size and next_start >= reported_total:
        return False
    return True


def normalize_orcid(value: str) -> str:
    text = (value or "").strip()
    lower = text.lower()
    for prefix in ("https://orcid.org/", "http://orcid.org/"):
        if lower.startswith(prefix):
            text = text[len(prefix) :]
            break
    return text.strip().replace(" ", "")


_ORCID_RE = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$", re.IGNORECASE)

_RU_TO_LAT = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "i",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "kh",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "shch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}


def orcid_identity(value: str) -> str:
    oid = normalize_orcid(value or "")
    return oid.lower() if _ORCID_RE.match(oid) else ""


def fold_surname(surname: str) -> str:
    """Kyrov и Кыров — одна фамилия для склейки авторов."""
    text = (surname or "").strip().lower().replace("ё", "е")
    if not text:
        return ""
    if any("а" <= ch <= "я" or ch == "ё" for ch in text):
        return "".join(_RU_TO_LAT.get(ch, ch) for ch in text)
    return text


def name_has_cyrillic(name: str) -> bool:
    return any("а" <= ch.lower() <= "я" or ch.lower() == "ё" for ch in name or "")


def parse_author_query(value: str) -> dict:
    """Одно поле: ORCID, Scopus Author ID или фамилия."""
    text = (value or "").strip()
    empty = {"kind": "", "orcid": "", "authid": "", "surname": ""}
    if not text:
        return empty
    orcid = normalize_orcid(text)
    if _ORCID_RE.match(orcid):
        return {"kind": "orcid", "orcid": orcid, "authid": "", "surname": ""}
    compact = text.replace(" ", "")
    digits = "".join(ch for ch in compact if ch.isdigit())
    if compact.isdigit() and len(digits) >= 6:
        return {"kind": "au-id", "orcid": "", "authid": digits, "surname": ""}
    surname = text.replace(",", " ").split()[0]
    return {"kind": "surname", "orcid": "", "authid": "", "surname": surname}


def author_retrieval_urls(authid: str = "", orcid: str = "") -> list[str]:
    """Author Retrieval принимает и Author ID, и ORCID — без предварительного Author Search."""
    urls: list[str] = []
    ident = "".join(ch for ch in str(authid or "") if ch.isdigit())
    if ident:
        urls.append(f"https://api.elsevier.com/content/author/author_id/{ident}")
    oid = normalize_orcid(orcid)
    if oid:
        urls.append(f"https://api.elsevier.com/content/author/orcid/{oid}")
    return urls


def gasu_affiliation_clause() -> str:
    """Только узнаваемые имена вуза, без акронима GASU и без AF-ID."""
    names = " OR ".join(f"AFFILORG({quoted(name)})" for name in AFFILIATION_NAMES)
    return f"({names})"


def query_targets_gasu(query: str) -> bool:
    text = query or ""
    return "AFFILORG(" in text or "Gorno-Altaisk" in text or "Горно-Алтайск" in text


def build_query(
    mode: str,
    last: str,
    orcid: str,
    date_filter: dict | None,
    only_gasu: bool,
) -> str:
    affil_query = gasu_affiliation_clause()

    if mode in ("Мониторинг ГАГУ", "РНФ"):
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
        base = f"ORCID({quoted(normalize_orcid(orcid))})"
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


def is_gasu_city(city: str) -> bool:
    norm = normalize_affiliation_name(city)
    if not norm:
        return False
    return any(marker in norm for marker in GASU_CITY_MARKERS)


def looks_like_university(name: str) -> bool:
    norm = normalize_affiliation_name(name)
    return any(token in norm for token in UNIVERSITY_TOKENS)


def affiliation_items(entry: dict) -> list[dict]:
    items: list[dict] = []
    affil = entry.get("affiliation")
    if isinstance(affil, list):
        items.extend(item for item in affil if isinstance(item, dict))
    elif isinstance(affil, dict):
        items.append(affil)

    authors = entry.get("author")
    if isinstance(authors, dict):
        authors = [authors]
    if isinstance(authors, list):
        for author in authors:
            if not isinstance(author, dict):
                continue
            author_aff = author.get("affiliation")
            if isinstance(author_aff, list):
                items.extend(item for item in author_aff if isinstance(item, dict))
            elif isinstance(author_aff, dict):
                items.append(author_aff)
    return items


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


def entry_belongs_to_gasu(entry: dict) -> bool:
    """Есть текстовое доказательство ГАГУ в ответе API — не только AF-ID."""
    for name in affiliation_names(entry):
        if is_gasu_name(name):
            return True
    for item in affiliation_items(entry):
        city = (item.get("affiliation-city") or item.get("city") or "").strip()
        name = (item.get("affilname") or item.get("affiliation-name") or item.get("name") or "").strip()
        if is_gasu_city(city) and (is_gasu_name(name) or looks_like_university(name)):
            return True
    return False


def has_gasu_affiliation(entry: dict) -> bool:
    return entry_belongs_to_gasu(entry)


def _affiliation_dict_is_gasu(item: dict) -> bool:
    name = (
        item.get("affilname")
        or item.get("affiliation-name")
        or item.get("name")
        or ""
    ).strip()
    city = (item.get("affiliation-city") or item.get("city") or "").strip()
    if is_gasu_name(name):
        return True
    return bool(is_gasu_city(city) and (is_gasu_name(name) or looks_like_university(name)))


def scopus_authid(author: dict) -> str:
    if not isinstance(author, dict):
        return ""

    def from_value(raw: object) -> str:
        if isinstance(raw, dict):
            for nested in ("$", "@id", "@auid", "#text"):
                found = from_value(raw.get(nested))
                if found:
                    return found
            return ""
        text = str(raw or "").strip()
        lower = text.lower()
        marker = "author_id/"
        if marker in lower:
            rest = text[lower.index(marker) + len(marker) :]
            digits = []
            for ch in rest:
                if ch.isdigit():
                    digits.append(ch)
                elif digits:
                    break
            if len(digits) >= 6:
                return "".join(digits)
        digits = "".join(ch for ch in text if ch.isdigit())
        if len(digits) >= 6:
            return digits
        return ""

    for key in ("authid", "auid", "@auid", "author-url", "@href"):
        found = from_value(author.get(key))
        if found:
            return found
    return ""


def author_id_query(authid: str, year_start: int, year_end: int) -> str:
    ident = "".join(ch for ch in str(authid or "") if ch.isdigit())
    return f"AU-ID({ident}) AND PUBYEAR > {year_start - 1} AND PUBYEAR < {year_end + 1}"


def orcid_id_query(orcid: str, year_start: int, year_end: int) -> str:
    ident = normalize_orcid(orcid)
    return f"ORCID({quoted(ident)}) AND PUBYEAR > {year_start - 1} AND PUBYEAR < {year_end + 1}"


def first_initial(initials: str = "", given: str = "") -> str:
    for text in (initials, given):
        for ch in text or "":
            if ch.isalpha():
                return ch.upper()
    return ""


def gasu_author_affil_clause() -> str:
    """Author Search: короткие AFFIL, как на карточке автора Scopus."""
    names = (
        "Gorno-Altaisk State University",
        "Gorno-Altaysk State University",
        "Gorno-Altaisk",
        "Gorno-Altaysk",
        "Горно-Алтайск",
    )
    return "(" + " OR ".join(f"AFFIL({quoted(name)})" for name in names) + ")"


def author_profile_query(
    surname: str,
    initials: str = "",
    given: str = "",
    *,
    with_initial: bool | None = None,
    gasu_only: bool = True,
) -> str:
    """Поиск профиля: фамилия, при необходимости первая буква имени и аффилиация ГАГУ."""
    query = f"AUTHLAST({quoted(surname)})"
    initial = first_initial(initials, given)
    if with_initial is None:
        with_initial = bool(initial)
    if with_initial and initial:
        query += f" AND AUTHFIRST({initial})"
    if gasu_only:
        query += f" AND {gasu_author_affil_clause()}"
    return query


def author_papers_query(authid: str, date_filter: dict | None, only_gasu: bool) -> str:
    ident = "".join(ch for ch in str(authid or "") if ch.isdigit())
    base = f"AU-ID({ident})"
    if date_filter:
        if date_filter.get("mode") == "current":
            base = f"{base} AND PUBYEAR IS {date_filter['year']}"
        else:
            year_start = date_filter["year_start"]
            year_end = date_filter["year_end"]
            base = f"{base} AND PUBYEAR > {year_start - 1} AND PUBYEAR < {year_end + 1}"
    if only_gasu:
        base = f"{base} AND {gasu_affiliation_clause()}"
    return base


def author_search_id(entry: dict) -> str:
    if not isinstance(entry, dict):
        return ""
    ident = str(entry.get("dc:identifier") or "")
    digits = "".join(ch for ch in ident if ch.isdigit())
    if len(digits) >= 6:
        return digits
    return scopus_authid(entry)


def _field_text(value: object) -> str:
    if isinstance(value, dict):
        return str(value.get("$") or value.get("#text") or "").strip()
    return str(value or "").strip()


def _field_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    text = _field_text(value).replace(",", "").replace(" ", "")
    if text.isdigit():
        return int(text)
    return None


def _compose_current_affiliation(*parts: object) -> str:
    seen: list[str] = []
    for part in parts:
        text = _field_text(part)
        if not text:
            continue
        lowered = text.lower()
        if any(lowered in existing.lower() or existing.lower() in lowered for existing in seen):
            continue
        seen.append(text)
    return ", ".join(seen)


def parse_author_search_profile(entry: dict) -> dict:
    """Поля Author Search: ID, ORCID, документы, цитирования, текущая аффилиация."""
    if not isinstance(entry, dict):
        return {}
    pref = entry.get("preferred-name")
    if not isinstance(pref, dict):
        pref = {}
    aff = entry.get("affiliation-current") or {}
    if isinstance(aff, list):
        aff = aff[0] if aff else {}
    if not isinstance(aff, dict):
        aff = {}
    affil = _compose_current_affiliation(
        aff.get("affiliation-name") or aff.get("affilname"),
        aff.get("affiliation-city"),
        aff.get("affiliation-country"),
    )
    return {
        "authid": author_search_id(entry),
        "orcid": _field_text(entry.get("orcid")),
        "documents": _field_int(entry.get("document-count")),
        "cited_by": _field_int(entry.get("cited-by-count")),
        "citations": _field_int(entry.get("citation-count") or entry.get("citations-count")),
        "h_index": _field_int(entry.get("h-index")),
        "profile_affil": affil,
        "surname": _field_text(pref.get("surname") or entry.get("surname")),
        "given": _field_text(pref.get("given-name") or entry.get("given-name")),
        "initials": _field_text(pref.get("initials") or entry.get("initials")),
    }


def parse_author_retrieval(payload: dict) -> dict:
    """Поля Author Retrieval: h-index, ORCID, документы, цитирования."""
    if not isinstance(payload, dict):
        return {}
    inner = payload.get("author-retrieval-response")
    if isinstance(inner, list):
        inner = inner[0] if inner else {}
    if not isinstance(inner, dict):
        inner = {}
    core = inner.get("coredata") if isinstance(inner.get("coredata"), dict) else {}
    profile = inner.get("author-profile") if isinstance(inner.get("author-profile"), dict) else {}
    aff = profile.get("affiliation-current") or inner.get("affiliation-current") or {}
    if isinstance(aff, dict) and "affiliation" in aff:
        aff = aff.get("affiliation") or {}
    if isinstance(aff, list):
        aff = aff[0] if aff else {}
    if not isinstance(aff, dict):
        aff = {}
    ipdoc = aff.get("ip-doc") if isinstance(aff.get("ip-doc"), dict) else {}
    address = ipdoc.get("address") if isinstance(ipdoc.get("address"), dict) else {}
    orcid = _field_text(core.get("orcid") or inner.get("orcid") or profile.get("orcid"))
    pref = profile.get("preferred-name") if isinstance(profile.get("preferred-name"), dict) else {}
    affil = _compose_current_affiliation(
        aff.get("affiliation-name")
        or aff.get("affilname")
        or (ipdoc.get("afdispname") if isinstance(ipdoc, dict) else ""),
        aff.get("affiliation-city") or address.get("city"),
        aff.get("affiliation-country") or address.get("country"),
    )
    metrics = inner.get("metrics") if isinstance(inner.get("metrics"), dict) else {}
    return {
        "authid": author_search_id(core) or author_search_id(inner),
        "orcid": orcid,
        "documents": _field_int(
            core.get("document-count") or inner.get("document-count") or metrics.get("document-count")
        ),
        "cited_by": _field_int(
            core.get("cited-by-count") or inner.get("cited-by-count") or metrics.get("cited-by-count")
        ),
        "citations": _field_int(
            core.get("citation-count")
            or core.get("citations-count")
            or inner.get("citation-count")
            or profile.get("citation-count")
            or metrics.get("citation-count")
        ),
        "h_index": _field_int(
            inner.get("h-index")
            or core.get("h-index")
            or profile.get("h-index")
            or metrics.get("h-index")
        ),
        "coauthors": _field_int(inner.get("coauthor-count") or core.get("coauthor-count")),
        "profile_affil": affil,
        "surname": _field_text(pref.get("surname") or profile.get("surname")),
        "given": _field_text(pref.get("given-name") or profile.get("given-name")),
        "initials": _field_text(pref.get("initials")),
    }


def profile_display_name(profile: dict, fallback: str = "") -> str:
    surname = (profile.get("surname") or "").strip()
    given = (profile.get("given") or "").strip()
    initials = (profile.get("initials") or "").strip()
    if surname and given:
        return f"{surname}, {given}"
    if surname and initials:
        return f"{surname}, {initials}"
    return surname or fallback


def apply_author_profile(author: dict, profile: dict) -> dict:
    if not isinstance(author, dict) or not isinstance(profile, dict):
        return author
    for key in ("authid", "orcid", "profile_affil", "surname", "given", "initials", "metrics_source"):
        if profile.get(key) and not author.get(key):
            author[key] = profile[key]
    for key in ("documents", "cited_by", "citations", "h_index", "coauthors"):
        if author.get(key) in (None, "") and profile.get(key) is not None:
            author[key] = profile[key]
    return author


def paper_authors_matching(
    records: list[dict],
    *,
    authid: str = "",
    orcid: str = "",
    surname: str = "",
) -> list[dict]:
    """Авторы на уже найденных статьях, совпадающие с запросом."""
    wanted_id = "".join(ch for ch in str(authid or "") if ch.isdigit())
    wanted_orcid = normalize_orcid(orcid).lower()
    wanted_sur = (surname or "").strip().lower()
    hits: list[dict] = []
    for rec in records or []:
        for author in rec.get("authors") or []:
            if not isinstance(author, dict):
                continue
            if wanted_id and (author.get("authid") or "") == wanted_id:
                hits.append(author)
                continue
            author_orcid = normalize_orcid(author.get("orcid") or "").lower()
            if wanted_orcid and author_orcid and author_orcid == wanted_orcid:
                hits.append(author)
                continue
            if wanted_sur and (author.get("surname") or "").strip().lower() == wanted_sur:
                hits.append(author)
    return hits


def authid_on_every_paper(records: list[dict]) -> str:
    """Author ID, который есть на каждой статье — обычно сам искомый автор."""
    common: set[str] | None = None
    for rec in records or []:
        ids = set(author_ids(rec.get("authors") or []))
        if not ids:
            return ""
        common = ids if common is None else common & ids
        if not common:
            return ""
    if common and len(common) == 1:
        return next(iter(common))
    return ""


def seed_profile_from_authors(authors: list[dict]) -> dict:
    profile: dict = {}
    for author in authors or []:
        apply_author_profile(
            profile,
            {
                "authid": author.get("authid") or "",
                "orcid": author.get("orcid") or "",
                "surname": author.get("surname") or "",
                "given": author.get("given") or "",
                "initials": author.get("initials") or "",
            },
        )
    if not profile.get("authid"):
        ids = author_ids(authors)
        if len(ids) == 1:
            profile["authid"] = ids[0]
    return profile


def h_index_from_citation_counts(counts: list[int]) -> int:
    ranked = sorted((max(0, int(n)) for n in counts), reverse=True)
    h = 0
    for index, cites in enumerate(ranked, start=1):
        if cites >= index:
            h = index
        else:
            break
    return h


def profile_metrics_from_papers(records: list[dict]) -> dict:
    """Документы, сумма citedby-count и h-индекс по статьям поиска — запасной путь без Author Retrieval."""
    if not records:
        return {}
    counts: list[int] = []
    for rec in records:
        value = rec.get("cited_by_count")
        parsed = _field_int(value)
        counts.append(0 if parsed is None else parsed)
    return {
        "documents": len(records),
        "citations": sum(counts),
        "h_index": h_index_from_citation_counts(counts),
        "metrics_source": "papers",
    }


def _author_entry_initial(entry: dict) -> str:
    pref = entry.get("preferred-name")
    if not isinstance(pref, dict):
        pref = {}
    return first_initial(
        str(pref.get("initials") or entry.get("initials") or ""),
        str(pref.get("given-name") or entry.get("given-name") or ""),
    )


def _author_entry_is_gasu(entry: dict) -> bool:
    aff = entry.get("affiliation-current") or {}
    if isinstance(aff, list):
        aff = aff[0] if aff else {}
    if not isinstance(aff, dict):
        aff = {}
    name = str(aff.get("affiliation-name") or aff.get("affilname") or "")
    city = str(aff.get("affiliation-city") or "")
    return is_gasu_name(name) or is_gasu_city(city)


def pick_scopus_authid(
    entries: list,
    surname: str = "",
    initials: str = "",
    given: str = "",
) -> str:
    """Один профиль, если однозначен. Несколько тёзок с той же буквой — не угадываем."""
    wanted = first_initial(initials, given).lower()
    parsed: list[tuple[str, bool, str]] = []
    for entry in entries or []:
        if not isinstance(entry, dict) or entry.get("error"):
            continue
        authid = author_search_id(entry)
        if not authid:
            continue
        parsed.append((authid, _author_entry_is_gasu(entry), _author_entry_initial(entry).lower()))
    if wanted:
        parsed = [item for item in parsed if not item[2] or item[2] == wanted]
    unique = list(dict.fromkeys(item[0] for item in parsed))
    if len(unique) == 1:
        return unique[0]
    gasu = list(dict.fromkeys(item[0] for item in parsed if item[1]))
    if len(gasu) == 1:
        return gasu[0]
    return ""


def match_authid_on_paper(
    authors: list[dict],
    surname: str,
    initials: str = "",
    given: str = "",
) -> str:
    """AU-ID человека на уже найденной статье ГАГУ — не по фамилии среди всех Scopus."""
    wanted_sur = (surname or "").strip().lower()
    if not wanted_sur:
        return ""
    wanted_ini = first_initial(initials, given).lower()
    hits: list[str] = []
    for author in authors or []:
        if (author.get("surname") or "").strip().lower() != wanted_sur:
            continue
        got = first_initial(author.get("initials") or "", author.get("given") or "").lower()
        if wanted_ini and got and got != wanted_ini:
            continue
        authid = (author.get("authid") or "").strip()
        if authid.isdigit():
            hits.append(authid)
    unique = list(dict.fromkeys(hits))
    return unique[0] if len(unique) == 1 else ""


def record_has_gasu(record: dict) -> bool:
    for part in (record.get("affiliation") or "").split(";"):
        if is_gasu_name(part):
            return True
    return False


def author_belongs_to_gasu(author: dict) -> bool | None:
    """True/False, если у автора в Scopus есть свои аффилиации; иначе None."""
    if not isinstance(author, dict):
        return None
    items: list[dict] = []
    aff = author.get("affiliation")
    if isinstance(aff, list):
        items.extend(item for item in aff if isinstance(item, dict))
    elif isinstance(aff, dict):
        items.append(aff)
    if not items:
        return None
    saw_name = False
    for item in items:
        name = (
            item.get("affilname")
            or item.get("affiliation-name")
            or item.get("name")
            or ""
        ).strip()
        city = (item.get("affiliation-city") or item.get("city") or "").strip()
        if name or city:
            saw_name = True
        if _affiliation_dict_is_gasu(item):
            return True
    if saw_name:
        return False
    return None


def iter_author_items(entry: dict) -> list[dict]:
    """Достаёт словари авторов из search COMPLETE, STANDARD и abstract retrieval."""
    if not isinstance(entry, dict):
        return []
    blobs: list[object] = []
    for key in ("author", "authors", "author-list"):
        if key in entry:
            blobs.append(entry[key])
    inner = entry.get("abstracts-retrieval-response")
    if isinstance(inner, dict):
        authors = inner.get("authors")
        if authors is not None:
            blobs.append(authors)
    found: list[dict] = []
    queue: list[object] = list(blobs)
    while queue:
        raw = queue.pop(0)
        if isinstance(raw, list):
            queue.extend(raw)
            continue
        if not isinstance(raw, dict):
            continue
        if any(
            key in raw
            for key in (
                "surname",
                "ce:surname",
                "authid",
                "@auid",
                "authname",
                "preferred-name",
                "given-name",
                "ce:given-name",
                "author-url",
            )
        ):
            found.append(raw)
            continue
        for key in ("author", "authors"):
            if key in raw:
                queue.append(raw[key])
    return found


def parse_author_item(item: dict) -> dict | None:
    if not isinstance(item, dict):
        return None
    preferred = item.get("preferred-name")
    if not isinstance(preferred, dict):
        preferred = {}
    surname = (
        item.get("surname")
        or item.get("ce:surname")
        or preferred.get("ce:surname")
        or preferred.get("surname")
        or ""
    ).strip()
    given = (
        item.get("given-name")
        or item.get("ce:given-name")
        or preferred.get("ce:given-name")
        or ""
    ).strip()
    initials = (
        item.get("initials")
        or item.get("ce:initials")
        or preferred.get("ce:initials")
        or ""
    ).strip()
    if not surname:
        authname = (
            item.get("authname")
            or item.get("ce:indexed-name")
            or preferred.get("ce:indexed-name")
            or ""
        ).strip()
        if "," in authname:
            surname, rest = [part.strip() for part in authname.split(",", 1)]
            if not given:
                given = rest
        elif authname:
            parts = authname.split()
            surname = parts[0]
            if not given and len(parts) > 1:
                given = " ".join(parts[1:])
    authid = scopus_authid(item) or scopus_authid(preferred)
    if not surname and not authid:
        return None
    orcid = normalize_orcid(
        _field_text(item.get("orcid") or preferred.get("orcid") or item.get("ORCID") or "")
    )
    return {
        "surname": surname,
        "given": given,
        "initials": initials,
        "from_gasu": author_belongs_to_gasu(item),
        "authid": authid,
        "orcid": orcid,
    }


def author_ids(authors: list[dict] | None) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for author in authors or []:
        authid = str((author or {}).get("authid") or "").strip()
        if authid.isdigit() and authid not in seen:
            seen.add(authid)
            ids.append(authid)
    return ids


def parse_author_count(entry: dict) -> int | None:
    """Сколько авторов в статье по полю author-count (COMPLETE view)."""
    if not isinstance(entry, dict):
        return None
    raw = entry.get("author-count")
    if isinstance(raw, dict):
        raw = raw.get("@total") or raw.get("$") or raw.get("#text")
    try:
        count = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return count if count > 0 else None


def paper_abstract_urls(record: dict) -> list[str]:
    """Abstract Retrieval: eid, Scopus ID, DOI — в таком порядке."""
    urls: list[str] = []
    seen: set[str] = set()

    def add(kind: str, ident: str) -> None:
        ident = (ident or "").strip()
        if not ident:
            return
        if kind == "doi":
            ident = quote(ident, safe="")
        url = f"https://api.elsevier.com/content/abstract/{kind}/{ident}"
        if url in seen:
            return
        seen.add(url)
        urls.append(url)

    sid = (record.get("scopus_id") or "").strip()
    eid = (record.get("eid") or "").strip()
    if sid.startswith("2-s2.0-"):
        add("eid", sid)
    elif sid:
        add("scopus_id", sid)
    add("eid", eid)
    add("doi", record.get("doi") or "")
    return urls


def authors_look_truncated(record: dict) -> bool:
    authors = record.get("authors") or []
    expected = record.get("author_count")
    if isinstance(expected, int) and expected > 0:
        return len(authors) < expected
    return len(authors) < 2


def needs_author_enrichment(record: dict) -> bool:
    """Search API часто отдаёт только первого автора и без Author ID."""
    if not ((record.get("scopus_id") or "").strip() or (record.get("doi") or "").strip() or (record.get("eid") or "").strip()):
        return False
    authors = record.get("authors") or []
    expected = record.get("author_count")
    if isinstance(expected, int) and expected == 1 and len(authors) == 1 and author_ids(authors):
        return False
    if authors_look_truncated(record):
        return True
    return len(author_ids(authors)) < len(authors)


def truncated_author_paper_count(records: list[dict]) -> int:
    return sum(1 for rec in records or [] if authors_look_truncated(rec))


def crossref_work_url(doi: str) -> str:
    ident = (doi or "").strip()
    lower = ident.lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/"):
        if lower.startswith(prefix):
            ident = ident[len(prefix) :]
            break
    ident = ident.strip()
    if not ident:
        return ""
    return f"https://api.crossref.org/works/{quote(ident, safe='')}"


def _initials_from_given(given: str) -> str:
    text = (given or "").strip()
    if not text:
        return ""
    compact = text.replace(" ", "").replace("-", "")
    if re.fullmatch(r"(?:[A-Za-zА-ЯЁ][a-zа-яё]?\.)+", compact):
        return compact if compact.endswith(".") else f"{compact}."
    return "".join(f"{part[0].upper()}." for part in re.split(r"[\s\-]+", text) if part[:1].isalpha())


def parse_crossref_authors(payload: dict) -> list[dict]:
    """Авторы из Crossref /works — запасной список, когда Scopus отдал только первого."""
    if not isinstance(payload, dict):
        return []
    message = payload.get("message")
    if not isinstance(message, dict):
        message = payload
    raw = message.get("author") or []
    if isinstance(raw, dict):
        raw = [raw]
    authors: list[dict] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        surname = (item.get("family") or "").strip()
        given = (item.get("given") or "").strip()
        if not surname:
            continue
        key = surname.lower()
        if key in seen:
            continue
        seen.add(key)
        authors.append(
            {
                "surname": surname,
                "given": given,
                "initials": _initials_from_given(given),
                "from_gasu": None,
                "authid": "",
                "orcid": normalize_orcid(item.get("ORCID") or item.get("orcid") or ""),
            }
        )
    return authors


def merge_author_lists(primary: list[dict], extra: list[dict]) -> list[dict]:
    """Полный список (Crossref) + Author ID/ORCID, которые уже были у Scopus."""
    if not extra:
        return [dict(item) for item in primary or []]
    if not primary:
        return [dict(item) for item in extra]
    by_surname: dict[str, dict] = {}
    for item in primary:
        key = (item.get("surname") or "").strip().lower()
        if key and key not in by_surname:
            by_surname[key] = item
    merged: list[dict] = []
    seen: set[str] = set()
    for item in extra:
        row = dict(item)
        key = (row.get("surname") or "").strip().lower()
        prior = by_surname.get(key) if key else None
        if prior:
            for field in ("authid", "orcid", "given", "initials"):
                if prior.get(field) and not row.get(field):
                    row[field] = prior[field]
            if row.get("from_gasu") is None:
                row["from_gasu"] = prior.get("from_gasu")
        merged.append(row)
        if key:
            seen.add(key)
    for item in primary:
        key = (item.get("surname") or "").strip().lower()
        if key and key not in seen:
            merged.append(dict(item))
            seen.add(key)
    return merged


def fill_truncated_authors_from_crossref(records: list[dict], fetch) -> int:
    """fetch(doi) → список авторов. Нужен, чтобы в РНФ попадали не только первые авторы."""
    updated = 0
    for rec in records or []:
        if not authors_look_truncated(rec):
            continue
        doi = (rec.get("doi") or "").strip()
        if not doi:
            continue
        try:
            extra = fetch(doi) or []
        except Exception:
            continue
        if not extra:
            continue
        rec["authors"] = merge_author_lists(rec.get("authors") or [], extra)
        updated += 1
    return updated


def record_sort_key(record: dict) -> tuple[str, int, str]:
    """Фамилия первого автора, затем год по убыванию, затем название."""
    authors = record.get("authors") or []
    surname = ""
    if authors:
        surname = (authors[0].get("surname") or "").strip().lower()
    year = str(record.get("year") or "").strip()
    year_n = int(year) if year.isdigit() else 0
    title = (record.get("title") or "").strip().lower()
    return (surname, -year_n, title)


_AUTHOR_TEXT_TOKEN = re.compile(
    r"([A-Za-zА-ЯЁа-яё][A-Za-zА-ЯЁа-яё''-]*)"
    r"(?:\s*,\s*|\s+)"
    r"([A-ZА-ЯЁ](?:\.[A-Za-zА-ЯЁ]+)*\.?)"
)


def parse_author_text(text: str) -> list[dict]:
    """Строка вроде «Frolov, I.N., Kudryavtsev, N.G., Safonova, V.Yu.»."""
    authors: list[dict] = []
    seen: set[str] = set()
    for match in _AUTHOR_TEXT_TOKEN.finditer(text or ""):
        surname = match.group(1).strip()
        initials = match.group(2).strip()
        if not initials.endswith("."):
            initials = f"{initials}."
        key = surname.lower()
        if not surname or key in seen:
            continue
        seen.add(key)
        authors.append(
            {
                "surname": surname,
                "given": "",
                "initials": initials,
                "from_gasu": None,
                "authid": "",
            }
        )
    return authors


def _author_text_blobs(entry: dict) -> list[str]:
    blobs: list[str] = []
    if not isinstance(entry, dict):
        return blobs
    for key in ("author", "authors", "dc:creator"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            blobs.append(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    blobs.append(item)
    return blobs


def parse_authors(entry: dict) -> list[dict]:
    authors = []
    seen: set[str] = set()
    for item in iter_author_items(entry):
        parsed = parse_author_item(item)
        if not parsed:
            continue
        key = parsed.get("authid") or f"{parsed.get('surname')}|{parsed.get('given')}"
        if key in seen:
            continue
        seen.add(key)
        authors.append(parsed)
    have = {(item.get("surname") or "").strip().lower() for item in authors if item.get("surname")}
    for blob in _author_text_blobs(entry):
        for extra in parse_author_text(blob):
            surname = (extra.get("surname") or "").strip().lower()
            if not surname or surname in have:
                continue
            have.add(surname)
            authors.append(extra)
    if authors:
        return authors
    creator = (entry.get("dc:creator") or "").strip()
    if not creator:
        return []
    parts = [p.strip() for p in creator.split(",") if p.strip()]
    if len(parts) >= 2:
        surname, given = parts[0], parts[1]
    else:
        surname, given = creator, ""
    return [{"surname": surname, "given": given, "initials": "", "from_gasu": None, "authid": ""}]


def format_affiliations(entry: dict, ensure_gasu: bool = False) -> str:
    names = affiliation_names(entry)
    if any(is_gasu_name(name) for name in names):
        names = sorted(names, key=lambda name: 0 if is_gasu_name(name) else 1)
    return "; ".join(names)
