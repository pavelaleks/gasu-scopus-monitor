"""Идентификация аффилиации ГАГУ в запросах и ответах Scopus.

Точность важнее полноты: короткий AFFIL("GASU") и непроверенный AF-ID
подмешивали сотни чужих статей (Innopolis, МФТИ и т.д.).

Документ относится к ГАГУ, только если в ответе есть узнаваемое название
или город Горно-Алтайска — не потому что совпал какой-то affiliation id.
Scopus индексирует все аффилиации документа, поэтому AFFILORG по полному
имени находит и случаи «ГАГУ — одна из нескольких организаций».
"""

from __future__ import annotations

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


def quoted(value: str) -> str:
    cleaned = (value or "").strip().replace('"', "")
    return f'"{cleaned}"'


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


def author_name_query(
    surname: str,
    initials: str = "",
    given: str = "",
    year_start: int | None = None,
    year_end: int | None = None,
) -> str:
    """Поиск статей человека по фамилии и инициалам, без фильтра ГАГУ."""
    last = quoted(surname)
    letters = [ch.upper() for ch in (initials or "") if ch.isalpha()]
    if not letters:
        letters = [word[0].upper() for word in (given or "").replace(".", " ").split() if word]
    query = f"AUTHLAST({last})"
    if len(letters) >= 2:
        query += f" AND AUTHFIRST({quoted('.'.join(letters[:2]) + '.')})"
    elif letters:
        query += f" AND AUTHFIRST({quoted(letters[0] + '.')})"
    if year_start is not None and year_end is not None:
        query += f" AND PUBYEAR > {year_start - 1} AND PUBYEAR < {year_end + 1}"
    return query


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
    return {
        "surname": surname,
        "given": given,
        "initials": initials,
        "from_gasu": author_belongs_to_gasu(item),
        "authid": authid,
    }


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
