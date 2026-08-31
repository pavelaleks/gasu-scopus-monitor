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
) -> str:
    """Поиск профиля автора: фамилия + ГАГУ, при возможности первая буква имени."""
    query = f"AUTHLAST({quoted(surname)})"
    initial = first_initial(initials, given)
    if with_initial is None:
        with_initial = bool(initial)
    if with_initial and initial:
        query += f" AND AUTHFIRST({initial})"
    return f"{query} AND {gasu_author_affil_clause()}"


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
    text = _field_text(value).replace(",", "").replace(" ", "")
    if text.isdigit():
        return int(text)
    return None


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
    affil = " ".join(
        part
        for part in (
            _field_text(aff.get("affiliation-name") or aff.get("affilname")),
            _field_text(aff.get("affiliation-city")),
        )
        if part
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
    affil = _field_text(
        aff.get("affiliation-name")
        or aff.get("affilname")
        or (ipdoc.get("afdispname") if isinstance(ipdoc, dict) else "")
    )
    orcid = _field_text(core.get("orcid") or inner.get("orcid") or profile.get("orcid"))
    return {
        "authid": author_search_id(core) or author_search_id(inner),
        "orcid": orcid,
        "documents": _field_int(core.get("document-count") or inner.get("document-count")),
        "cited_by": _field_int(core.get("cited-by-count") or inner.get("cited-by-count")),
        "citations": _field_int(
            core.get("citation-count")
            or core.get("citations-count")
            or inner.get("citation-count")
        ),
        "h_index": _field_int(inner.get("h-index") or core.get("h-index") or profile.get("h-index")),
        "coauthors": _field_int(inner.get("coauthor-count") or core.get("coauthor-count")),
        "profile_affil": affil,
    }


def apply_author_profile(author: dict, profile: dict) -> dict:
    if not isinstance(author, dict) or not isinstance(profile, dict):
        return author
    for key in ("authid", "orcid", "profile_affil"):
        if profile.get(key) and not author.get(key):
            author[key] = profile[key]
    for key in ("documents", "cited_by", "citations", "h_index", "coauthors"):
        if author.get(key) in (None, "") and profile.get(key) is not None:
            author[key] = profile[key]
    return author
    if not isinstance(entry, dict):
        return ""
    ident = str(entry.get("dc:identifier") or "")
    digits = "".join(ch for ch in ident if ch.isdigit())
    if len(digits) >= 6:
        return digits
    return scopus_authid(entry)


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
    return {
        "surname": surname,
        "given": given,
        "initials": initials,
        "from_gasu": author_belongs_to_gasu(item),
        "authid": authid,
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


def needs_author_enrichment(record: dict) -> bool:
    """Search API часто отдаёт только первого автора и без Author ID."""
    if not (record.get("scopus_id") or "").strip():
        return False
    authors = record.get("authors") or []
    if len(authors) < 2:
        return True
    return len(author_ids(authors)) < len(authors)


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
