"""
``manage.py dropcap_fonts``: the registry text surgery and file-picking
helpers (offline), and add/remove end to end against a temporary registry
copy and font directory with the network and subsetting stubbed.
"""

import ast
import shutil
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from engine.management.commands import dropcap_fonts as cmd
from engine.markdown import dropcaps
from engine.models import Post, SiteSettings

REGISTRY = Path(dropcaps.__file__)


class HelperTests(TestCase):
    def test_slug_and_key_derivation(self):
        self.assertEqual(cmd.slugify_family("IM Fell English"), "imfellenglish")
        self.assertEqual(cmd.key_for_family("IM Fell English"), "im-fell-english")
        self.assertEqual(
            cmd.key_for_family("Goudy Bookletter 1911"), "goudy-bookletter-1911"
        )
        with self.assertRaises(CommandError):
            cmd.key_for_family("!!!")

    def test_choose_font_file_prefers_variable_then_regular(self):
        names = ["OFL.txt", "Foo-Bold.ttf", "Foo-Regular.ttf", "Foo-Italic.ttf"]
        self.assertEqual(cmd.choose_font_file(names), "Foo-Regular.ttf")
        self.assertEqual(
            cmd.choose_font_file(["Foo[wght].ttf", "Foo-Italic[wght].ttf"]),
            "Foo[wght].ttf",
        )
        self.assertEqual(cmd.choose_font_file(["OFL.txt", "Foo.ttf"]), "Foo.ttf")
        self.assertEqual(cmd.choose_font_file(names, "Foo-Bold.ttf"), "Foo-Bold.ttf")
        with self.assertRaises(CommandError):
            cmd.choose_font_file(names, "Nope.ttf")
        with self.assertRaises(CommandError):
            cmd.choose_font_file(["OFL.txt"])

    def test_render_entry_matches_registry_layout_and_parses(self):
        entry = cmd.render_entry_source(
            key="ultra",
            label="Ultra",
            family="Ultra",
            group="display",
            weight=700,
            variable=True,
            scale=0.95,
            gap=0.2,
            license="Apache-2.0",
            description="Fat slab.",
        )
        self.assertTrue(entry.startswith('    _s(\n        "ultra",\n'))
        self.assertIn("        variable=True,\n", entry)
        self.assertIn('        license="Apache-2.0",\n', entry)
        self.assertTrue(entry.endswith("    ),\n"))
        ast.parse(entry.strip().rstrip(","))  # valid Python call
        minimal = cmd.render_entry_source(
            key="k", label="L", family="F", group="script"
        )
        quoted = cmd.render_entry_source(
            key="k",
            label="L",
            family="F",
            group="script",
            description='After Franck\'s "Kunstbuch" of 1601.',
        )
        ast.parse(quoted.strip().rstrip(","))
        self.assertIn("Franck's", quoted)
        self.assertIn('\\"Kunstbuch\\"', quoted)
        self.assertNotIn("weight=", minimal)
        self.assertNotIn("scale=", minimal)
        self.assertNotIn("license=", minimal)

    def test_insert_then_remove_round_trips_the_registry(self):
        text = REGISTRY.read_text()
        entry = cmd.render_entry_source(
            key="zz-test", label="ZZ", family="ZZ", group="script", description="t"
        )
        inserted = cmd.insert_entry_source(text, entry, "script")
        # lands inside the Script section, before the Display marker
        self.assertLess(inserted.index('"zz-test"'), inserted.index("# Display"))
        self.assertGreater(inserted.index('"zz-test"'), inserted.index("# Script"))
        ast.parse(inserted)
        # last group: goes right before the tuple closes
        last = cmd.insert_entry_source(text, entry, "display")
        self.assertTrue(last.rstrip().endswith("STYLE_MAP") or ")" in last)
        ast.parse(last)
        self.assertEqual(cmd.remove_entry_source(inserted, "zz-test"), text)
        with self.assertRaises(CommandError):
            cmd.remove_entry_source(text, "zz-test")
        with self.assertRaises(CommandError):
            cmd.insert_entry_source(text, entry, "nope")

    def test_licence_ids(self):
        self.assertEqual(cmd.licence_id_for("OFL.txt"), "OFL-1.1")
        self.assertEqual(cmd.licence_id_for("UFL.txt"), "UFL-1.0")
        with self.assertRaises(CommandError):
            cmd.licence_id_for("COPYING")


class CommandTests(TestCase):
    """add/remove against temp copies; network and subsetting are stubbed."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.registry = self.tmp / "dropcaps.py"
        shutil.copy(REGISTRY, self.registry)
        self.fonts = self.tmp / "fonts"
        self.fonts.mkdir()
        cache.delete("site_settings")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        cache.delete("site_settings")

    def _add(self, *args, **kw):
        out = StringIO()
        with (
            mock.patch.object(
                cmd,
                "resolve_google_family",
                return_value={
                    "dir": "ofl/ultra",
                    "files": ["OFL.txt", "Ultra-Regular.ttf", "METADATA.pb"],
                    "licence_file": "OFL.txt",
                    "family": "Ultra",
                },
            ),
            mock.patch.object(cmd, "_fetch", side_effect=self._fake_fetch),
            mock.patch.object(cmd, "subset_to_woff2", return_value=b"wOF2fake"),
        ):
            call_command(
                "dropcap_fonts",
                "add",
                *args,
                registry_path=str(self.registry),
                fonts_dir=str(self.fonts),
                no_css=True,
                stdout=out,
                **kw,
            )
        return out.getvalue()

    @staticmethod
    def _fake_fetch(url, binary=False):
        if url.endswith("OFL.txt"):
            return "SIL OPEN FONT LICENSE Version 1.1"
        return b"\x00\x01ttf" if binary else ""

    def test_add_writes_font_licence_and_registry_entry(self):
        out = self._add("Ultra", group="display", description="Fat slab.")
        self.assertIn("registered 'ultra'", out)
        self.assertEqual(
            (self.fonts / "ultra" / "ultra.woff2").read_bytes(), b"wOF2fake"
        )
        self.assertIn(
            "OPEN FONT LICENSE", (self.fonts / "ultra" / "OFL.txt").read_text()
        )
        text = self.registry.read_text()
        self.assertIn(
            '        "ultra",\n        "Ultra",\n        "Ultra",\n        "display",',
            text,
        )
        self.assertIn('description="Fat slab."', text)
        ast.parse(text)
        # the real registry was not touched
        self.assertNotIn('"ultra"', REGISTRY.read_text())

    def test_add_refuses_registered_key_and_source_without_licence(self):
        with self.assertRaises(CommandError):
            self._add("Cinzel", group="classic", key=dropcaps.STYLES[0].key)
        with self.assertRaises(CommandError):
            call_command(
                "dropcap_fonts",
                "add",
                "Local",
                group="classic",
                source=str(self.registry),
                registry_path=str(self.registry),
                fonts_dir=str(self.fonts),
                no_css=True,
            )

    def test_add_no_register_only_prints_entry(self):
        out = self._add("Ultra", group="display", no_register=True)
        self.assertIn("Add to STYLES", out)
        self.assertIn('"ultra"', out)
        self.assertNotIn('"ultra"', self.registry.read_text())

    def test_remove_refuses_when_in_use_then_forces(self):
        key = dropcaps.STYLES[0].key
        site = SiteSettings.load()
        site.default_dropcap_style = key
        site.save()
        cache.delete("site_settings")
        with self.assertRaises(CommandError):
            call_command(
                "dropcap_fonts",
                "remove",
                key,
                registry_path=str(self.registry),
                fonts_dir=str(self.fonts),
                no_css=True,
            )
        (self.fonts / key).mkdir()
        (self.fonts / key / f"{key}.woff2").write_bytes(b"x")
        out = StringIO()
        call_command(
            "dropcap_fonts",
            "remove",
            key,
            force=True,
            registry_path=str(self.registry),
            fonts_dir=str(self.fonts),
            no_css=True,
            stdout=out,
        )
        self.assertIn("site default", out.getvalue())
        self.assertFalse((self.fonts / key).exists())
        self.assertNotIn(f'"{key}",\n', self.registry.read_text())
        ast.parse(self.registry.read_text())
        cache.delete("site_settings")
        self.assertEqual(SiteSettings.load().default_dropcap_style, "")
        self.assertIn(f'"{key}"', REGISTRY.read_text())  # real registry intact

    def test_remove_unknown_key(self):
        with self.assertRaises(CommandError):
            call_command(
                "dropcap_fonts",
                "remove",
                "no-such-style",
                registry_path=str(self.registry),
                fonts_dir=str(self.fonts),
                no_css=True,
            )

    def test_list_reports_usage(self):
        key = dropcaps.STYLES[1].key
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_user("lister", password="x")
        Post.objects.create(
            title="t",
            slug="list-post",
            author=user,
            content_markdown="x",
            dropcap_style=key,
        )
        out = StringIO()
        call_command("dropcap_fonts", "list", stdout=out)
        text = out.getvalue()
        self.assertIn(f"{len(dropcaps.STYLES)} styles", text)
        row = next(line for line in text.splitlines() if line.startswith(key))
        self.assertTrue(row.rstrip().endswith("1"), row)
