import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from streamlit.testing.v1 import AppTest

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def _login(at: AppTest) -> AppTest:
    at.run()
    for inp in at.text_input:
        if "Пароль" in (inp.label or ""):
            inp.input("12345")
            break
    for button in at.button:
        if "Войти" in (button.label or ""):
            return button.click().run()
    return at


def _labels(at: AppTest) -> set[str]:
    return {button.label or "" for button in at.button}


class AppModeTests(unittest.TestCase):
    def test_three_modes_keep_rsf_off_the_university_screen(self):
        at = AppTest.from_file(str(APP_PATH), default_timeout=20)
        _login(at)
        self.assertFalse(at.exception)
        options = list(at.radio[0].options)
        self.assertEqual(options, ["Мониторинг ГАГУ", "РНФ", "Поиск по автору"])

        labels = _labels(at)
        self.assertIn("Найти публикации", labels)
        self.assertNotIn("Статьи ГАГУ за текущий год", labels)
        self.assertFalse(any("От 8 статей" in item or "От 5 статей" in item for item in labels))
        self.assertFalse(any("Авторы ГАГУ" in item for item in labels))
        self.assertIn("Как считаем", {item.label for item in at.expander})

        at.radio[0].set_value("РНФ").run()
        self.assertFalse(at.exception)
        labels = _labels(at)
        self.assertIn("От 8 статей", labels)
        self.assertIn("От 5 статей", labels)
        self.assertNotIn("Статьи ГАГУ за текущий год", labels)
        self.assertNotIn("Найти публикации", labels)
        self.assertFalse(any("Авторы ГАГУ" in item for item in labels))

        at.radio[0].set_value("Поиск по автору").run()
        self.assertFalse(at.exception)
        labels = _labels(at)
        self.assertIn("Найти публикации", labels)
        self.assertFalse(any("От 8 статей" in item or "От 5 статей" in item for item in labels))
        self.assertIn("Автор", {item.label for item in at.text_input})
        self.assertNotIn("Фамилия", {item.label for item in at.text_input})

    def test_university_search_does_not_advertise_hindex_spinner(self):
        text = APP_PATH.read_text(encoding="utf-8")
        self.assertNotIn("Загружаем профили Scopus: Author ID, ORCID, h-индекс", text)
        self.assertIn("Загружаем профиль Scopus...", text)

    def test_all_modes_try_abstract_retrieval_for_coauthors(self):
        text = APP_PATH.read_text(encoding="utf-8")
        self.assertIn("Дополняем соавторов по карточкам статей и DOI, если Search отдал только первого...", text)
        self.assertIn('{"view": "FULL"}', text)
        self.assertIn("fetch_crossref_authors", text)
        self.assertNotIn("if truncated and saved_mode in {MODE_UNIVERSITY, MODE_RSF}:", text)
        enrich_idx = text.index("enrich_record_authors(records, api_key)")
        authid_guard = text.find("if not authid_ready:", 0, enrich_idx)
        self.assertEqual(authid_guard, -1)


    def test_last_five_years_radio_stays_selected(self):
        at = AppTest.from_file(str(APP_PATH), default_timeout=20)
        _login(at)
        self.assertFalse(at.exception)
        self.assertGreaterEqual(len(at.radio), 2)
        period = at.radio[1]
        self.assertEqual(period.label, "Период")
        self.assertIn("Последние 5 лет", period.options)
        at.radio[1].set_value("Последние 5 лет").run()
        self.assertFalse(at.exception)
        self.assertEqual(at.radio[1].value, "Последние 5 лет")


class LastFiveYearsSearchTests(unittest.TestCase):
    def test_find_sends_pubyear_range_and_reads_past_first_page(self):
        os.environ["SCOPUS_API_KEY"] = "test-key"
        queries = []
        starts = []

        def _entry(year: str, title: str, idx: int) -> dict:
            return {
                "dc:title": title,
                "dc:identifier": f"SCOPUS_ID:{idx}",
                "prism:coverDate": f"{year}-06-01",
                "prism:publicationName": "Test Journal",
                "affiliation": [{"affilname": "Gorno-Altaisk State University"}],
                "author": [{"surname": "Ivanov", "given-name": "I", "initials": "I.", "authid": "1"}],
            }

        def fake_get(url, headers=None, params=None, timeout=None):
            params = params or {}
            resp = MagicMock()
            resp.status_code = 200
            resp.text = "{}"
            url = str(url)
            if "search/scopus" in url:
                queries.append(params.get("query") or "")
                start = int(params.get("start") or 0)
                starts.append(start)
                if start == 0:
                    entries = [_entry("2026", f"New {i}", i) for i in range(25)]
                    total = "25"
                else:
                    entries = [_entry("2022", "Older paper", 100)]
                    total = "26"
                resp.json.return_value = {
                    "search-results": {
                        "opensearch:totalResults": total,
                        "entry": entries,
                    }
                }
            else:
                resp.json.return_value = {"search-results": {"opensearch:totalResults": "0", "entry": []}}
            return resp

        with patch("requests.get", side_effect=fake_get):
            at = AppTest.from_file(str(APP_PATH), default_timeout=30)
            _login(at)
            self.assertFalse(at.exception)
            at.radio[1].set_value("Последние 5 лет").run()
            self.assertFalse(at.exception)
            clicked = False
            for button in at.button:
                if button.label == "Найти публикации":
                    button.click().run()
                    clicked = True
                    break
            self.assertTrue(clicked)

        paper_queries = [q for q in queries if "AFFILORG(" in q]
        self.assertTrue(paper_queries)
        self.assertTrue(any("PUBYEAR > 2021" in q and "PUBYEAR < 2027" in q for q in paper_queries))
        self.assertFalse(any("PUBYEAR IS 2026" in q for q in paper_queries))
        self.assertIn(25, starts)
        records = list(at.session_state["records"] or [])
        years = {rec["year"] for rec in records}
        self.assertIn("2026", years)
        self.assertIn("2022", years)


if __name__ == "__main__":
    unittest.main()
