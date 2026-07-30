"""
Tests for the unified content-lint engine (``engine.markdown.lint``).

The engine is the single source of truth behind three admin surfaces: the
CodeMirror lint gutter (needs char offsets), the preview modal's warning list,
and the save-time messages (both need per-kind summaries). These tests exercise
the detection rules, the offset math, and the summary/diagnostic adapters.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from engine.markdown.lint import (
    group_labels,
    lint_markdown,
    summarize,
    to_diagnostics,
)
from engine.models import Asset, Post, PostAsset, Source

User = get_user_model()


def _spans(findings, kind):
    return [(f.start, f.end) for f in findings if f.kind == kind]


class CleanContentTests(TestCase):
    def test_empty_content_has_no_findings(self):
        self.assertEqual(lint_markdown(""), [])
        self.assertEqual(lint_markdown(None), [])

    def test_plain_prose_has_no_findings(self):
        self.assertEqual(lint_markdown("# Title\n\nJust some prose, no refs."), [])


class AssetRefTests(TestCase):
    def test_unresolved_asset_ref_flagged_with_offset(self):
        content = "before ![alt](@asset:missing) after"
        findings = [f for f in lint_markdown(content) if f.kind == "asset"]
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual(f.label, "@asset:missing")
        # The span must cover exactly the @…key token, sigil included.
        self.assertEqual(content[f.start : f.end], "@asset:missing")

    def test_unresolved_alias_ref_flagged(self):
        content = "![alt](@diagram1)"
        findings = [f for f in lint_markdown(content) if f.kind == "asset"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].label, "@diagram1")
        self.assertEqual(content[findings[0].start : findings[0].end], "@diagram1")

    def test_global_ref_resolves_against_ready_asset(self):
        Asset.objects.create(
            title="Chart", asset_type="image", key="chart", status="ready"
        )
        findings = lint_markdown("![c](@asset:chart)")
        self.assertEqual(_spans(findings, "asset"), [])

    def test_deleted_asset_still_flagged(self):
        Asset.objects.create(
            title="Old",
            asset_type="image",
            key="old",
            status="ready",
            is_deleted=True,
        )
        findings = [f for f in lint_markdown("![o](@asset:old)") if f.kind == "asset"]
        self.assertEqual(len(findings), 1)

    def test_alias_resolves_against_attached_post_asset(self):
        user = User.objects.create_user(username="a", password="p")
        post = Post.objects.create(
            title="p", slug="p", author=user, content_markdown="x"
        )
        asset = Asset.objects.create(
            title="Diagram", asset_type="image", key="diagram-real", status="ready"
        )
        pa = PostAsset.objects.create(post=post, asset=asset, alias="diagram1")
        content = "![d](@diagram1)"
        findings = lint_markdown(content, post_assets=[pa])
        self.assertEqual(_spans(findings, "asset"), [])
        # Without the attachment, the same alias is unresolved.
        self.assertEqual(len(lint_markdown(content)), 1)


class CitationTests(TestCase):
    def test_unknown_narrative_citation_flagged(self):
        content = "As @smith2024 argues, this holds."
        findings = [f for f in lint_markdown(content) if f.kind == "citation"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].label, "@smith2024")
        self.assertEqual(content[findings[0].start : findings[0].end], "@smith2024")

    def test_unknown_bracketed_citation_flagged(self):
        content = "See [@jones2020] for details."
        findings = [f for f in lint_markdown(content) if f.kind == "citation"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(content[findings[0].start : findings[0].end], "@jones2020")

    def test_known_source_not_flagged(self):
        Source.objects.create(
            citation_key="smith2024", title="Paper", source_type="article"
        )
        findings = lint_markdown("As @smith2024 shows.")
        self.assertEqual(_spans(findings, "citation"), [])

    def test_citation_in_inline_code_skipped(self):
        findings = lint_markdown("Use `@handle` in code, not a cite.")
        self.assertEqual(_spans(findings, "citation"), [])

    def test_citation_in_fenced_code_skipped(self):
        content = "```\n@smith2024\n```\n"
        self.assertEqual(_spans(lint_markdown(content), "citation"), [])

    def test_asset_ref_target_not_treated_as_citation(self):
        # @asset:x lives in a link target; it is an asset check, never a cite.
        findings = lint_markdown("![x](@asset:x)")
        self.assertEqual(_spans(findings, "citation"), [])

    def test_multi_key_bracket_flags_each_unknown(self):
        Source.objects.create(citation_key="known", title="K", source_type="article")
        content = "[@known; @unknown]"
        labels = group_labels(lint_markdown(content)).get("citation", [])
        self.assertEqual(labels, ["@unknown"])


class InternalLinkTests(TestCase):
    def test_broken_internal_link_flagged(self):
        content = "See [it](/posts/no-such-post/)."
        findings = [f for f in lint_markdown(content) if f.kind == "link"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].label, "/posts/no-such-post/")
        self.assertTrue(content[findings[0].start :].startswith("/posts/no-such-post"))

    def test_existing_post_link_not_flagged(self):
        user = User.objects.create_user(username="b", password="p")
        Post.objects.create(
            title="Real", slug="real-post", author=user, content_markdown="x"
        )
        findings = lint_markdown("[go](/posts/real-post/)")
        self.assertEqual(_spans(findings, "link"), [])


class FenceTests(TestCase):
    def test_odd_fences_flagged(self):
        content = "::: tip\nhello there\n"
        findings = [f for f in lint_markdown(content) if f.kind == "fence"]
        self.assertEqual(len(findings), 1)
        self.assertTrue(content[findings[0].start : findings[0].end].startswith(":::"))

    def test_balanced_fences_ok(self):
        content = "::: tip\nhello\n:::\n"
        self.assertEqual(_spans(lint_markdown(content), "fence"), [])


class AdapterTests(TestCase):
    def test_to_diagnostics_shape(self):
        diags = to_diagnostics(lint_markdown("As @xyz argues."))
        self.assertEqual(len(diags), 1)
        self.assertEqual(set(diags[0]), {"from", "to", "severity", "message"})
        self.assertEqual(diags[0]["severity"], "warning")

    def test_group_labels_dedupes_in_order(self):
        content = "As @a and again @a, plus @b."
        labels = group_labels(lint_markdown(content))["citation"]
        self.assertEqual(labels, ["@a", "@b"])

    def test_summarize_produces_one_line_per_kind(self):
        content = "![x](@asset:nope)\n\nAs @cite says [oops](/posts/ghost/).\n::: tip\n"
        lines = summarize(lint_markdown(content))
        self.assertEqual(len(lines), 4)  # asset, citation, link, fence
        joined = "\n".join(lines)
        self.assertIn("@asset:nope", joined)
        self.assertIn("@cite", joined)
        self.assertIn("/posts/ghost/", joined)
        self.assertIn(":::", joined)

    def test_summarize_empty_when_clean(self):
        self.assertEqual(summarize(lint_markdown("clean prose")), [])


class AltTextLintTests(TestCase):
    """The alt rule: image refs with no markdown alt AND no asset alt."""

    @classmethod
    def setUpTestData(cls):
        cls.no_alt = Asset.objects.create(
            title="Bare", asset_type="image", key="img-bare", status="ready"
        )
        cls.with_alt = Asset.objects.create(
            title="Described",
            asset_type="image",
            key="img-described",
            status="ready",
            alt_text="A described image",
        )
        cls.doc = Asset.objects.create(
            title="Paper", asset_type="document", key="doc-paper", status="ready"
        )

    def test_image_without_any_alt_flagged(self):
        content = "text ![](@asset:img-bare) more"
        findings = [f for f in lint_markdown(content) if f.kind == "alt"]
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual(f.label, "@asset:img-bare")
        # Span covers the image marker and empty brackets.
        self.assertEqual(content[f.start : f.end], "![]")

    def test_markdown_alt_satisfies_rule(self):
        findings = lint_markdown("![harbor at dusk](@asset:img-bare)")
        self.assertEqual([f for f in findings if f.kind == "alt"], [])

    def test_asset_level_alt_satisfies_rule(self):
        findings = lint_markdown("![](@asset:img-described)")
        self.assertEqual([f for f in findings if f.kind == "alt"], [])

    def test_non_image_asset_not_flagged(self):
        findings = lint_markdown("![](@asset:doc-paper)")
        self.assertEqual([f for f in findings if f.kind == "alt"], [])

    def test_alias_custom_alt_override_satisfies_rule(self):
        author = User.objects.create_user(username="lint-alt", password="x")
        post = Post.objects.create(title="P", content_markdown="x", author=author)
        pa = PostAsset.objects.create(
            post=post, asset=self.no_alt, alias="hero", custom_alt_text="Override"
        )
        findings = lint_markdown("![](@hero)", post_assets=[pa])
        self.assertEqual([f for f in findings if f.kind == "alt"], [])

    def test_alias_without_alt_flagged(self):
        author = User.objects.create_user(username="lint-alt2", password="x")
        post = Post.objects.create(title="P2", content_markdown="x", author=author)
        pa = PostAsset.objects.create(post=post, asset=self.no_alt, alias="hero2")
        findings = [
            f for f in lint_markdown("![](@hero2)", post_assets=[pa]) if f.kind == "alt"
        ]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].label, "@hero2")

    def test_summarize_mentions_alt(self):
        lines = summarize(lint_markdown("![](@asset:img-bare)"))
        self.assertTrue(any("alt text" in line for line in lines))
