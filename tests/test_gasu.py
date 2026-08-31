import unittest

from gasu import (
    AFFILIATION_ID,
    GASU_PREFERRED_NAME,
    build_query,
    format_affiliations,
    gasu_affiliation_clause,
    has_gasu_affiliation,
)


class GasuQueryTests(unittest.TestCase):
    def test_clause_does_not_use_short_acronym(self):
        clause = gasu_affiliation_clause()
        self.assertIn(f"AF-ID({AFFILIATION_ID})", clause)
        self.assertNotIn('AFFIL("GASU")', clause)
        self.assertIn("Gorno-Altaisk State University", clause)

    def test_monitoring_query_keeps_all_gasu_hits(self):
        query = build_query(
            "Мониторинг ГАГУ",
            "",
            "",
            {"mode": "current", "year": 2026, "year_start": 2026, "year_end": 2026},
            False,
        )
        self.assertTrue(query.startswith("(AF-ID("))
        self.assertIn("PUBYEAR IS 2026", query)
        self.assertNotIn('AFFIL("GASU")', query)

    def test_author_search_without_gasu_filter_does_not_restrict_affiliation(self):
        query = build_query("Поиск по автору", "Alekseev", "", None, False)
        self.assertNotIn("AF-ID(", query)

    def test_author_search_with_gasu_uses_af_id(self):
        query = build_query("Поиск по автору", "Alekseev", "", None, True)
        self.assertIn(f"AF-ID({AFFILIATION_ID})", query)


class MultiAffiliationTests(unittest.TestCase):
    def test_gasu_as_second_affiliation_is_detected(self):
        entry = {
            "affiliation": [
                {"affilname": "Lomonosov Moscow State University"},
                {"affilname": "Gorno-Altaisk State University"},
            ]
        }
        self.assertTrue(has_gasu_affiliation(entry))
        text = format_affiliations(entry)
        self.assertIn("Gorno-Altaisk State University", text)
        self.assertIn("Lomonosov Moscow State University", text)
        self.assertTrue(text.startswith("Gorno-Altaisk State University"))

    def test_author_afid_keeps_paper_when_payload_shows_other_org(self):
        """STANDARD/неполный ответ часто отдаёт только первую организацию."""
        entry = {
            "affiliation": [{"affilname": "Tomsk State University"}],
            "author": [
                {
                    "surname": "Alekseev",
                    "afid": [{"$": AFFILIATION_ID}, {"$": "60015150"}],
                }
            ],
        }
        self.assertTrue(has_gasu_affiliation(entry))
        text = format_affiliations(entry, ensure_gasu=True)
        self.assertIn(GASU_PREFERRED_NAME, text)
        self.assertIn("Tomsk State University", text)

    def test_query_match_does_not_invent_gasu_affiliation(self):
        entry = {"affiliation": [{"affilname": "Innopolis University"}]}
        self.assertFalse(has_gasu_affiliation(entry))
        text = format_affiliations(entry, ensure_gasu=True)
        self.assertNotIn(GASU_PREFERRED_NAME, text)
        self.assertEqual(text, "Innopolis University")

    def test_variant_spelling_counts_as_gasu(self):
        entry = {"affiliation": [{"affilname": "Gorno-Altaysk State University, Russian Federation"}]}
        self.assertTrue(has_gasu_affiliation(entry))


if __name__ == "__main__":
    unittest.main()
