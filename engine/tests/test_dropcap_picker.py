"""
Dropcaps, phase two: the admin picker widget on the site-settings, post and
page forms, the "Dropcap styles" gallery page, and the editor completions.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from engine.admin.post import EDITOR_FENCE_SNIPPETS, EDITOR_INLINE_CLASSES
from engine.admin.widgets import DropcapPickerSelect
from engine.markdown import dropcaps
from engine.models import Page, Post, SiteSettings

User = get_user_model()


class DropcapPickerWidgetTests(TestCase):
    def test_renders_select_specials_and_a_tile_per_style(self):
        widget = DropcapPickerSelect(
            choices=dropcaps.document_dropcap_choices(), gallery_url="/g/"
        )
        html = widget.render("dropcap_style", "", attrs={"id": "id_dropcap_style"})
        self.assertIn('<select name="dropcap_style"', html)
        self.assertIn("mk-dropcap-picker", html)
        self.assertIn('class="mk-dropcap-option mk-dropcap-special" data-key=""', html)
        self.assertIn('data-key="none"', html)
        for style in dropcaps.STYLES:
            self.assertIn(f'data-key="{style.key}"', html)
            self.assertIn(f"font-family: '{style.family}'", html)
        self.assertIn('href="/g/"', html)
        self.assertEqual(html.count("mk-dropcap-group-label"), len(dropcaps.GROUPS))

    def test_site_choices_have_no_none_tile(self):
        widget = DropcapPickerSelect(choices=dropcaps.site_dropcap_choices())
        html = widget.render("default_dropcap_style", "")
        self.assertNotIn('data-key="none"', html)
        self.assertNotIn("mk-dropcap-gallery-link", html)

    def test_media_loads_faces_and_widget_assets(self):
        media = str(DropcapPickerSelect().media)
        self.assertIn("css/dist/dropcaps.css", media)
        self.assertIn("css/admin-widgets.css", media)
        self.assertIn("js/admin-widgets.js", media)


class DropcapAdminPagesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("dc-admin", "a@example.com", "pw")
        cls.settings = SiteSettings.load()
        cls.post = Post.objects.create(
            title="Picker post",
            slug="picker-post",
            author=cls.admin,
            content_markdown="x",
        )
        cls.page = Page.objects.create(slug="picker-page", title="Picker page")

    def setUp(self):
        self.client.force_login(self.admin)

    def test_site_settings_form_uses_picker_with_gallery_link(self):
        resp = self.client.get(
            reverse("admin:engine_sitesettings_change", args=[self.settings.pk])
        )
        self.assertContains(resp, '<select name="default_dropcap_style"')
        self.assertContains(resp, "mk-dropcap-picker")
        self.assertContains(resp, reverse("admin:engine_sitesettings_dropcap_gallery"))
        self.assertContains(resp, "css/dist/dropcaps.css")

    def test_post_and_page_forms_use_picker(self):
        for url in (
            reverse("admin:engine_post_change", args=[self.post.pk]),
            reverse("admin:engine_page_change", args=[self.page.pk]),
        ):
            resp = self.client.get(url)
            self.assertContains(resp, '<select name="dropcap_style"', msg_prefix=url)
            self.assertContains(resp, "mk-dropcap-picker", msg_prefix=url)
            self.assertContains(resp, 'data-key="none"', msg_prefix=url)

    def test_gallery_shows_every_style_in_body_text(self):
        resp = self.client.get(reverse("admin:engine_sitesettings_dropcap_gallery"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        for style in dropcaps.STYLES:
            self.assertIn(f'class="markdownBody {style.css_class}"', body)
            self.assertIn(f"::: {{.{style.css_class}}}", body)
        self.assertIn('class="dropcap-letter"', body)
        self.assertIn("--dropcap-lines: 2", body)
        self.assertIn("css/dist/base.css", body)

    def test_gallery_requires_staff(self):
        self.client.logout()
        resp = self.client.get(reverse("admin:engine_sitesettings_dropcap_gallery"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp["Location"])


class EditorCompletionTests(TestCase):
    def test_fence_snippets_and_inline_classes_include_dropcaps(self):
        fence = {s["className"] for s in EDITOR_FENCE_SNIPPETS}
        self.assertTrue({"dropcap-STYLE", "dropcap", "dropcap-not"} <= fence)
        names = {c["name"] for c in EDITOR_INLINE_CLASSES}
        self.assertIn("dropcap", names)
        self.assertIn("dropcap-not", names)
        for style in dropcaps.STYLES:
            self.assertIn(style.css_class, names)
