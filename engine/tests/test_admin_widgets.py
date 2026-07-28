"""
Tests for the admin picker widgets: color/glyph pickers on the tag admins,
the language datalist on the post form, the curated citation-style dropdown
on site settings, and a guard that every offered citation style actually
resolves to a .csl file (the chicago-notes-bibliography regression).
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from engine.admin.widgets import ColorInput, DatalistTextInput, GlyphPickerInput
from engine.models import AssetTag, SiteSettings, Tag

User = get_user_model()


class AdminWidgetRenderTests(TestCase):
    """Widget-level rendering, independent of any admin page."""

    def test_color_input_renders_native_picker_with_presets(self):
        html = ColorInput().render("color", "#8a6d3b", attrs={"id": "id_color"})
        self.assertIn('type="color"', html)
        self.assertIn('list="id_color_presets"', html)
        self.assertIn('<datalist id="id_color_presets">', html)

    def test_datalist_input_accepts_bare_values_and_pairs(self):
        html = DatalistTextInput(["en", ("de", "German")]).render(
            "language", "en", attrs={"id": "id_language"}
        )
        self.assertIn('list="id_language_options"', html)
        self.assertIn('<option value="en"', html)
        self.assertIn('label="German"', html)

    def test_glyph_picker_renders_panel_and_options(self):
        html = GlyphPickerInput().render("icon", "", attrs={"id": "id_icon"})
        self.assertIn("mk-glyph-picker", html)
        self.assertIn("mk-glyph-panel", html)
        self.assertIn('data-glyph="¶"', html)
        self.assertIn("mk-glyph-clear", html)


class AdminWidgetPageTests(TestCase):
    """The widgets actually appear on the relevant admin pages."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username="admin", password="pw", email="a@example.com"
        )
        cls.tag = Tag.objects.create(name="Django")
        cls.asset_tag = AssetTag.objects.create(name="photos", slug="photos")
        # Singleton — seeded by migration, so fetch rather than create.
        cls.site_settings = (
            SiteSettings.objects.first() or SiteSettings.objects.create()
        )

    def setUp(self):
        self.client.force_login(self.superuser)

    def test_tag_form_has_color_and_glyph_pickers(self):
        resp = self.client.get(reverse("admin:engine_tag_change", args=[self.tag.pk]))
        self.assertContains(resp, 'type="color"')
        self.assertContains(resp, "mk-glyph-picker")
        self.assertContains(resp, "js/admin-widgets.js")
        self.assertContains(resp, "css/admin-widgets.css")

    def test_asset_tag_form_has_color_picker(self):
        resp = self.client.get(
            reverse("admin:engine_assettag_change", args=[self.asset_tag.pk])
        )
        self.assertContains(resp, 'type="color"')

    def test_post_add_form_has_language_datalist(self):
        resp = self.client.get(reverse("admin:engine_post_add"))
        self.assertContains(resp, 'list="id_language_options"')
        self.assertContains(resp, '<datalist id="id_language_options">')

    def test_site_settings_has_citation_style_dropdown(self):
        resp = self.client.get(
            reverse("admin:engine_sitesettings_change", args=[self.site_settings.pk])
        )
        self.assertContains(resp, '<select name="default_citation_style"')
        self.assertContains(resp, "chicago-notes-bibliography")

    def test_tag_change_form_saves_through_pickers(self):
        resp = self.client.post(
            reverse("admin:engine_tag_change", args=[self.tag.pk]),
            {
                "name": "Django",
                "slug": "django",
                "namespace": "",
                "parent": "",
                "description": "",
                "color": "#8a6d3b",
                "icon": "¶",
                "is_active": "on",
                "rank": "0",
                "aliases-TOTAL_FORMS": "0",
                "aliases-INITIAL_FORMS": "0",
                "aliases-MIN_NUM_FORMS": "0",
                "aliases-MAX_NUM_FORMS": "1000",
            },
        )
        self.assertEqual(resp.status_code, 302, getattr(resp, "context", None))
        self.tag.refresh_from_db()
        self.assertEqual(self.tag.color, "#8a6d3b")
        self.assertEqual(self.tag.icon, "¶")


class CitationStyleChoicesTests(TestCase):
    """Every citation style offered in the admin must resolve to a real
    .csl file (directly or via a formatter alias) — a typo'd value silently
    falls back to APA at render time."""

    def test_all_offered_styles_exist_on_disk(self):
        from engine.admin.post import CITATION_STYLE_CHOICES
        from engine.bibliography.formatter import _STYLE_ALIASES, _STYLES_DIR

        for value, label in CITATION_STYLE_CHOICES:
            if not value:
                continue
            resolved = _STYLE_ALIASES.get(value, value)
            self.assertTrue(
                (_STYLES_DIR / f"{resolved}.csl").exists(),
                f"Admin offers citation style '{value}' ({label}) but no "
                f"matching .csl file exists in {_STYLES_DIR}",
            )
