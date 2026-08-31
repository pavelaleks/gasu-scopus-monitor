"""Области знаний Scopus (ASJC) по ISSN журнала — Search API их не отдаёт."""

from __future__ import annotations

import time
from collections import Counter

import requests

SERIAL_URL = "https://api.elsevier.com/content/serial/title/issn/{issn}"
UNKNOWN_AREA = "Не указано"

SUBJECT_LABELS_RU = {
    "AGRI": "Сельскохозяйственные и биологические науки",
    "ARTS": "Искусство и гуманитарные науки",
    "BIOC": "Биохимия, генетика и молекулярная биология",
    "BUSI": "Бизнес, менеджмент и бухгалтерский учёт",
    "CENG": "Химическая технология",
    "CHEM": "Химия",
    "COMP": "Компьютерные науки",
    "DECI": "Науки о принятии решений",
    "DENT": "Стоматология",
    "EART": "Науки о Земле и планетах",
    "ECON": "Экономика, эконометрика и финансы",
    "ENER": "Энергетика",
    "ENGI": "Инженерия",
    "ENVI": "Науки об окружающей среде",
    "HEAL": "Профессии здравоохранения",
    "IMMU": "Иммунология и микробиология",
    "MATE": "Материаловедение",
    "MATH": "Математика",
    "MEDI": "Медицина",
    "MULT": "Междисциплинарные исследования",
    "NEUR": "Нейронауки",
    "NURS": "Сестринское дело",
    "PHAR": "Фармакология, токсикология и фармацевтика",
    "PHYS": "Физика и астрономия",
    "PSYC": "Психология",
    "SOCI": "Социальные науки",
    "VETE": "Ветеринария",
}

# Первые две цифры 4-значного кода ASJC → верхний уровень Scopus.
ASJC_PREFIX = {
    "10": "MULT",
    "11": "AGRI",
    "12": "ARTS",
    "13": "BIOC",
    "14": "BUSI",
    "15": "CENG",
    "16": "CHEM",
    "17": "COMP",
    "18": "DECI",
    "19": "EART",
    "20": "ECON",
    "21": "ENER",
    "22": "ENGI",
    "23": "ENVI",
    "24": "IMMU",
    "25": "MATE",
    "26": "MATH",
    "27": "MEDI",
    "28": "NEUR",
    "29": "NURS",
    "30": "PHAR",
    "31": "PHYS",
    "32": "PSYC",
    "33": "SOCI",
    "34": "VETE",
    "35": "DENT",
    "36": "HEAL",
}


def normalize_issn(value: str) -> str | None:
    raw = (value or "").strip().upper().replace("-", "").replace(" ", "")
    if len(raw) < 8:
        return None
    body, check = raw[:7], raw[7]
    if body.isdigit() and (check.isdigit() or check == "X"):
        return raw[:8]
    return None


def _issn_values(raw) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, dict):
        text = raw.get("$") or raw.get("#text") or raw.get("prism:issn") or ""
        return [str(text)] if text else []
    if isinstance(raw, list):
        found = []
        for item in raw:
            found.extend(_issn_values(item))
        return found
    return [str(raw)]


def extract_issns(entry: dict) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for key in ("prism:issn", "prism:eIssn"):
        for raw in _issn_values(entry.get(key)):
            issn = normalize_issn(raw)
            if issn and issn not in seen:
                seen.add(issn)
                found.append(issn)
    return found


def abbrev_from_code(code: str) -> str | None:
    digits = "".join(ch for ch in str(code or "") if ch.isdigit())
    if len(digits) >= 2:
        return ASJC_PREFIX.get(digits[:2])
    return None


def parse_serial_abbrevs(payload: dict) -> list[str]:
    serial = payload.get("serial-metadata-response") or payload
    entries = serial.get("entry") or []
    if isinstance(entries, dict):
        entries = [entries]
    areas = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        raw = entry.get("subject-area")
        if raw is None:
            continue
        if isinstance(raw, dict):
            raw = [raw]
        if not isinstance(raw, list):
            continue
        for item in raw:
            if not isinstance(item, dict):
                continue
            abbrev = (item.get("@abbrev") or "").strip().upper()
            if abbrev not in SUBJECT_LABELS_RU:
                abbrev = abbrev_from_code(item.get("@code") or "") or abbrev
            if abbrev in SUBJECT_LABELS_RU and abbrev not in areas:
                areas.append(abbrev)
    return areas


def label_for_abbrev(abbrev: str) -> str:
    return SUBJECT_LABELS_RU.get(abbrev, UNKNOWN_AREA)


def format_subject_areas(abbrevs: list[str]) -> str:
    labels = []
    seen: set[str] = set()
    for abbrev in abbrevs:
        label = label_for_abbrev(abbrev)
        if label not in seen:
            seen.add(label)
            labels.append(label)
    return "; ".join(labels)


def primary_area_label(record: dict) -> str:
    abbrevs = record.get("subject_abbrevs") or []
    if abbrevs:
        return label_for_abbrev(abbrevs[0])
    return UNKNOWN_AREA


def area_share_rows(records: list[dict], year: str | None = None) -> list[dict]:
    subset = records
    if year:
        subset = [rec for rec in records if str(rec.get("year") or "") == str(year)]
    counts = Counter(primary_area_label(rec) for rec in subset)
    total = len(subset)
    rows = []
    for label, current in counts.most_common():
        share = round(current / total * 100, 1) if total else 0.0
        rows.append(
            {
                "Область знаний": label,
                "Публикаций": current,
                "Доля": f"{share:g}%",
            }
        )
    return rows


def grouped_area_counts(rows: list[dict], max_slices: int = 8) -> list[tuple[str, int]]:
    pairs = [(row["Область знаний"], int(row["Публикаций"])) for row in rows]
    if len(pairs) <= max_slices:
        return pairs
    head = pairs[: max_slices - 1]
    rest = sum(count for _, count in pairs[max_slices - 1 :])
    head.append(("Прочие", rest))
    return head


def fetch_serial_abbrevs(issn: str, api_key: str) -> tuple[list[str], int]:
    headers = {"X-ELS-APIKey": api_key, "Accept": "application/json"}
    url = SERIAL_URL.format(issn=issn)
    response = requests.get(url, headers=headers, params={"view": "ENHANCED"}, timeout=45)
    if response.status_code in {400, 401, 403}:
        response = requests.get(url, headers=headers, timeout=45)
    if response.status_code != 200:
        return [], response.status_code
    try:
        payload = response.json()
    except ValueError:
        return [], response.status_code
    if not isinstance(payload, dict):
        return [], response.status_code
    return parse_serial_abbrevs(payload), response.status_code


def attach_subject_areas(
    records: list[dict],
    api_key: str,
    cache: dict | None = None,
    *,
    fetch=None,
    sleep_s: float = 0.12,
) -> dict:
    """Дописывает subject_abbrevs / subject_areas. cache: ISSN → список аббревиатур."""
    cache = cache if cache is not None else {}
    fetch = fetch or fetch_serial_abbrevs
    pending: list[str] = []
    seen: set[str] = set()
    for rec in records:
        for issn in rec.get("issns") or []:
            if issn not in cache and issn not in seen:
                seen.add(issn)
                pending.append(issn)

    denied = False
    for issn in pending:
        if denied:
            cache[issn] = []
            continue
        abbrevs, status = fetch(issn, api_key)
        if status in {401, 403}:
            denied = True
            cache[issn] = []
            continue
        cache[issn] = abbrevs or []
        if sleep_s:
            time.sleep(sleep_s)

    for rec in records:
        abbrevs: list[str] = []
        for issn in rec.get("issns") or []:
            for item in cache.get(issn) or []:
                if item not in abbrevs:
                    abbrevs.append(item)
        rec["subject_abbrevs"] = abbrevs
        rec["subject_areas"] = format_subject_areas(abbrevs) or UNKNOWN_AREA
    return cache
