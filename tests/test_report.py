import unittest

from report import build_report, has_external_affiliation, report_sentence


class ReportTests(unittest.TestCase):
    def test_year_counts_fill_gaps_and_yoy(self):
        records = [
            {"year": "2024", "journal": "A", "affiliation": "Gorno-Altaisk State University"},
            {"year": "2024", "journal": "A", "affiliation": "Gorno-Altaisk State University"},
            {"year": "2026", "journal": "B", "affiliation": "Gorno-Altaisk State University; Innopolis University"},
        ]
        report = build_report(records)
        self.assertEqual(report.total, 3)
        self.assertEqual(report.year_label, "2024–2026")
        self.assertEqual(report.counts, {2024: 2, 2025: 0, 2026: 1})
        self.assertEqual(report.year_rows[0]["К предыдущему году"], "—")
        self.assertEqual(report.year_rows[1]["Публикаций"], 0)
        self.assertEqual(report.year_rows[2]["К предыдущему году"], "н/д")
        self.assertEqual(report.unique_journals, 2)
        self.assertEqual(report.external_count, 1)
        self.assertEqual(report.external_share, 33.3)
        self.assertEqual(report.top_journals[0][0], "A")

    def test_single_year_has_no_change(self):
        records = [{"year": "2026", "journal": "X", "affiliation": "Gorno-Altai State University"}]
        report = build_report(records)
        self.assertEqual(report.distinct_years, 1)
        self.assertEqual(report.year_rows[0]["К предыдущему году"], "—")

    def test_external_affiliation(self):
        self.assertFalse(has_external_affiliation("Gorno-Altaisk State University"))
        self.assertTrue(
            has_external_affiliation("Gorno-Altaisk State University; Tomsk State University")
        )

    def test_sentence_includes_last_year(self):
        records = [
            {"year": "2025", "journal": "A", "affiliation": "Gorno-Altaisk State University"},
            {"year": "2026", "journal": "A", "affiliation": "Gorno-Altaisk State University"},
            {"year": "2026", "journal": "A", "affiliation": "Gorno-Altaisk State University"},
        ]
        text = report_sentence(build_report(records))
        self.assertIn("2025–2026", text)
        self.assertIn("2026 году — 2", text)
        self.assertIn("+100%", text)


if __name__ == "__main__":
    unittest.main()
