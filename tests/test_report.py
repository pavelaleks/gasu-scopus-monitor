import unittest

from report import build_report, has_external_affiliation, report_area_png, report_chart_png, report_sentence, ru_publications


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
        self.assertEqual(report.year_rows[0]["Изменение к предыдущему году"], "—")
        self.assertEqual(report.year_rows[1]["Публикаций"], 0)
        self.assertEqual(report.year_rows[2]["Изменение к предыдущему году"], "н/д")
        self.assertEqual(report.unique_journals, 2)
        self.assertEqual(report.external_count, 1)
        self.assertEqual(report.external_share, 33.3)
        self.assertEqual(report.top_journals[0][0], "A")

    def test_single_year_has_no_change(self):
        records = [{"year": "2026", "journal": "X", "affiliation": "Gorno-Altai State University"}]
        report = build_report(records)
        self.assertEqual(report.distinct_years, 1)
        self.assertEqual(report.year_rows[0]["Изменение к предыдущему году"], "—")

    def test_external_affiliation(self):
        self.assertFalse(has_external_affiliation("Gorno-Altaisk State University"))
        self.assertTrue(
            has_external_affiliation("Gorno-Altaisk State University; Tomsk State University")
        )

    def test_sentence_is_period_total_only(self):
        records = [
            {"year": "2025", "journal": "A", "affiliation": "Gorno-Altaisk State University"},
            {"year": "2026", "journal": "A", "affiliation": "Gorno-Altaisk State University"},
            {"year": "2026", "journal": "A", "affiliation": "Gorno-Altaisk State University"},
        ]
        text = report_sentence(build_report(records))
        self.assertEqual(text, "За 2025–2026 годы: 3 публикации.")
        self.assertNotIn("%", text)
        self.assertNotIn("2026 году", text)

    def test_ru_publications_plural(self):
        self.assertEqual(ru_publications(1), "1 публикация")
        self.assertEqual(ru_publications(3), "3 публикации")
        self.assertEqual(ru_publications(83), "83 публикации")

    def test_chart_png_is_compact(self):
        records = [
            {"year": "2024", "journal": "A", "affiliation": "Gorno-Altaisk State University"},
            {"year": "2026", "journal": "A", "affiliation": "Gorno-Altaisk State University"},
        ]
        png = report_chart_png(build_report(records))
        self.assertTrue(png.startswith(b"\x89PNG"))
        self.assertLess(len(png), 80_000)

    def test_area_png_is_compact(self):
        png = report_area_png([("Социальные науки", 12), ("Инженерия", 5), ("Не указано", 2)])
        self.assertTrue(png.startswith(b"\x89PNG"))
        self.assertLess(len(png), 120_000)


if __name__ == "__main__":
    unittest.main()
