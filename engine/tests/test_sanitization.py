"""
Tests for HTML sanitization in the markdown pipeline.
"""

from django.test import TestCase

from engine.markdown.postprocessors.sanitizer import sanitize_html


class SanitizationTests(TestCase):
    """Test that the HTML sanitizer properly filters dangerous content."""

    def test_script_tags_removed(self):
        html = '<p>Hello</p><script>alert("xss")</script>'
        result = sanitize_html(html, {})
        self.assertNotIn("<script", result)
        self.assertNotIn("alert", result)
        self.assertIn("<p>Hello</p>", result)

    def test_event_handlers_removed(self):
        html = '<p onclick="alert(1)">Click me</p>'
        result = sanitize_html(html, {})
        self.assertNotIn("onclick", result)
        self.assertIn("<p>", result)

    def test_safe_html_preserved(self):
        html = '<p>Normal <strong>text</strong> with <a href="https://example.com">link</a></p>'
        result = sanitize_html(html, {})
        self.assertIn("<strong>text</strong>", result)
        self.assertIn('href="https://example.com"', result)

    def test_img_tags_preserved(self):
        html = '<img src="https://example.com/img.png" alt="test" />'
        result = sanitize_html(html, {})
        self.assertIn("src=", result)
        self.assertIn("alt=", result)

    def test_javascript_urls_removed(self):
        html = '<a href="javascript:alert(1)">Click</a>'
        result = sanitize_html(html, {})
        self.assertNotIn("javascript:", result)

    def test_data_attributes_preserved(self):
        html = '<div data-value="test">Content</div>'
        result = sanitize_html(html, {})
        self.assertIn("data-value", result)

    def test_noopener_added_to_links(self):
        html = '<a href="https://external.com">Link</a>'
        result = sanitize_html(html, {})
        self.assertIn("noopener", result)
