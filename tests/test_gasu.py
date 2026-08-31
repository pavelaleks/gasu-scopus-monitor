import unittest

from gasu import (
    AFFILIATION_ID,
    GASU_FOUNDED_YEAR,
    GASU_PREFERRED_NAME,
    author_belongs_to_gasu,
    build_query,
    entry_belongs_to_gasu,
    format_affiliations,
    gasu_affiliation_clause,
    has_gasu_affiliation,
)


class GasuQueryTests(unittest.TestCase):
    def test_clause_uses_full_names_not_acronym_or_afid(self):
        clause = gasu_affiliation_clause()
        self.assertIn("AFFILORG(", clause)
        self.assertIn("Gorno-Altaisk State University", clause)
        self.assertIn("Gorno-Altai State University", clause)
        self.assertNotIn('AFFIL("GASU")', clause)
        self.assertNotIn(f"AF-ID({AFFILIATION_ID})", clause)

    def test_monitoring_query_is_name_based(self):
        query = build_query(
            "Мониторинг ГАГУ",
            "",
            "",
            {"mode": "current", "year": 2026, "year_start": 2026, "year_end": 2026},
            False,
        )
        self.assertIn("AFFILORG(", query)
        self.assertIn("PUBYEAR IS 2026", query)
        self.assertNotIn("AF-ID(", query)
        self.assertNotIn('AFFIL("GASU")', query)

    def test_author_search_without_gasu_filter_does_not_restrict_affiliation(self):
        query = build_query("Поиск по автору", "Alekseev", "", None, False)
        self.assertNotIn("AFFILORG(", query)

    def test_author_search_with_gasu_uses_names(self):
        query = build_query("Поиск по автору", "Alekseev", "", None, True)
        self.assertIn("AFFILORG(", query)
        self.assertIn("Alekseev", query)

    def test_since_founding_uses_1993(self):
        self.assertEqual(GASU_FOUNDED_YEAR, 1993)
        query = build_query(
            "Мониторинг ГАГУ",
            "",
            "",
            {"mode": "range", "year": 2026, "year_start": GASU_FOUNDED_YEAR, "year_end": 2026},
            False,
        )
        self.assertIn("PUBYEAR > 1992", query)
        self.assertIn("PUBYEAR < 2027", query)


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

    def test_innopolis_with_legacy_afid_is_rejected(self):
        entry = {
            "affiliation": [
                {
                    "affilname": "Innopolis University",
                    "affiliation-city": "Innopolis",
                    "afid": AFFILIATION_ID,
                }
            ],
            "author": [{"surname": "Ivanov", "afid": [{"$": AFFILIATION_ID}]}],
        }
        self.assertFalse(entry_belongs_to_gasu(entry))
        self.assertNotIn(GASU_PREFERRED_NAME, format_affiliations(entry, ensure_gasu=True))

    def test_author_level_gasu_name_is_enough(self):
        entry = {
            "affiliation": [{"affilname": "Tomsk State University"}],
            "author": [
                {
                    "surname": "Alekseev",
                    "affiliation": {"affilname": "Gorno-Altaisk State University"},
                }
            ],
        }
        self.assertTrue(entry_belongs_to_gasu(entry))

    def test_gorno_altaisk_city_plus_university_counts(self):
        entry = {
            "affiliation": [
                {
                    "affilname": "State University",
                    "affiliation-city": "Gorno-Altaysk",
                }
            ]
        }
        self.assertTrue(entry_belongs_to_gasu(entry))

    def test_variant_spelling_counts_as_gasu(self):
        entry = {"affiliation": [{"affilname": "Gorno-Altaysk State University, Russian Federation"}]}
        self.assertTrue(has_gasu_affiliation(entry))

    def test_gorno_altai_without_sk_counts_as_gasu(self):
        entry = {"affiliation": [{"affilname": "Gorno-Altai State University"}]}
        self.assertTrue(has_gasu_affiliation(entry))
        self.assertIn("Gorno-Altai State University", gasu_affiliation_clause())

    def test_altai_state_university_is_not_gasu(self):
        entry = {"affiliation": [{"affilname": "Altai State University"}]}
        self.assertFalse(has_gasu_affiliation(entry))

    def test_author_belongs_to_gasu_from_own_affiliation(self):
        gasu_author = {"surname": "Ivanov", "affiliation": {"affilname": "Gorno-Altaisk State University"}}
        other = {"surname": "Petrov", "affiliation": {"affilname": "Tomsk State University"}}
        unknown = {"surname": "Sidorov"}
        self.assertTrue(author_belongs_to_gasu(gasu_author))
        self.assertFalse(author_belongs_to_gasu(other))
        self.assertIsNone(author_belongs_to_gasu(unknown))


if __name__ == "__main__":
    unittest.main()
