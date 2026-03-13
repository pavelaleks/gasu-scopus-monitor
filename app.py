import os
from datetime import datetime
from io import BytesIO
from pathlib import Path

import pandas as pd
import requests
import streamlit as st
from docx import Document

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

API_URL = "https://api.elsevier.com/content/search/scopus"
AFFILIATION_ID = "60105869"
AFFILIATION_NAME = "Gorno-Altaisk State University"
ENV_PATH = Path(__file__).with_name(".env")


def load_api_key() -> str | None:
    try:
        if "SCOPUS_API_KEY" in st.secrets:
            return st.secrets["SCOPUS_API_KEY"]
    except Exception:
        pass
    if load_dotenv:
        load_dotenv(ENV_PATH)
    return os.getenv("SCOPUS_API_KEY")


def save_api_key(value: str) -> None:
    value = value.strip()
    if not value:
        return
    lines = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    key_line = f"SCOPUS_API_KEY={value}"
    updated = False
    for i, line in enumerate(lines):
        if line.startswith("SCOPUS_API_KEY="):
            lines[i] = key_line
            updated = True
            break
    if not updated:
        lines.append(key_line)
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ["SCOPUS_API_KEY"] = value


def normalize_initials(text: str) -> str:
    cleaned = (text or "").replace(".", "").replace("-", " ").strip()
    if not cleaned:
        return ""
    parts = [p for p in cleaned.split() if p]
    return "".join(f"{p[0].upper()}." for p in parts)


def initials_from_given(given: str) -> str:
    return normalize_initials(given)


def parse_authors(entry: dict) -> list[dict]:
    authors = []
    raw = entry.get("author")
    if isinstance(raw, list):
        for item in raw:
            surname = (item.get("surname") or "").strip()
            given = (item.get("given-name") or "").strip()
            initials = (item.get("initials") or "").strip()
            if not given and initials:
                given = normalize_initials(initials)
            authors.append({"surname": surname, "given": given, "initials": initials})
    creator = (entry.get("dc:creator") or "").strip()
    if not authors and creator:
        parts = [p.strip() for p in creator.split(",")]
        if len(parts) >= 2:
            surname, given = parts[0], parts[1]
        else:
            surname, given = creator, ""
        authors.append({"surname": surname, "given": given, "initials": ""})
    return authors


def format_authors_gost(authors: list[dict]) -> str:
    formatted = []
    for author in authors:
        surname = author.get("surname", "").strip()
        given = author.get("given", "").strip()
        initials = initials_from_given(given) or normalize_initials(author.get("initials", ""))
        if surname and initials:
            formatted.append(f"{surname} {initials}")
        elif surname:
            formatted.append(surname)
    return ", ".join(formatted)


def format_authors_apa(authors: list[dict]) -> str:
    formatted = []
    for author in authors:
        surname = author.get("surname", "").strip()
        given = author.get("given", "").strip()
        initials = initials_from_given(given) or normalize_initials(author.get("initials", ""))
        if surname and initials:
            formatted.append(f"{surname}, {initials}")
        elif surname:
            formatted.append(surname)
    if not formatted:
        return ""
    if len(formatted) == 1:
        return formatted[0]
    return ", ".join(formatted[:-1]) + f", & {formatted[-1]}"


def format_gost(record: dict) -> str:
    parts = []
    authors = format_authors_gost(record["authors"])
    if authors:
        parts.append(authors)
    if record["title"]:
        parts.append(record["title"])
    main = " ".join(parts).strip()
    journal_part = f"// {record['journal']}" if record["journal"] else ""
    year_part = f"{record['year']}" if record["year"] else ""
    volume_part = f"Т. {record['volume']}" if record["volume"] else ""
    issue_part = f"№ {record['issue']}" if record["issue"] else ""
    pages_part = f"С. {record['pages']}" if record["pages"] else ""
    tail = ". ".join([p for p in [journal_part, year_part, volume_part, issue_part, pages_part] if p])
    if tail:
        return f"{main} {tail}."
    return f"{main}."


def format_apa(record: dict) -> str:
    authors = format_authors_apa(record["authors"])
    year_part = f"({record['year']})." if record["year"] else "(n.d.)."
    title_part = f"{record['title']}." if record["title"] else ""
    journal_part = record["journal"] or ""
    volume_issue = ""
    if record["volume"] and record["issue"]:
        volume_issue = f"{record['volume']}({record['issue']})"
    elif record["volume"]:
        volume_issue = record["volume"]
    pages_part = record["pages"]
    doi = record["doi"]
    doi_part = f"https://doi.org/{doi}" if doi else ""
    tail = ", ".join([p for p in [journal_part, volume_issue, pages_part] if p])
    if tail:
        tail = f"{tail}."
    parts = [p for p in [authors, year_part, title_part, tail, doi_part] if p]
    return " ".join(parts).strip()


def build_query(
    mode: str,
    last: str,
    orcid: str,
    date_filter: dict,
    only_gasu: bool,
) -> str:
    def quoted(value: str) -> str:
        cleaned = (value or "").strip().replace('"', "")
        return f"\"{cleaned}\""

    if mode == "Мониторинг ГАГУ":
        base = f"AFFIL({quoted(AFFILIATION_NAME)})"
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
        base = f"{base} AND AFFIL({quoted(AFFILIATION_NAME)})"

    return base


def make_date_filter(mode: str, start_year: int | None, end_year: int | None) -> dict | None:
    current_year = datetime.now().year
    if mode == "current":
        return {"mode": "current", "year": current_year, "year_start": current_year, "year_end": current_year}
    if mode == "last5":
        start = current_year - 4
        return {"mode": "range", "year": current_year, "year_start": start, "year_end": current_year}
    if mode == "range" and start_year and end_year:
        return {"mode": "range", "year": start_year, "year_start": start_year, "year_end": end_year}
    return None


def affiliation_items(entry: dict) -> list[dict]:
    affil = entry.get("affiliation")
    if isinstance(affil, list):
        return [item for item in affil if isinstance(item, dict)]
    if isinstance(affil, dict):
        return [affil]
    return []


def extract_affiliation(entry: dict) -> str:
    items = affiliation_items(entry)
    for item in items:
        name = (item.get("affilname") or item.get("affiliation-name") or item.get("name") or "").strip()
        if name.lower() == AFFILIATION_NAME.lower():
            return name
    if items:
        item = items[0]
        return (item.get("affilname") or item.get("affiliation-name") or item.get("name") or "").strip()
    affil = entry.get("affiliation")
    if isinstance(affil, str):
        return affil.strip()
    return ""


def has_gasu_affiliation(entry: dict) -> bool:
    for item in affiliation_items(entry):
        name = (item.get("affilname") or item.get("affiliation-name") or item.get("name") or "").strip()
        if name.lower() == AFFILIATION_NAME.lower():
            return True
    return False


def fetch_scopus_data(query: str, api_key: str, max_results: int | None) -> list[dict]:
    headers = {"X-ELS-APIKey": api_key, "Accept": "application/json"}
    records = []
    start = 0
    page_size = 25
    total = None
    while True:
        params = {"query": query, "count": page_size, "start": start}
        last_error = None
        for _ in range(3):
            try:
                response = requests.get(API_URL, headers=headers, params=params, timeout=60)
                last_error = None
                break
            except requests.RequestException as exc:
                last_error = exc
        if last_error:
            raise RuntimeError(f"Scopus API timeout: {last_error}") from last_error
        if response.status_code != 200:
            raise RuntimeError(response.text)
        payload = response.json()
        if total is None:
            total = int(payload["search-results"].get("opensearch:totalResults", 0))
        entries = payload["search-results"].get("entry", [])
        for entry in entries:
            if f'AFFIL("{AFFILIATION_NAME}")' in query and not has_gasu_affiliation(entry):
                continue
            authors = parse_authors(entry)
            cover_date = (entry.get("prism:coverDate") or "").strip()
            record = {
                "title": (entry.get("dc:title") or "").strip(),
                "journal": (entry.get("prism:publicationName") or "").strip(),
                "year": cover_date[:4],
                "cover_date": cover_date,
                "volume": (entry.get("prism:volume") or "").strip(),
                "issue": (entry.get("prism:issueIdentifier") or "").strip(),
                "pages": (entry.get("prism:pageRange") or "").strip(),
                "doi": (entry.get("prism:doi") or "").strip(),
                "scopus_id": (entry.get("dc:identifier") or "").replace("SCOPUS_ID:", ""),
                "authors": authors,
                "affiliation": extract_affiliation(entry),
            }
            records.append(record)
            if max_results and len(records) >= max_results:
                break
        start += page_size
        if start >= total or not entries:
            break
    records.sort(key=lambda item: item.get("cover_date") or "", reverse=True)
    return records


def records_to_dataframe(records: list[dict]) -> pd.DataFrame:
    rows = []
    for rec in records:
        rows.append(
            {
                "Год": rec["year"],
                "Название": rec["title"],
                "Журнал": rec["journal"],
                "Авторы": format_authors_gost(rec["authors"]),
                "Организация": rec.get("affiliation", ""),
                "DOI": rec["doi"],
                "Scopus ID": rec["scopus_id"],
            }
        )
    df = pd.DataFrame(rows)
    df.index = range(1, len(df) + 1)
    return df


def sort_records_for_bibliography(records: list[dict], date_filter: dict | None) -> list[dict]:
    def author_key(rec: dict) -> str:
        authors = rec.get("authors") or []
        if authors:
            surname = (authors[0].get("surname") or "").strip().lower()
            if surname:
                return surname
        return format_authors_gost(authors).lower()

    def year_key(rec: dict) -> int:
        year = rec.get("year") or ""
        return int(year) if year.isdigit() else 0

    if date_filter and date_filter.get("mode") == "range":
        return sorted(records, key=lambda rec: (author_key(rec), year_key(rec)))
    return sorted(records, key=author_key)


def build_docx(records: list[dict], fmt: str) -> BytesIO:
    doc = Document()
    title = "Список публикаций"
    doc.add_heading(title, level=1)
    for idx, rec in enumerate(records, start=1):
        text = format_gost(rec) if fmt == "ГОСТ 7.0.5" else format_apa(rec)
        doc.add_paragraph(f"{idx}. {text}")
    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


def build_xlsx(records: list[dict]) -> BytesIO:
    df = records_to_dataframe(records)
    df["ГОСТ 7.0.5"] = [format_gost(r) for r in records]
    df["APA 7th"] = [format_apa(r) for r in records]
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Scopus")
    buf.seek(0)
    return buf


st.set_page_config(page_title="Мониторинг публикаций Scopus", layout="wide")
st.title("Мониторинг публикаций Scopus")

api_key = load_api_key()
with st.sidebar:
    st.header("Доступ к Scopus")
    if not api_key:
        st.write("Введите API-ключ один раз. Он сохранится локально в `.env`.")
        key_input = st.text_input("API-ключ Scopus", type="password")
        if st.button("Сохранить ключ"):
            if key_input.strip():
                save_api_key(key_input)
                st.success("Ключ сохранен. Перезагружаю...")
                st.rerun()
            else:
                st.warning("Введите корректный ключ.")
    else:
        st.success("API-ключ найден.")
        st.caption("Используется ключ из `st.secrets` или `.env`.")

st.markdown("Нажмите кнопку для быстрого мониторинга или выберите режим поиска.")

quick_check = st.button(
    "Проверить новые статьи ГАГУ за текущий год",
    type="primary",
    use_container_width=True,
)

mode = st.radio("Режим поиска", ["Мониторинг ГАГУ", "Поиск по автору"], horizontal=True)

author_last = ""
author_orcid = ""
only_gasu = False
if mode == "Поиск по автору":
    author_last = st.text_input("Фамилия автора")
    author_orcid = st.text_input("ORCID (если есть)")
    only_gasu = st.checkbox("Только аффилиация ГАГУ", value=False)

time_filter = st.radio(
    "Период",
    ["Текущий год", "Диапазон лет", "Последние 5 лет"],
    horizontal=True,
)
start_year = None
end_year = None
if time_filter == "Диапазон лет":
    col1, col2 = st.columns(2)
    with col1:
        start_year = st.number_input("С", min_value=1900, max_value=2100, value=2020, step=1)
    with col2:
        end_year = st.number_input("По", min_value=1900, max_value=2100, value=datetime.now().year, step=1)

search_clicked = st.button("Найти публикации")

if quick_check:
    mode = "Мониторинг ГАГУ"
    time_filter = "Текущий год"
    search_clicked = True

date_filter = None
if time_filter == "Текущий год":
    date_filter = make_date_filter("current", None, None)
elif time_filter == "Последние 5 лет":
    date_filter = make_date_filter("last5", None, None)
else:
    date_filter = make_date_filter("range", int(start_year), int(end_year))

if search_clicked:
    if not api_key:
        st.error("Нужен API-ключ Scopus. Введите его в боковой панели.")
        st.stop()
    if mode == "Поиск по автору" and not author_orcid and not author_last:
        st.error("Для поиска по автору укажите фамилию или ORCID.")
        st.stop()
    query = build_query(mode, author_last, author_orcid, date_filter, only_gasu)
    with st.spinner("Идет поиск в Scopus..."):
        try:
            records = fetch_scopus_data(query, api_key, None)
        except Exception as exc:
            st.error("Ошибка запроса к Scopus API.")
            st.code(str(exc))
            st.stop()

    if not records:
        st.info("Статей по данному запросу не найдено.")
        st.stop()

    st.session_state["records"] = records
    st.session_state["date_filter"] = date_filter

if "records" in st.session_state and st.session_state["records"]:
    records = st.session_state["records"]
    active_date_filter = st.session_state.get("date_filter")
    records_for_list = sort_records_for_bibliography(records, active_date_filter)

    st.subheader("Результаты")
    df = records_to_dataframe(records)
    st.dataframe(df, use_container_width=True)

    st.subheader("Готовый список литературы")
    format_choice = st.selectbox("Формат", ["ГОСТ 7.0.5", "APA 7th Edition"])
    formatted_list = [
        format_gost(rec) if format_choice == "ГОСТ 7.0.5" else format_apa(rec)
        for rec in records_for_list
    ]
    st.markdown("\n".join([f"{i}. {text}" for i, text in enumerate(formatted_list, start=1)]))

    docx_buffer = build_docx(records_for_list, format_choice)
    xlsx_buffer = build_xlsx(records_for_list)

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "Скачать .docx",
            data=docx_buffer,
            file_name="scopus_publications.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    with col2:
        st.download_button(
            "Скачать .xlsx",
            data=xlsx_buffer,
            file_name="scopus_publications.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

st.markdown("---")
st.caption("© Алексеев П.В., pavel.alekseev.gasu@gmail.com, Горно-Алтайский государственный университет")
