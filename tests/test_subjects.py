import unittest

from subjects import (
    UNKNOWN_AREA,
    area_share_rows,
    attach_subject_areas,
    extract_issns,
    format_subject_areas,
    grouped_area_counts,
    normalize_issn,
    parse_serial_abbrevs,
)


SERIAL_SAMPLE = {
    "serial-metadata-response": {
        "entry": [
            {
                "subject-area": [
                    {"@code": "2303", "@abbrev": "ENVI", "$": "Ecology"},
                    {"@code": "1105", "@abbrev": "AGRI", "$": "Ecology, Evolution, Behavior and Systematics"},
                    {"@code": "2303", "@abbrev": "ENVI", "$": "Ecology"},
                ]
            }
        ]
    }
}


class SubjectTests(unittest.TestCase):
    def test_normalize_issn(self):
        self.assertEqual(normalize_issn("1234-5678"), "12345678")
        self.assertEqual(normalize_issn("12345678X extra"), "12345678")
        self.assertIsNone(normalize_issn("12"))

    def test_extract_issns_print_and_electronic(self):
        entry = {"prism:issn": "1234-5678", "prism:eIssn": "8765-4321"}
        self.assertEqual(extract_issns(entry), ["12345678", "87654321"])

    def test_parse_serial_keeps_unique_top_level(self):
        self.assertEqual(parse_serial_abbrevs(SERIAL_SAMPLE), ["ENVI", "AGRI"])

    def test_parse_serial_uses_code_prefix_if_abbrev_missing(self):
        payload = {
            "entry": [{"subject-area": {"@code": "3304", "$": "Education"}}]
        }
        self.assertEqual(parse_serial_abbrevs(payload), ["SOCI"])

    def test_parse_serial_physics_code(self):
        payload = {"entry": [{"subject-area": {"@code": "3101"}}]}
        self.assertEqual(parse_serial_abbrevs(payload), ["PHYS"])

    def test_format_subject_areas(self):
        text = format_subject_areas(["ENVI", "AGRI"])
        self.assertIn("Науки об окружающей среде", text)
        self.assertIn("Сельскохозяйственные и биологические науки", text)

    def test_attach_uses_cache_and_primary(self):
        records = [
            {"issns": ["11112222"], "year": "2026"},
            {"issns": ["11112222"], "year": "2025"},
            {"issns": [], "year": "2026"},
        ]
        calls = []

        def fake_fetch(issn, api_key):
            calls.append(issn)
            return ["SOCI", "ARTS"], 200

        attach_subject_areas(records, "key", {}, fetch=fake_fetch, sleep_s=0)
        self.assertEqual(calls, ["11112222"])
        self.assertEqual(records[0]["subject_abbrevs"], ["SOCI", "ARTS"])
        self.assertIn("Социальные науки", records[0]["subject_areas"])
        self.assertEqual(records[2]["subject_areas"], UNKNOWN_AREA)

        rows = area_share_rows(records)
        self.assertEqual(rows[0]["Область знаний"], "Социальные науки")
        self.assertEqual(rows[0]["Публикаций"], 2)
        year_rows = area_share_rows(records, "2026")
        labels = {row["Область знаний"]: row["Публикаций"] for row in year_rows}
        self.assertEqual(labels["Социальные науки"], 1)
        self.assertEqual(labels[UNKNOWN_AREA], 1)

    def test_group_small_tail(self):
        rows = [{"Область знаний": f"A{i}", "Публикаций": 10 - i} for i in range(10)]
        grouped = grouped_area_counts(rows, max_slices=8)
        self.assertEqual(len(grouped), 8)
        self.assertEqual(grouped[-1][0], "Прочие")
        self.assertEqual(grouped[-1][1], sum(10 - i for i in range(7, 10)))


if __name__ == "__main__":
    unittest.main()
