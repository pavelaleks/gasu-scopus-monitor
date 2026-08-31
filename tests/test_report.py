import unittest

from report import (
    apply_author_total,
    build_report,
    has_external_affiliation,
    report_area_png,
    report_chart_png,
    report_quartile_png,
    report_scope_label,
    report_sentence,
    rsf_candidates,
    rsf_eligibility_rows,
    ru_publications,
    top_authors,
)


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

    def test_quartile_png_is_compact(self):
        png = report_quartile_png([{"Квартиль": "Q1", "Публикаций": 10}, {"Квартиль": "Q2", "Публикаций": 5}])
        self.assertTrue(png.startswith(b"\x89PNG"))
        self.assertLess(len(png), 120_000)

    def test_scope_label_university_and_author(self):
        records = [
            {
                "year": "2022",
                "authors": [{"surname": "Alekseev", "given": "Pavel", "initials": "P.V."}],
            },
            {"year": "2026", "authors": [{"surname": "Alekseev", "given": "Pavel", "initials": "P.V."}]},
        ]
        self.assertEqual(report_scope_label(records, university=True), "ГАГУ, 2022–2026")
        self.assertEqual(
            report_scope_label(records, university=False, author_last="Alekseev"),
            "Alekseev P.V., 2022–2026",
        )
        self.assertEqual(report_scope_label(records, university=True, year="2024"), "ГАГУ, 2024")

    def test_top_authors_counts_papers_and_quartiles(self):
        records = [
            {
                "scimago_quartile": "Q1",
                "authors": [
                    {"surname": "Ivanov", "given": "Ivan", "initials": "I.I."},
                    {"surname": "Petrov", "given": "Petr", "initials": "P.P."},
                ],
            },
            {
                "scimago_quartile": "Q2",
                "authors": [{"surname": "Ivanov", "given": "I", "initials": "I."}],
            },
            {
                "scimago_quartile": "Нет",
                "authors": [{"surname": "Petrov", "given": "Petr", "initials": "P.P."}],
            },
        ]
        rows = top_authors(records, 10)
        by_name = {row["Автор"]: row for row in rows}
        self.assertEqual(by_name["Ivanov I.I."]["Публикаций"], 2)
        self.assertEqual(by_name["Ivanov I.I."]["Q1"], 1)
        self.assertEqual(by_name["Ivanov I.I."]["Q2"], 1)
        self.assertEqual(by_name["Petrov P.P."]["Публикаций"], 2)
        self.assertEqual(by_name["Petrov P.P."]["Без квартиля"], 1)
        self.assertEqual(rows[0]["Автор"], "Ivanov I.I.")

    def test_rsf_keeps_coauthors_on_gasu_papers(self):
        records = [
            {
                "authors": [
                    {"surname": "Ivanov", "given": "I", "initials": "I.", "from_gasu": True},
                    {"surname": "Petrov", "given": "P", "initials": "P.", "from_gasu": False},
                ]
            }
            for _ in range(8)
        ]
        names = [row["Автор"] for row in rsf_eligibility_rows(rsf_candidates(records), 8)]
        self.assertEqual(names, ["Ivanov I.", "Petrov P."])

    def test_rsf_excludes_chanchaeva_and_keeps_alekseev(self):
        records = [
            {
                "authors": [
                    {"surname": "Alekseev", "given": "Pavel", "initials": "P.V.", "from_gasu": False},
                    {"surname": "Chanchaeva", "given": "E", "initials": "E.A.", "from_gasu": True},
                ]
            }
            for _ in range(8)
        ]
        names = [row["Автор"] for row in rsf_eligibility_rows(rsf_candidates(records), 8)]
        self.assertEqual(names, ["Alekseev P.V."])

    def test_rsf_threshold_uses_all_scopus_papers(self):
        gasu_paper = {
            "year": "2022",
            "cover_date": "2022-03-01",
            "affiliation": "Gorno-Altaisk State University",
            "authors": [
                {
                    "surname": "Alekseev",
                    "given": "Pavel",
                    "initials": "P.V.",
                    "from_gasu": False,
                    "authid": "57200000000",
                }
            ],
        }
        candidates = rsf_candidates([gasu_paper, dict(gasu_paper), dict(gasu_paper)])
        self.assertEqual(candidates[0]["С ГАГУ"], 3)
        self.assertEqual(candidates[0]["Всего Scopus"], 3)
        apply_author_total(candidates[0], 8)
        self.assertEqual(candidates[0]["Всего Scopus"], 8)
        self.assertEqual(candidates[0]["С ГАГУ"], 3)
        self.assertEqual(candidates[0]["Учёт"], "все статьи автора")
        rows = rsf_eligibility_rows(candidates, 8)
        self.assertEqual([row["Автор"] for row in rows], ["Alekseev P.V."])
        self.assertNotIn("authid", rows[0])

    def test_rsf_merges_alekseev_p_and_pv(self):
        records = [
            {"authors": [{"surname": "Alekseev", "initials": "P."}]},
            {"authors": [{"surname": "Alekseev", "initials": "P.V."}]},
        ]
        rows = rsf_candidates(records)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["С ГАГУ"], 2)
        self.assertIn("Alekseev", rows[0]["Автор"])


if __name__ == "__main__":
    unittest.main()
