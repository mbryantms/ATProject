"""
Add, remove and list dropcap faces.

    manage.py dropcap_fonts list
    manage.py dropcap_fonts add "Ultra" --group display
    manage.py dropcap_fonts add "Goudy Initialen" --group classic \\
        --source ~/Downloads/GoudyInitialen.ttf --license ~/Downloads/LICENSE.txt
    manage.py dropcap_fonts remove ultra [--force]

``add`` fetches the family from the Google Fonts repository (ofl/, apache/
and ufl/ directories) or takes a local TTF/OTF, subsets it to Latin letters
and digits as woff2, writes it with its licence text under
``static/font/dropcap/<key>/``, inserts a ``_s(...)`` entry into the
registry's group section and regenerates ``dropcaps.css``. ``remove`` does
the reverse and refuses while any post, page or the site default still
uses the key unless ``--force`` (which resets those to inherit; markdown
``::: {.dropcap-<key>}`` blocks are listed for hand editing, since they
simply stop matching once the style is gone).

Only the OFL, Apache and UFL licences are accepted from Google Fonts; a
local font needs its licence file passed explicitly, and it is your call
that the licence permits web embedding.
"""

from __future__ import annotations

import io
import json
import re
import shutil
import urllib.error
import urllib.request
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from engine.markdown import dropcaps

UNICODES = "U+0030-0039,U+0041-005A,U+0061-007A,U+00C0-00D6,U+00D8-00DE"
GOOGLE_RAW = "https://raw.githubusercontent.com/google/fonts/main"
GOOGLE_API = "https://api.github.com/repos/google/fonts/contents"
GOOGLE_DIRS = ("ofl", "apache", "ufl")
LICENCE_FILES = {
    "OFL.txt": "OFL-1.1",
    "LICENSE.txt": "Apache-2.0",
    "UFL.txt": "UFL-1.0",
}
GROUP_LABELS = dict(dropcaps.GROUPS)


# ---------------------------------------------------------------------------
# Pure helpers (tested without network or filesystem)


def slugify_family(family: str) -> str:
    """Google Fonts directory name for a family: lowercase, no spaces."""
    return re.sub(r"[^a-z0-9]", "", family.lower())


def key_for_family(family: str) -> str:
    """Registry key: hyphenated lowercase words."""
    key = re.sub(r"[^a-z0-9]+", "-", family.lower()).strip("-")
    if not key:
        raise CommandError(f"Cannot derive a key from {family!r}; pass --key.")
    return key


def choose_font_file(names: list[str], preferred: str | None = None) -> str:
    """Pick the face to ship from a family's TTF file names.

    Preference: an explicit ``preferred`` name, then a variable face
    (``[wght]``), then ``-Regular``, then the first file.
    """
    ttfs = [n for n in names if n.lower().endswith((".ttf", ".otf"))]
    if not ttfs:
        raise CommandError("No TTF/OTF files found in the family directory.")
    if preferred:
        if preferred in ttfs:
            return preferred
        raise CommandError(f"{preferred!r} is not one of: {', '.join(ttfs)}")
    variable = [n for n in ttfs if "[" in n and "Italic" not in n]
    if variable:
        return variable[0]
    regular = [n for n in ttfs if "-Regular" in n or n.count("-") == 0]
    if regular:
        return regular[0]
    return ttfs[0]


def render_entry_source(
    *,
    key: str,
    label: str,
    family: str,
    group: str,
    weight: int = 400,
    variable: bool = False,
    scale: float = 1.0,
    nudge: float = 0.0,
    gap: float = 0.1,
    license: str = "OFL-1.1",
    description: str = "",
) -> str:
    """The ``_s(...)`` block for the registry, in the file's ruff layout."""
    lines = [
        "    _s(",
        f"        {key!r},",
        f"        {label!r},",
        f"        {family!r},",
        f"        {group!r},",
    ]
    if variable:
        lines.append("        variable=True,")
    if weight != 400:
        lines.append(f"        weight={weight},")
    if scale != 1.0:
        lines.append(f"        scale={scale:g},")
    if nudge:
        lines.append(f"        nudge={nudge:g},")
    if gap != 0.1:
        lines.append(f"        gap={gap:g},")
    if license != "OFL-1.1":
        lines.append(f"        license={license!r},")
    lines.append(f"        description={description!r},")
    lines.append("    ),")
    return "\n".join(lines).replace("'", '"') + "\n"


def _group_marker(group: str) -> str:
    return f"    # {GROUP_LABELS[group]}\n"


def insert_entry_source(registry_text: str, entry: str, group: str) -> str:
    """Insert ``entry`` at the end of ``group``'s section of ``STYLES``."""
    if group not in GROUP_LABELS:
        raise CommandError(f"Unknown group {group!r}; one of {list(GROUP_LABELS)}")
    marker = _group_marker(group)
    start = registry_text.find(marker)
    if start == -1:
        raise CommandError(f"Registry has no section comment for group {group!r}")
    # The section ends at the next group marker, or at the tuple's close.
    next_positions = [
        registry_text.find(_group_marker(g), start + len(marker))
        for g in GROUP_LABELS
        if g != group
    ]
    next_positions = [p for p in next_positions if p != -1]
    close = registry_text.find("\n)\n", start)
    end = min(next_positions + [close + 1])  # +1: keep the newline before ')'
    return registry_text[:end] + entry + registry_text[end:]


def remove_entry_source(registry_text: str, key: str) -> str:
    """Delete the ``_s(...)`` block whose first argument is ``key``."""
    pattern = re.compile(
        r"^    _s\(\n        \"" + re.escape(key) + r"\",\n(?:        .*\n)*?    \),\n",
        re.M,
    )
    text, n = pattern.subn("", registry_text)
    if n != 1:
        raise CommandError(f"Registry entry for {key!r} not found (matched {n}).")
    return text


def licence_id_for(filename: str) -> str:
    try:
        return LICENCE_FILES[filename]
    except KeyError as exc:
        raise CommandError(
            f"Unrecognised licence file {filename!r}; expected one of "
            f"{', '.join(LICENCE_FILES)}"
        ) from exc


# ---------------------------------------------------------------------------
# Network + font processing


def _fetch(url: str, *, binary: bool = False):
    req = urllib.request.Request(url, headers={"User-Agent": "ATProject dropcap_fonts"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
            data = resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise CommandError(f"{url}: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise CommandError(f"{url}: {exc.reason}") from exc
    return data if binary else data.decode("utf-8")


def resolve_google_family(family: str) -> dict:
    """Locate a family in google/fonts; returns dir, files, licence and the
    display name from METADATA.pb."""
    slug = slugify_family(family)
    for top in GOOGLE_DIRS:
        listing = _fetch(f"{GOOGLE_API}/{top}/{slug}")
        if listing is None:
            continue
        names = [item["name"] for item in json.loads(listing)]
        licence = next((n for n in LICENCE_FILES if n in names), None)
        if licence is None:
            raise CommandError(
                f"{top}/{slug} has no recognised licence file; refusing to ship it."
            )
        display = family
        if "METADATA.pb" in names:
            meta = _fetch(f"{GOOGLE_RAW}/{top}/{slug}/METADATA.pb") or ""
            m = re.search(r'^name:\s*"([^"]+)"', meta, re.M)
            if m:
                display = m.group(1)
        return {
            "dir": f"{top}/{slug}",
            "files": names,
            "licence_file": licence,
            "family": display,
        }
    raise CommandError(
        f"{family!r} ({slug}) is not in google/fonts under {', '.join(GOOGLE_DIRS)}."
    )


def subset_to_woff2(font_bytes: bytes) -> bytes:
    try:
        from fontTools import subset
        from fontTools.ttLib import TTFont
    except ImportError as exc:  # pragma: no cover - dev dependency
        raise CommandError(
            "fonttools is not installed; run `uv sync` (it is a dev dependency)."
        ) from exc
    font = TTFont(io.BytesIO(font_bytes))
    options = subset.Options()
    options.flavor = "woff2"
    options.layout_features = ["*"]
    options.name_IDs = ["*"]
    options.notdef_outline = True
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(unicodes=subset.parse_unicodes(UNICODES))
    subsetter.subset(font)
    out = io.BytesIO()
    font.flavor = "woff2"
    font.save(out)
    return out.getvalue()


# ---------------------------------------------------------------------------


class Command(BaseCommand):
    help = "Add, remove or list dropcap faces (fonts + registry + stylesheet)."

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest="action", required=True)

        sub.add_parser("list", help="Show every registered style and its file.")

        add = sub.add_parser("add", help="Fetch, subset and register a face.")
        add.add_argument("family", help="Google Fonts family name (or slug).")
        add.add_argument("--group", required=True, choices=list(GROUP_LABELS))
        add.add_argument("--key", help="Registry key (default: from the family).")
        add.add_argument("--label", help="Picker label (default: family name).")
        add.add_argument("--file", help="Which TTF in the family dir to use.")
        add.add_argument(
            "--source", help="Local TTF/OTF instead of Google Fonts (needs --license)."
        )
        add.add_argument("--license", help="Licence text file for --source.")
        add.add_argument("--weight", type=int, default=None)
        add.add_argument("--scale", type=float, default=1.0)
        add.add_argument("--nudge", type=float, default=0.0)
        add.add_argument("--gap", type=float, default=0.1)
        add.add_argument("--description", default="")
        add.add_argument(
            "--no-register",
            action="store_true",
            help="Write the font but only print the registry entry.",
        )

        rm = sub.add_parser("remove", help="Unregister a face and delete its files.")
        # dest differs from add's --key so call_command() can map both.
        rm.add_argument("style_key", metavar="key")
        rm.add_argument(
            "--force",
            action="store_true",
            help="Also reset posts/pages/site default that use the key.",
        )

        for p in (add, rm):
            p.add_argument("--registry-path", help="(tests) alternate registry file")
            p.add_argument("--fonts-dir", help="(tests) alternate font directory")
            p.add_argument(
                "--no-css", action="store_true", help="Skip regenerating dropcaps.css"
            )

    # -- paths

    def _registry_path(self, options) -> Path:
        if options.get("registry_path"):
            return Path(options["registry_path"])
        return Path(settings.BASE_DIR) / "engine" / "markdown" / "dropcaps.py"

    def _fonts_dir(self, options) -> Path:
        if options.get("fonts_dir"):
            return Path(options["fonts_dir"])
        return Path(settings.BASE_DIR) / "static" / "font" / "dropcap"

    def _regenerate(self, options):
        if options.get("no_css"):
            return
        call_command("generate_dropcaps_css", stdout=self.stdout)

    # -- actions

    def handle(self, *args, **options):
        action = options["action"]
        if action == "list":
            return self.handle_list(options)
        if action == "add":
            return self.handle_add(options)
        if action == "remove":
            return self.handle_remove(options)

    def handle_list(self, options):
        fonts_dir = self._fonts_dir(options)
        usage = self._usage_counts()
        self.stdout.write(
            f"{'key':<24}{'group':<14}{'weight':<8}{'file':>9}  {'licence':<11}usage"
        )
        for s in dropcaps.STYLES:
            path = fonts_dir / s.key / (s.file or f"{s.key}.woff2")
            size = f"{path.stat().st_size // 1024}K" if path.exists() else "MISSING"
            used = usage.get(s.key, 0)
            self.stdout.write(
                f"{s.key:<24}{s.group:<14}{s.weight:<8}{size:>9}  {s.license:<11}"
                f"{used or ''}"
            )
        self.stdout.write(f"{len(dropcaps.STYLES)} styles")

    def handle_add(self, options):
        family = options["family"]
        group = options["group"]
        source = options.get("source")

        if source:
            if not options.get("license"):
                raise CommandError("--source needs --license <file>.")
            font_bytes = Path(source).read_bytes()
            licence_path = Path(options["license"])
            licence_name = licence_path.name
            if licence_name not in LICENCE_FILES:
                licence_name = "LICENSE.txt"
                licence_id = "See LICENSE.txt"
            else:
                licence_id = LICENCE_FILES[licence_name]
            licence_text = licence_path.read_text()
            display = family
            chosen = Path(source).name
        else:
            info = resolve_google_family(family)
            chosen = choose_font_file(info["files"], options.get("file"))
            self.stdout.write(f"google/fonts {info['dir']}: using {chosen}")
            url = f"{GOOGLE_RAW}/{info['dir']}/{chosen}".replace("[", "%5B").replace(
                "]", "%5D"
            )
            font_bytes = _fetch(url, binary=True)
            if font_bytes is None:
                raise CommandError(f"Could not download {url}")
            licence_name = info["licence_file"]
            licence_id = licence_id_for(licence_name)
            licence_text = _fetch(f"{GOOGLE_RAW}/{info['dir']}/{licence_name}") or ""
            display = info["family"]

        key = options.get("key") or key_for_family(display)
        if dropcaps.is_style_key(key):
            raise CommandError(f"{key!r} is already registered; remove it first.")
        label = options.get("label") or display
        variable = "[" in chosen
        weight = options.get("weight")
        if weight is None:
            weight = 700 if "Bold" in chosen else 400

        woff2 = subset_to_woff2(font_bytes)
        target = self._fonts_dir(options) / key
        target.mkdir(parents=True, exist_ok=True)
        (target / f"{key}.woff2").write_bytes(woff2)
        (target / licence_name).write_text(licence_text)
        self.stdout.write(
            f"wrote {target / (key + '.woff2')} ({len(woff2) // 1024}K) + {licence_name}"
        )

        entry = render_entry_source(
            key=key,
            label=label,
            family=display,
            group=group,
            weight=weight,
            variable=variable,
            scale=options["scale"],
            nudge=options["nudge"],
            gap=options["gap"],
            license=licence_id,
            description=options["description"],
        )
        if options.get("no_register"):
            self.stdout.write("Add to STYLES in engine/markdown/dropcaps.py:\n" + entry)
            return
        registry = self._registry_path(options)
        registry.write_text(insert_entry_source(registry.read_text(), entry, group))
        self.stdout.write(f"registered {key!r} in {registry.name} ({group})")
        self._regenerate(options)
        self.stdout.write(
            self.style.SUCCESS(
                f"Added {label} as dropcap-{key}. Check it on the admin gallery "
                "page and tune scale/nudge/gap in the registry if the cap sits off."
            )
        )

    def handle_remove(self, options):
        key = options["style_key"]
        if not dropcaps.is_style_key(key):
            raise CommandError(f"{key!r} is not a registered style.")

        from engine.models import Page, Post, SiteSettings

        posts = Post.all_objects.filter(dropcap_style=key)
        pages = Page.objects.filter(dropcap_style=key)
        site = SiteSettings.load()
        site_uses = site.default_dropcap_style == key
        marker = f".dropcap-{key}"
        md_posts = list(
            Post.all_objects.filter(content_markdown__contains=marker).values_list(
                "slug", flat=True
            )
        )
        md_pages = list(
            Page.objects.filter(content__contains=marker).values_list("slug", flat=True)
        )

        in_use = posts.exists() or pages.exists() or site_uses
        if in_use and not options["force"]:
            raise CommandError(
                f"{key!r} is in use: {posts.count()} post(s), {pages.count()} "
                f"page(s){', and the site default' if site_uses else ''}. "
                "Re-run with --force to reset them to inherit."
            )
        if in_use:
            n = posts.update(dropcap_style=dropcaps.INHERIT)
            m = pages.update(dropcap_style=dropcaps.INHERIT)
            if site_uses:
                site.default_dropcap_style = dropcaps.INHERIT
                site.save()
            self.stdout.write(
                f"reset {n} post(s), {m} page(s)"
                f"{' and the site default' if site_uses else ''} to inherit"
            )
        for kind, slugs in (("post", md_posts), ("page", md_pages)):
            for slug in slugs:
                self.stdout.write(
                    self.style.WARNING(
                        f"{kind} {slug!r} still has a `{marker}` block in its "
                        "markdown; it will render without a dropcap until edited."
                    )
                )

        registry = self._registry_path(options)
        registry.write_text(remove_entry_source(registry.read_text(), key))
        folder = self._fonts_dir(options) / key
        if folder.exists():
            shutil.rmtree(folder)
        self.stdout.write(f"removed {key!r} from {registry.name} and {folder}")
        self._regenerate(options)
        self.stdout.write(self.style.SUCCESS(f"Removed dropcap-{key}."))

    def _usage_counts(self) -> dict[str, int]:
        from django.db.models import Count

        from engine.models import Page, Post, SiteSettings

        counts: dict[str, int] = {}
        for model in (Post.all_objects, Page.objects):
            for row in (
                model.exclude(dropcap_style="")
                .values("dropcap_style")
                .annotate(n=Count("pk"))
            ):
                counts[row["dropcap_style"]] = counts.get(row["dropcap_style"], 0)
                counts[row["dropcap_style"]] += row["n"]
        site_key = SiteSettings.load().default_dropcap_style
        if site_key:
            counts[site_key] = counts.get(site_key, 0) + 1
        return counts
