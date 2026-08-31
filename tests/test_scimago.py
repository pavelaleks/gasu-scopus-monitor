import unittest

import pandas as pd

from scimago import (
    UNKNOWN_QUARTILE,
    ScimagoIndex,
    attach_scimago,
    format_quartile_cell,
    quartile_share_rows,
    slim_from_frame,
    split_issns,
)


class ScimagoTests(unittest.TestCase):
    def test_split_issns(self):
        self.assertEqual(split_issns("1234-5678, 87654321"), ["12345678", "87654321"])

    def test_lookup_same_year_then_latest(self):
        slim = pd.DataFrame(
            [
                {"issn": "12345678", "year": 2024, "quartile": "Q2", "sjr": 0.4},
                {"issn": "12345678", "year": 2025, "quartile": "Q1", "sjr": 0.6},
            ]
        )
        index = ScimagoIndex(slim)
        same = index.lookup(["12345678"], 2024)
        self.assertEqual(same.quartile, "Q2")
        self.assertTrue(same.matched)
        self.assertEqual(same.sjr_year, 2024)
        later = index.lookup(["12345678"], 2026)
        self.assertEqual(later.quartile, "Q1")
        self.assertFalse(later.matched)
        self.assertEqual(later.sjr_year, 2025)
        self.assertIsNone(index.lookup(["12345678"], 2023))
        self.assertIsNone(index.lookup(["00000000"], 2025))

    def test_attach_and_display(self):
        index = ScimagoIndex(
            pd.DataFrame([{"issn": "11112222", "year": 2025, "quartile": "Q3", "sjr": 0.21}])
        )
        records = [
            {"issns": ["11112222"], "year": "2026"},
            {"issns": ["11112222"], "year": "2025"},
            {"issns": [], "year": "2025"},
        ]
        attach_scimago(records, index)
        self.assertEqual(format_quartile_cell(records[0]), "Q3 (2025)")
        self.assertEqual(format_quartile_cell(records[1]), "Q3")
        self.assertEqual(format_quartile_cell(records[2]), UNKNOWN_QUARTILE)
        rows = quartile_share_rows(records)
        by_label = {row["Квартиль"]: row["Публикаций"] for row in rows}
        self.assertEqual(by_label["Q3"], 2)
        self.assertEqual(by_label[UNKNOWN_QUARTILE], 1)

    def test_slim_from_official_columns(self):
        frame = pd.DataFrame(
            {
                "Year": [2024, 2010],
                "Issn": ["1234-5678, 87654321", "11111111"],
                "SJR Best Quartile": ["Q1", "Q4"],
                "SJR": ["1,234", "0.1"],
            }
        )
        slim = slim_from_frame(frame)
        self.assertEqual(len(slim), 2)
        self.assertEqual(set(slim["issn"]), {"12345678", "87654321"})
        self.assertEqual(slim["quartile"].iloc[0], "Q1")
        self.assertEqual(slim["sjr"].iloc[0], 1.234)


if __name__ == "__main__":
    unittest.main()
