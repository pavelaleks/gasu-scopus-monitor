import unittest
from datetime import date

from rsf import record_in_rsf_window, rsf_window


class RsfWindowTests(unittest.TestCase):
    def test_2026_maps_to_2027_contest_from_january_2021(self):
        window = rsf_window(date(2026, 8, 31))
        self.assertEqual(window.contest_year, 2027)
        self.assertEqual(window.from_year, 2021)
        self.assertEqual(window.to_year, 2026)
        self.assertEqual(window.from_label, "января 2021")

    def test_window_shifts_next_calendar_year(self):
        window = rsf_window(date(2027, 1, 1))
        self.assertEqual(window.contest_year, 2028)
        self.assertEqual(window.from_year, 2022)
        self.assertEqual(window.to_year, 2027)

    def test_cover_date_from_january_counts(self):
        window = rsf_window(date(2026, 8, 31))
        self.assertTrue(record_in_rsf_window({"cover_date": "2021-01-15", "year": "2021"}, window))
        self.assertFalse(record_in_rsf_window({"cover_date": "2020-12-31", "year": "2020"}, window))
        self.assertTrue(record_in_rsf_window({"cover_date": "", "year": "2023"}, window))


if __name__ == "__main__":
    unittest.main()
