"""
Dropcaps: the style registry, the postprocessor that hoists opening letters,
the resolution of site/document settings, and the generated stylesheet.
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings

from engine.management.commands.generate_dropcaps_css import (
    render_css,
    target_path,
)
from engine.markdown import dropcaps
from engine.markdown.postprocessors.dropcap_enhancer import enhance_dropcaps
from engine.markdown.renderer import render_markdown
from engine.models import Page, Post, SiteSettings


def _run(html: str, context: dict | None = None) -> str:
    return enhance_dropcaps(html, context if context is not None else {})


class RegistryTests(TestCase):
    def test_keys_are_unique_and_slug_like(self):
        keys = [s.key for s in dropcaps.STYLES]
        self.assertEqual(len(keys), len(set(keys)))
        for key in keys:
            self.assertRegex(key, r"^[a-z0-9]+(-[a-z0-9]+)*$")
            self.assertNotIn(key, {dropcaps.NONE, ""})

    def test_every_style_has_a_known_group(self):
        groups = {g for g, _ in dropcaps.GROUPS}
        for style in dropcaps.STYLES:
            self.assertIn(style.group, groups, style.key)

    def test_choices_offer_inherit_and_none_for_documents_only(self):
        doc = dropcaps.document_dropcap_choices()
        site = dropcaps.site_dropcap_choices()
        self.assertEqual(doc[0][0], dropcaps.INHERIT)
        self.assertEqual(doc[1][0], dropcaps.NONE)
        self.assertEqual(site[0][0], dropcaps.INHERIT)
        self.assertNotIn(dropcaps.NONE, [c[0] for c in site])
        # grouped remainder covers every style exactly once
        listed = [k for _, group in doc[2:] for k, _ in group]
        self.assertEqual(sorted(listed), sorted(s.key for s in dropcaps.STYLES))

    def test_parse_class_only_accepts_known_keys(self):
        first = dropcaps.STYLES[0].key
        self.assertEqual(dropcaps.parse_class(f"dropcap-{first}"), first)
        self.assertIsNone(dropcaps.parse_class("dropcap-nope"))
        self.assertIsNone(dropcaps.parse_class("dropcap"))
        self.assertIsNone(dropcaps.parse_class("dropcap-not"))

    def test_resolve_style_nearest_wins_and_none_switches_off(self):
        a, b = dropcaps.STYLES[0].key, dropcaps.STYLES[1].key
        self.assertEqual(dropcaps.resolve_style(dropcaps.INHERIT, ""), "")
        self.assertEqual(dropcaps.resolve_style(dropcaps.INHERIT, a), a)
        self.assertEqual(dropcaps.resolve_style(b, a), b)
        self.assertEqual(dropcaps.resolve_style(dropcaps.NONE, a), "")
        self.assertEqual(dropcaps.resolve_style("bogus", a), a)

    def test_clamp_lines(self):
        self.assertEqual(dropcaps.clamp_lines("2"), 2)
        self.assertEqual(dropcaps.clamp_lines(" 4 "), 4)
        self.assertIsNone(dropcaps.clamp_lines("1"))
        self.assertIsNone(dropcaps.clamp_lines("7"))
        self.assertIsNone(dropcaps.clamp_lines("two"))
        self.assertIsNone(dropcaps.clamp_lines(None))


class EnhancerTests(TestCase):
    def test_opening_paragraph_gets_letter_span_and_class(self):
        out = _run("<p>Grand opening. Second sentence.</p><p>Next.</p>")
        self.assertIn(
            '<p class="dropcap"><span class="dropcap-letter">G</span>rand opening.',
            out,
        )
        self.assertEqual(out.count("dropcap-letter"), 1)

    def test_opening_quote_rides_inside_the_span(self):
        out = _run("<p>“Quoted” start.</p>")
        self.assertIn(
            '<span class="dropcap-letter"><span class="dropcap-punct">“</span>Q</span>uoted”',
            out,
        )

    def test_letter_inside_inline_element_is_wrapped_in_place(self):
        out = _run("<p><em>Emphatic</em> start.</p>")
        self.assertIn(
            '<p class="dropcap"><em><span class="dropcap-letter">E</span>mphatic</em>',
            out,
        )

    def test_non_letter_openings_are_left_alone(self):
        for html in (
            "<p>2024 was a year.</p>",
            '<p><img src="x.png" alt="x"> Caption-ish.</p>',
            "<p><code>x = 1</code> is code.</p>",
            "<p>— dash first.</p>",
        ):
            out = _run(html)
            self.assertNotIn("dropcap-letter", out, html)
            self.assertNotIn('class="dropcap"', out, html)

    def test_skips_abstract_footnotes_blockquotes_and_epigraphs(self):
        html = (
            '<blockquote class="page-abstract"><p>Abstract text.</p></blockquote>'
            '<div class="epigraph"><blockquote><p>Quote.</p></blockquote></div>'
            "<blockquote><p>Quoted para.</p></blockquote>"
            "<ul><li><p>List para.</p></li></ul>"
            "<p>Real opening.</p>"
            '<section id="footnotes" class="footnotes"><p>Note.</p></section>'
        )
        out = _run(html)
        self.assertEqual(out.count("dropcap-letter"), 1)
        self.assertIn(
            '<p class="dropcap"><span class="dropcap-letter">R</span>eal opening.', out
        )

    def test_abstract_and_fragment_contexts_are_untouched(self):
        html = "<p>Abstract.</p>"
        self.assertEqual(_run(html, {"is_abstract": True}), html)
        self.assertEqual(_run(html, {"fragment": True}), html)

    def test_fragment_render_sets_and_clears_flag(self):
        from engine.markdown.renderer import render_markdown_fragment

        context = {}
        html = render_markdown_fragment("Caption text.", context)
        self.assertNotIn("dropcap", html)
        self.assertNotIn("fragment", context)

    def test_dropcap_not_block_suppresses_opening_dropcap(self):
        out = _run('<div class="dropcap-not"><p>First.</p></div><p>Second.</p>')
        self.assertNotIn("dropcap-letter", out)
        self.assertIn('<div class="dropcap-not">', out)

    def test_explicit_style_block_moves_classes_onto_paragraph(self):
        key = dropcaps.STYLES[0].key
        out = _run(f'<div class="dropcap-{key}"><p>Styled.</p></div>')
        self.assertIn(
            f'<p class="dropcap dropcap-{key}"><span class="dropcap-letter">S</span>tyled.</p>',
            out,
        )
        self.assertNotIn("<div", out)

    def test_bare_dropcap_block_and_lines_attribute(self):
        out = _run('<div class="dropcap" data-lines="2"><p>Two lines.</p></div>')
        self.assertIn('<p class="dropcap" style="--dropcap-lines: 2">', out)
        self.assertNotIn("data-lines", out)
        out = _run('<div class="dropcap" data-lines="9"><p>Bad lines.</p></div>')
        self.assertNotIn("--dropcap-lines", out)

    def test_unknown_style_class_is_dropped_but_block_kept(self):
        out = _run('<div class="dropcap-nope columns"><p>Plain.</p></div>')
        self.assertNotIn("dropcap-nope", out)
        self.assertIn('<div class="columns">', out)
        # still the document's opening paragraph, so it gets the inert span
        self.assertIn('<p class="dropcap"><span class="dropcap-letter">P</span>', out)
        self.assertNotIn("dropcap dropcap-", out)

    def test_block_with_other_classes_is_not_unwrapped(self):
        key = dropcaps.STYLES[0].key
        out = _run(f'<div class="dropcap-{key} text-center"><p>Kept.</p></div>')
        self.assertIn('<div class="text-center">', out)
        self.assertIn(f'<p class="dropcap dropcap-{key}">', out)

    def test_explicit_block_on_opening_paragraph_is_not_doubled(self):
        key = dropcaps.STYLES[0].key
        out = _run(f'<div class="dropcap-{key}"><p>Once.</p></div><p>Later.</p>')
        self.assertEqual(out.count("dropcap-letter"), 1)
        self.assertNotIn('<p class="dropcap"><span', out)

    def test_idempotent(self):
        once = _run("<p>Again and again.</p>")
        self.assertEqual(_run(once), once)

    def test_full_pipeline_from_markdown(self):
        key = dropcaps.STYLES[0].key
        md = (
            "Opening paragraph here.\n\n"
            f"::: {{.dropcap-{key} lines=2}}\n"
            "Marked paragraph.\n"
            ":::\n"
        )
        html = render_markdown(md, context={})
        self.assertIn('<span class="dropcap-letter">O</span>pening', html)
        self.assertIn(f"dropcap dropcap-{key}", html)
        self.assertIn("--dropcap-lines: 2", html)


class ResolutionTests(TestCase):
    def setUp(self):
        # SiteSettings.load() caches the singleton; the test transaction
        # rollback does not clear the cache, so start each test clean.
        cache.delete("site_settings")
        self.site = SiteSettings.load()

        self.a = dropcaps.STYLES[0].key
        self.b = dropcaps.STYLES[1].key

    def tearDown(self):
        cache.delete("site_settings")

    def _set_site(self, value):
        self.site.default_dropcap_style = value
        self.site.save()

    def test_off_by_default(self):
        post = Post(title="t", content_markdown="x")
        page = Page(slug="p", title="p")
        self.assertEqual(post.effective_dropcap_style, "")
        self.assertEqual(page.effective_dropcap_style, "")

    def test_site_default_applies_and_document_overrides(self):
        self._set_site(self.a)
        post = Post(title="t", content_markdown="x")
        self.assertEqual(post.effective_dropcap_style, self.a)
        post.dropcap_style = self.b
        self.assertEqual(post.effective_dropcap_style, self.b)
        post.dropcap_style = dropcaps.NONE
        self.assertEqual(post.effective_dropcap_style, "")

    def test_field_choices_validate(self):
        post = Post(title="t", content_markdown="x", dropcap_style="bogus")
        with self.assertRaises(Exception):
            post.full_clean(exclude=None, validate_unique=False)

    def test_post_detail_wrapper_carries_style_class(self):
        self._set_site(self.a)
        author = get_user_model().objects.create_user("author", password="x")
        post = Post.objects.create(
            title="Dropcap post",
            slug="dropcap-post",
            author=author,
            content_markdown="Opening words of the post.",
            status=Post.Status.PUBLISHED,
            visibility=Post.Visibility.PUBLIC,
        )
        response = self.client.get(post.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'class="markdownBody dropcap-{self.a}"')
        self.assertContains(response, 'class="dropcap-letter">O</span>pening')

        post.dropcap_style = dropcaps.NONE
        post.save()
        response = self.client.get(post.get_absolute_url())
        self.assertContains(response, 'class="markdownBody">')


class StylesheetTests(TestCase):
    def test_committed_stylesheet_matches_registry(self):
        self.assertEqual(target_path().read_text(), render_css())
        call_command("generate_dropcaps_css", "--check")

    def test_every_style_has_face_rules_and_selectors(self):
        css = render_css()
        for style in dropcaps.STYLES:
            self.assertIn(f"font-family: '{style.family}';", css)
            self.assertIn(f".markdownBody.{style.css_class}", css)
            self.assertIn(f".markdownBody p.{style.css_class}", css)
            self.assertIn(style.font_path, css)

    @override_settings()
    def test_every_font_file_is_shipped_with_its_licence(self):
        from pathlib import Path

        from django.conf import settings

        for style in dropcaps.STYLES:
            font = Path(settings.BASE_DIR) / style.font_path.lstrip("/")
            self.assertTrue(font.exists(), font)
            self.assertTrue((font.parent / "OFL.txt").exists(), font.parent)
