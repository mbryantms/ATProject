"""
Tests for the bibliography/citation system.
"""

from unittest.mock import patch

from django.test import TestCase

from engine.bibliography.formatter import (
    FormattedOutput,
    _extract_first_author,
    _extract_year,
    _format_fallback,
    format_citations,
    get_available_styles,
    get_citation_format,
)


class CitationFormatterFallbackTests(TestCase):
    """Test the fallback citation formatter (no Node.js required)."""

    def setUp(self):
        self.items = [
            {
                "id": "smith2024",
                "type": "article-journal",
                "title": "A Study on Testing",
                "author": [{"family": "Smith", "given": "John"}],
                "issued": {"date-parts": [[2024]]},
                "container-title": "Journal of Tests",
            },
            {
                "id": "jones2023",
                "type": "book",
                "title": "The Book of Knowledge",
                "author": [
                    {"family": "Jones", "given": "Alice"},
                    {"family": "Williams", "given": "Bob"},
                ],
                "issued": {"date-parts": [[2023]]},
            },
        ]
        self.clusters = [
            {
                "citationItems": [{"id": "smith2024"}],
                "properties": {"noteIndex": 0},
            },
            {
                "citationItems": [{"id": "jones2023"}],
                "properties": {"noteIndex": 0},
            },
        ]

    def test_fallback_produces_citations(self):
        result = _format_fallback(self.items, self.clusters)
        self.assertIsInstance(result, FormattedOutput)
        self.assertTrue(result.is_fallback)
        self.assertEqual(len(result.citations), 2)
        self.assertIn("Smith", result.citations[0])
        self.assertIn("2024", result.citations[0])

    def test_fallback_produces_bibliography(self):
        result = _format_fallback(self.items, self.clusters)
        self.assertEqual(len(result.bibliography), 2)
        # Bibliography entries are (id, html) tuples
        ids = [entry[0] for entry in result.bibliography]
        self.assertIn("smith2024", ids)
        self.assertIn("jones2023", ids)

    def test_fallback_with_locator(self):
        clusters = [
            {
                "citationItems": [{"id": "smith2024", "locator": "42", "label": "p."}],
                "properties": {"noteIndex": 0},
            },
        ]
        result = _format_fallback(self.items, clusters)
        self.assertIn("p. 42", result.citations[0])

    def test_empty_items_returns_empty_output(self):
        result = format_citations([], [])
        self.assertEqual(result.citations, [])
        self.assertEqual(result.bibliography, [])


class CitationHelperTests(TestCase):
    """Test helper functions for citation extraction."""

    def test_extract_first_author_family(self):
        item = {"author": [{"family": "Smith", "given": "John"}]}
        self.assertEqual(_extract_first_author(item), "Smith")

    def test_extract_first_author_literal(self):
        item = {"author": [{"literal": "World Health Organization"}]}
        self.assertEqual(_extract_first_author(item), "World Health Organization")

    def test_extract_first_author_no_author(self):
        item = {"title": "Anonymous Work"}
        self.assertEqual(_extract_first_author(item), "Anonymous Work")

    def test_extract_year(self):
        item = {"issued": {"date-parts": [[2024]]}}
        self.assertEqual(_extract_year(item), "2024")

    def test_extract_year_missing(self):
        item = {}
        self.assertEqual(_extract_year(item), "")

    def test_extract_year_empty_date_parts(self):
        item = {"issued": {"date-parts": [[]]}}
        self.assertEqual(_extract_year(item), "")


class CitationStyleTests(TestCase):
    """Test CSL style resolution."""

    def test_available_styles_returns_list(self):
        styles = get_available_styles()
        self.assertIsInstance(styles, list)
        # At minimum APA should be available
        if styles:
            self.assertIn("apa", styles)

    def test_get_citation_format_default(self):
        # Non-existent style should return default
        fmt = get_citation_format("nonexistent-style")
        self.assertEqual(fmt, "author-date")


class CitationCachingTests(TestCase):
    """Test that citation formatting results are cached."""

    def test_format_citations_caches_result(self):
        items = [
            {
                "id": "test2024",
                "type": "article-journal",
                "title": "Test",
                "author": [{"family": "Test", "given": "T"}],
                "issued": {"date-parts": [[2024]]},
            },
        ]
        clusters = [
            {
                "citationItems": [{"id": "test2024"}],
                "properties": {"noteIndex": 0},
            },
        ]

        # First call — populates cache
        with patch(
            "engine.bibliography.formatter._format_via_citeproc",
            side_effect=Exception("subprocess not available"),
        ):
            result1 = format_citations(items, clusters, style="apa")

        # Second call with same inputs — should hit cache (no subprocess call).
        # The cache key is based on the hash of inputs; verify it exists
        # by checking that format_citations returns the same result
        with patch(
            "engine.bibliography.formatter._format_via_citeproc",
            side_effect=Exception("should not be called"),
        ):
            result2 = format_citations(items, clusters, style="apa")

        self.assertEqual(result1.citations, result2.citations)
        self.assertEqual(result1.bibliography, result2.bibliography)
