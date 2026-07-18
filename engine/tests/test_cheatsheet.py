"""
Tests for the data-driven Markdown reference (``engine.markdown.cheatsheet``)
and its admin surfaces: the browsable fallback HTML, the palette JSON payload,
and the change-form launcher.
"""

import html
import json
import re

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from engine.markdown.cheatsheet import (
    CHEATSHEET_SECTIONS,
    palette_payload,
    reference_html,
)
from engine.models import Post

User = get_user_model()


class CheatsheetDataTests(TestCase):
    def test_every_item_has_the_three_fields(self):
        for section in CHEATSHEET_SECTIONS:
            self.assertIn("title", section)
            self.assertIn("items", section)
            for item in section["items"]:
                self.assertEqual(set(item), {"syntax", "insert", "desc"})
                self.assertIsInstance(item["syntax"], str)
                self.assertIsInstance(item["desc"], str)
                self.assertTrue(
                    item["insert"] is None or isinstance(item["insert"], str)
                )

    def test_insert_snippets_use_wellformed_placeholders(self):
        # Every ${...} must be a CM6 snippet placeholder (${N} or ${N:default}).
        # Literal class braces like {.smallcaps} are fine — they aren't ${...}.
        any_re = re.compile(r"\$\{[^}]*\}")
        valid_re = re.compile(r"\$\{\d+(:[^}]*)?\}")
        for section in CHEATSHEET_SECTIONS:
            for item in section["items"]:
                tmpl = item["insert"]
                if not tmpl:
                    continue
                for m in any_re.finditer(tmpl):
                    self.assertRegex(
                        m.group(),
                        valid_re,
                        f"malformed placeholder in {item['syntax']!r}",
                    )


class ReferenceHtmlTests(TestCase):
    def test_renders_all_section_titles(self):
        markup = reference_html()
        for section in CHEATSHEET_SECTIONS:
            self.assertIn(html.escape(section["title"]), markup)

    def test_descriptions_are_escaped_not_injected(self):
        # The "Disallowed" row mentions <script>; it must be escaped, never a
        # live tag in the readonly field.
        markup = reference_html()
        self.assertIn("&lt;script&gt;", markup)
        self.assertNotIn("<script>", markup)

    def test_backtick_spans_become_code(self):
        # e.g. "expands every occurrence into `<abbr>`" -> <code>&lt;abbr&gt;</code>
        markup = reference_html()
        self.assertIn("<code>&lt;abbr&gt;</code>", markup)


class PalettePayloadTests(TestCase):
    def test_payload_is_valid_json_matching_the_data(self):
        payload = json.loads(palette_payload())
        self.assertEqual(len(payload), len(CHEATSHEET_SECTIONS))
        self.assertEqual(payload[0]["title"], CHEATSHEET_SECTIONS[0]["title"])
        self.assertIn("insert", payload[0]["items"][0])


class ChangeFormLauncherTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(
            username="admin", password="pw", email="a@example.com"
        )
        cls.post = Post.objects.create(
            title="t", slug="t", author=cls.admin, content_markdown="hi"
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def test_change_form_has_launcher_and_cheatsheet_data(self):
        url = reverse("admin:engine_post_change", args=[self.post.pk])
        body = self.client.get(url).content.decode()
        # Launcher button the palette JS wires up.
        self.assertIn("data-md-helper-open", body)
        # The palette data is stamped onto the editor textarea.
        self.assertIn("data-cm-cheatsheet", body)
