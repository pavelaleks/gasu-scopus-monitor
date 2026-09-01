import unittest

from gasu import (
    AFFILIATION_ID,
    GASU_FOUNDED_YEAR,
    GASU_PREFERRED_NAME,
    author_belongs_to_gasu,
    author_id_query,
    author_ids,
    author_papers_query,
    author_profile_query,
    build_query,
    entry_belongs_to_gasu,
    format_affiliations,
    gasu_affiliation_clause,
    has_gasu_affiliation,
    match_authid_on_paper,
    needs_author_enrichment,
    normalize_orcid,
    orcid_id_query,
    parse_author_query,
    parse_author_retrieval,
    parse_author_search_profile,
    parse_author_text,
    parse_authors,
    pick_scopus_authid,
    profile_display_name,
    record_has_gasu,
    record_sort_key,
    scopus_authid,
    truncated_author_paper_count,
)


class GasuQueryTests(unittest.TestCase):
    def test_clause_uses_full_names_not_acronym_or_afid(self):
        clause = gasu_affiliation_clause()
        self.assertIn("AFFILORG(", clause)
        self.assertIn("Gorno-Altaisk State University", clause)
        self.assertIn("Gorno-Altai State University", clause)
        self.assertNotIn('AFFIL("GASU")', clause)
        self.assertNotIn(f"AF-ID({AFFILIATION_ID})", clause)

    def test_rsf_query_uses_gasu_names_and_window(self):
        query = build_query(
            "РНФ",
            "",
            "",
            {"mode": "range", "year": 2021, "year_start": 2021, "year_end": 2026},
            False,
        )
        self.assertIn("AFFILORG(", query)
        self.assertIn("Gorno-Altaisk State University", query)
        self.assertIn("PUBYEAR > 2020", query)
        self.assertIn("PUBYEAR < 2027", query)
        self.assertNotIn("AUTH(", query)
        self.assertNotIn(f"AF-ID({AFFILIATION_ID})", query)

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

    def test_parse_author_query_accepts_orcid_url_authid_or_surname(self):
        orcid = parse_author_query("https://orcid.org/0000-0002-8043-4014")
        self.assertEqual(orcid["kind"], "orcid")
        self.assertEqual(orcid["orcid"], "0000-0002-8043-4014")
        self.assertEqual(orcid["authid"], "")
        self.assertEqual(orcid["surname"], "")

        authid = parse_author_query("57222578674")
        self.assertEqual(authid["kind"], "au-id")
        self.assertEqual(authid["authid"], "57222578674")
        self.assertEqual(authid["orcid"], "")

        surname = parse_author_query("Сафонова П.В.")
        self.assertEqual(surname["kind"], "surname")
        self.assertEqual(surname["surname"], "Сафонова")
        self.assertEqual(surname["orcid"], "")
        self.assertEqual(parse_author_query(""), {"kind": "", "orcid": "", "authid": "", "surname": ""})

    def test_author_search_with_orcid_is_person_query(self):
        query = build_query(
            "Поиск по автору",
            "Alekseev",
            "https://orcid.org/0000-0003-3680-1785",
            {"mode": "range", "year_start": 2021, "year_end": 2026},
            False,
        )
        self.assertEqual(normalize_orcid("https://orcid.org/0000-0003-3680-1785"), "0000-0003-3680-1785")
        self.assertIn('ORCID("0000-0003-3680-1785")', query)
        self.assertIn("PUBYEAR > 2020", query)
        self.assertNotIn("AFFILORG(", query)
        self.assertNotIn("AUTH(", query.replace("AUTHLAST", ""))
        self.assertEqual(
            orcid_id_query("0000-0003-3680-1785", 2021, 2026),
            'ORCID("0000-0003-3680-1785") AND PUBYEAR > 2020 AND PUBYEAR < 2027',
        )

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
        id_only = {"surname": "Alekseev", "affiliation": {"@id": "https://api.elsevier.com/content/affiliation/affiliation_id/60105869"}}
        self.assertIsNone(author_belongs_to_gasu(id_only))
        self.assertEqual(scopus_authid({"authid": "57202111111"}), "57202111111")
        self.assertEqual(
            scopus_authid({"author-url": "https://api.elsevier.com/content/author/author_id/57202111111"}),
            "57202111111",
        )
        self.assertEqual(author_id_query("57202111111", 2021, 2026), "AU-ID(57202111111) AND PUBYEAR > 2020 AND PUBYEAR < 2027")
        profile = author_profile_query("Alekseev", "P.V.")
        self.assertIn('AUTHLAST("Alekseev")', profile)
        self.assertIn("AUTHFIRST(P)", profile)
        self.assertIn("AFFIL(", profile)
        self.assertNotIn("AUTH(", profile.replace("AUTHLAST", "").replace("AUTHFIRST", ""))
        open_query = author_profile_query("Alekseev", "P.V.", gasu_only=False)
        self.assertIn('AUTHLAST("Alekseev")', open_query)
        self.assertNotIn("AFFIL(", open_query)
        papers = author_papers_query(
            "57202111111",
            {"mode": "range", "year_start": 2021, "year_end": 2026},
            False,
        )
        self.assertEqual(papers, "AU-ID(57202111111) AND PUBYEAR > 2020 AND PUBYEAR < 2027")
        self.assertTrue(record_has_gasu({"affiliation": "Gorno-Altaisk State University; Tomsk State University"}))
        self.assertFalse(record_has_gasu({"affiliation": "Tomsk State University"}))

    def test_parse_authors_from_complete_and_abstract(self):
        complete = {
            "author": [
                {
                    "authid": "57200000001",
                    "surname": "Alekseev",
                    "given-name": "Pavel",
                    "initials": "P.V.",
                },
                {
                    "@auid": "57200000002",
                    "authname": "Kyrov, V.N.",
                },
            ]
        }
        names = {(a["surname"], a["authid"]) for a in parse_authors(complete)}
        self.assertEqual(
            names,
            {("Alekseev", "57200000001"), ("Kyrov", "57200000002")},
        )
        abstract = {
            "abstracts-retrieval-response": {
                "authors": {
                    "author": [
                        {
                            "@auid": "57200000001",
                            "preferred-name": {
                                "ce:surname": "Alekseev",
                                "ce:given-name": "Pavel V.",
                                "ce:initials": "P.V.",
                            },
                        }
                    ]
                }
            }
        }
        parsed = parse_authors(abstract)
        self.assertEqual(parsed[0]["surname"], "Alekseev")
        self.assertEqual(parsed[0]["authid"], "57200000001")
        self.assertEqual(
            scopus_authid({"@auid": "57200000009"}),
            "57200000009",
        )

    def test_pick_authid_prefers_unique_profile(self):
        entries = [
            {
                "dc:identifier": "AUTHOR_ID:57200000001",
                "preferred-name": {"surname": "Alekseev", "given-name": "Pavel", "initials": "P.V."},
                "affiliation-current": {
                    "affiliation-name": "Tomsk State University",
                    "affiliation-city": "Tomsk",
                },
            }
        ]
        self.assertEqual(
            pick_scopus_authid(entries, surname="Alekseev", initials="P.V."),
            "57200000001",
        )

    def test_pick_authid_does_not_guess_two_same_initials(self):
        entries = [
            {
                "dc:identifier": "AUTHOR_ID:11111111111",
                "preferred-name": {"initials": "P.A."},
                "affiliation-current": {"affiliation-name": "Gorno-Altaisk State University"},
            },
            {
                "dc:identifier": "AUTHOR_ID:22222222222",
                "preferred-name": {"initials": "P.V."},
                "affiliation-current": {"affiliation-name": "Gorno-Altaisk State University"},
            },
        ]
        self.assertEqual(pick_scopus_authid(entries, surname="Alekseev", initials="P."), "")

    def test_match_authid_on_paper_by_surname_and_initial(self):
        authors = [
            {"surname": "Kyrov", "initials": "V.A.", "authid": "11111111111"},
            {"surname": "Alekseev", "initials": "P.", "authid": "57200000001"},
        ]
        self.assertEqual(
            match_authid_on_paper(authors, "Alekseev", "P.V."),
            "57200000001",
        )
        self.assertEqual(match_authid_on_paper(authors, "Ivanov", "I."), "")

    def test_needs_author_enrichment_when_list_is_truncated(self):
        self.assertFalse(needs_author_enrichment({"authors": [{"authid": "1"}]}))
        self.assertTrue(
            needs_author_enrichment(
                {"scopus_id": "851", "authors": [{"surname": "Alekseev", "authid": "57200000001"}]}
            )
        )
        self.assertTrue(
            needs_author_enrichment(
                {
                    "scopus_id": "851",
                    "authors": [
                        {"surname": "Alekseev", "authid": ""},
                        {"surname": "Kyrov", "authid": "11111111111"},
                    ],
                }
            )
        )
        self.assertFalse(
            needs_author_enrichment(
                {
                    "scopus_id": "851",
                    "authors": [
                        {"surname": "Alekseev", "authid": "57200000001"},
                        {"surname": "Kyrov", "authid": "11111111111"},
                    ],
                }
            )
        )
        self.assertEqual(
            author_ids(
                [
                    {"authid": "57200000001"},
                    {"authid": "57200000001"},
                    {"authid": "11111111111"},
                ]
            ),
            ["57200000001", "11111111111"],
        )

    def test_parse_author_search_and_retrieval_profile(self):
        search = parse_author_search_profile(
            {
                "dc:identifier": "AUTHOR_ID:58102647800",
                "orcid": "0000-0003-3680-1785",
                "document-count": "13",
                "cited-by-count": "10",
                "preferred-name": {
                    "surname": "Alekseev",
                    "given-name": "Pavel",
                    "initials": "P.V.",
                },
                "affiliation-current": {
                    "affiliation-name": "Gorno-Altaisk State University",
                    "affiliation-city": "Gorno-Altaysk",
                    "affiliation-country": "Russian Federation",
                },
            }
        )
        self.assertEqual(search["authid"], "58102647800")
        self.assertEqual(search["orcid"], "0000-0003-3680-1785")
        self.assertEqual(search["documents"], 13)
        self.assertEqual(search["cited_by"], 10)
        self.assertIn("Gorno-Altaisk", search["profile_affil"])
        self.assertIn("Russian Federation", search["profile_affil"])
        retrieval = parse_author_retrieval(
            {
                "author-retrieval-response": [
                    {
                        "h-index": "1",
                        "coauthor-count": "20",
                        "coredata": {
                            "dc:identifier": "AUTHOR_ID:57222578674",
                            "orcid": "0000-0002-8043-4014",
                            "document-count": "8",
                            "cited-by-count": "3",
                            "citation-count": "3",
                        },
                        "author-profile": {
                            "preferred-name": {
                                "surname": "Safonova",
                                "given-name": "Varvara Yu",
                                "initials": "V.Y.",
                            },
                            "affiliation-current": {
                                "affiliation-name": "Gorno-Altaisk State University",
                                "affiliation-city": "Gorno-Altaysk",
                                "affiliation-country": "Russian Federation",
                            },
                        },
                    }
                ]
            }
        )
        self.assertEqual(retrieval["h_index"], 1)
        self.assertEqual(retrieval["documents"], 8)
        self.assertEqual(retrieval["cited_by"], 3)
        self.assertEqual(retrieval["orcid"], "0000-0002-8043-4014")
        self.assertEqual(profile_display_name(retrieval), "Safonova, Varvara Yu")
        self.assertIn("Gorno-Altaisk", retrieval["profile_affil"])
        self.assertIn("Russian Federation", retrieval["profile_affil"])

    def test_parse_author_text_keeps_coauthors_not_only_first(self):
        names = [item["surname"] for item in parse_author_text(
            "Frolov, I.N., Kudryavtsev, N.G., Safonova, V.Yu."
        )]
        self.assertEqual(names, ["Frolov", "Kudryavtsev", "Safonova"])
        parsed = parse_authors(
            {
                "dc:creator": "Frolov, I.N.",
                "author": "Frolov, I.N., Kudryavtsev, N.G., Safonova, V.Yu.",
            }
        )
        self.assertEqual([item["surname"] for item in parsed], ["Frolov", "Kudryavtsev", "Safonova"])
        self.assertEqual(
            truncated_author_paper_count(
                [
                    {"authors": parsed},
                    {"authors": [{"surname": "Frolov"}]},
                ]
            ),
            1,
        )

    def test_records_sort_by_surname_then_newest_year(self):
        records = [
            {"authors": [{"surname": "Safonova"}], "year": "2024", "title": "A"},
            {"authors": [{"surname": "Alekseev"}], "year": "2023", "title": "Old"},
            {"authors": [{"surname": "Alekseev"}], "year": "2025", "title": "New"},
        ]
        ordered = sorted(records, key=record_sort_key)
        self.assertEqual(
            [(item["authors"][0]["surname"], item["year"]) for item in ordered],
            [("Alekseev", "2025"), ("Alekseev", "2023"), ("Safonova", "2024")],
        )


if __name__ == "__main__":
    unittest.main()
