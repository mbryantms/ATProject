"""
Admin classes for Post model and related inlines.

This module contains the admin configuration for posts, including
internal links (backlinks), post-asset relationships, and revision history.
"""

import csv
import difflib
import re

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from engine.models import (
    InternalLink,
    Post,
    PostAsset,
    PostCitation,
    PostRevision,
    PostSimilarity,
    PostSlugHistory,
)

from .display import admin_change_link
from .mixins import ReadOnlyAdminMixin, SoftDeleteAdminMixin

# Curated list of CSL styles supported by the citeproc-js bridge.
# Leaving blank uses the site-wide default.
CITATION_STYLE_CHOICES = [
    ("", "— Use site default —"),
    ("chicago-author-date", "Chicago (author-date)"),
    ("chicago-note-bibliography", "Chicago (notes & bibliography)"),
    ("apa", "APA 7th edition"),
    ("modern-language-association", "MLA 9th edition"),
    ("ieee", "IEEE"),
    ("nature", "Nature"),
    ("harvard-cite-them-right", "Harvard (Cite Them Right)"),
    ("vancouver", "Vancouver"),
]

# Static sample renderings to help an author pick a citation style
# without leaving the change form. These are illustrative, not authoritative —
# the real renderer is citeproc-js on the server.
_CITATION_STYLE_SAMPLES = [
    (
        "chicago-author-date",
        "(Smith 2024, 42)",
        "Smith, Jane. 2024. “A Short Article.” Journal of Things 12 (3): 37–58.",
    ),
    (
        "chicago-note-bibliography",
        "¹ Jane Smith, “A Short Article,”…",
        "Smith, Jane. “A Short Article.” Journal of Things 12, no. 3 (2024): 37–58.",
    ),
    (
        "apa",
        "(Smith, 2024, p. 42)",
        "Smith, J. (2024). A short article. Journal of Things, 12(3), 37–58.",
    ),
    (
        "modern-language-association",
        "(Smith 42)",
        "Smith, Jane. “A Short Article.” Journal of Things, vol. 12, no. 3, 2024, pp. 37–58.",
    ),
    (
        "ieee",
        "[1]",
        "[1] J. Smith, “A short article,” J. Things, vol. 12, no. 3, pp. 37–58, 2024.",
    ),
    (
        "nature",
        "Smith, J. ¹",
        "1. Smith, J. A short article. J. Things 12, 37–58 (2024).",
    ),
    (
        "harvard-cite-them-right",
        "(Smith, 2024)",
        "Smith, J. (2024) ‘A short article’, Journal of Things, 12(3), pp. 37–58.",
    ),
    ("vancouver", "(1)", "1. Smith J. A short article. J Things. 2024;12(3):37–58."),
]


def _build_citation_style_help_html():
    rows = []
    for key, inline, bib in _CITATION_STYLE_SAMPLES:
        label = dict(CITATION_STYLE_CHOICES).get(key, key)
        rows.append(
            f'<div class="mk-cs-entry">'
            f"<h5>{label} <code>{key}</code></h5>"
            f'<div class="mk-cs-sample">Inline: {inline}</div>'
            f'<div class="mk-cs-sample">Bibliography: {bib}</div>'
            f"</div>"
        )
    # The toggle behavior lives in static/js/admin-post-aux.js (loaded via
    # PostAdmin.Media) — an external file so the site's nonce CSP doesn't block
    # it, and so the JS is linted/cached in one place.
    return (
        '<span class="mk-citestyle-help">'
        "<button type='button' class='mk-citestyle-help-btn' "
        "aria-label='Show citation style examples'>?</button>"
        '<div class="mk-citestyle-help-panel" role="dialog">'
        "<strong>Sample output per style</strong>"
        '<div style="margin-top:6px;">' + "".join(rows) + "</div>"
        "</div>"
        "</span>"
    )


CITATION_STYLE_HELP_HTML = _build_citation_style_help_html()

# Regex matching asset references in markdown: @asset:key or @alias used
# inside a markdown link/image target. Mirrors the production
# asset_resolver preprocessor pattern so orphan warnings stay in sync.
_ASSET_REF_RE = re.compile(r"!?\[[^\]]*\]\(@(asset:)?([a-zA-Z0-9_-]+)(?:\?[^\)]*)?\)")


# Fenced-div snippets surfaced in the CM6 editor when a line starts with ``:::``.
# Templates use CM6 snippet syntax (``${n:placeholder}`` / ``$0`` for final cursor).
EDITOR_FENCE_SNIPPETS = [
    {
        "className": "admonition-tip",
        "detail": "Tip callout",
        "template": "::: {.admonition-tip}\n# ${1:Title}\n\n${2:Body}\n:::\n$0",
    },
    {
        "className": "admonition-note",
        "detail": "Neutral note callout",
        "template": "::: {.admonition-note}\n# ${1:Title}\n\n${2:Body}\n:::\n$0",
    },
    {
        "className": "admonition-warning",
        "detail": "Warning callout",
        "template": "::: {.admonition-warning}\n# ${1:Title}\n\n${2:Body}\n:::\n$0",
    },
    {
        "className": "admonition-error",
        "detail": "Error / pitfall callout",
        "template": "::: {.admonition-error}\n# ${1:Title}\n\n${2:Body}\n:::\n$0",
    },
    {
        "className": "epigraph",
        "detail": "Opening epigraph quote",
        "template": "::: {.epigraph}\n> ${1:Quote}\n>\n> --- ${2:Attribution}\n:::\n$0",
    },
    {
        "className": "columns",
        "detail": "Multi-column list",
        "template": "::: {.columns}\n- ${1:item}\n- ${2:item}\n- ${3:item}\n:::\n$0",
    },
    {
        "className": "text-center",
        "detail": "Center-aligned block",
        "template": "::: {.text-center}\n${1:Content}\n:::\n$0",
    },
    {
        "className": "text-right",
        "detail": "Right-aligned block",
        "template": "::: {.text-right}\n${1:Content}\n:::\n$0",
    },
    {
        "className": "sans-serif",
        "detail": "Sans-serif paragraphs",
        "template": "::: {.sans-serif}\n${1:Content}\n:::\n$0",
    },
    {
        "className": "float-left",
        "detail": "Float a block to the left",
        "template": "::: {.float-left}\n${1:Content}\n:::\n$0",
    },
    {
        "className": "float-right",
        "detail": "Float a block to the right",
        "template": "::: {.float-right}\n${1:Content}\n:::\n$0",
    },
    {
        "className": "width-full",
        "detail": "Full-bleed width block",
        "template": "::: {.width-full}\n${1:Content}\n:::\n$0",
    },
    {
        "className": "table-small",
        "detail": "Compact/dense table variant",
        "template": "::: {.table-small}\n| ${1:a} | ${2:b} |\n|---|---|\n| ${3:1} | ${4:2} |\n:::\n$0",
    },
    {
        "className": "sortable",
        "detail": "Client-sortable table",
        "template": "::: {.sortable}\n| ${1:Col 1} | ${2:Col 2} |\n|---|---|\n| ${3:a} | ${4:b} |\n:::\n$0",
    },
]

# Inline class names surfaced when the cursor is inside ``{.``. These apply to
# bracketed spans (``[text]{.smallcaps}``), images/links (``![alt](src){.class}``),
# and fenced divs. Not every class is valid in every context, but that's on the
# author — the list is grouped rough-by-use.
EDITOR_INLINE_CLASSES = [
    # Spans
    {"name": "smallcaps", "detail": "Small caps"},
    {"name": "marginnote", "detail": "Margin note (outer-margin)"},
    {"name": "sidenote", "detail": "Sidebar sidenote"},
    {"name": "tabular-nums", "detail": "Tabular / lined numerals"},
    {"name": "sans-serif", "detail": "Sans-serif run"},
    {"name": "date-since", "detail": "Date + 'N years ago' subscript"},
    {"name": "date-range", "detail": "Date range with duration subscript"},
    {"name": "date-range-since", "detail": "Date range + years since end"},
    # Layout utilities
    {"name": "text-center", "detail": "Center-align"},
    {"name": "text-right", "detail": "Right-align"},
    {"name": "float-left", "detail": "Float left"},
    {"name": "float-right", "detail": "Float right"},
    {"name": "width-full", "detail": "Full-bleed width"},
    {"name": "icon-not", "detail": "Suppress auto link icon"},
    # Fenced-div modifiers
    {"name": "admonition-tip", "detail": "Tip callout"},
    {"name": "admonition-note", "detail": "Note callout"},
    {"name": "admonition-warning", "detail": "Warning callout"},
    {"name": "admonition-error", "detail": "Error callout"},
    {"name": "epigraph", "detail": "Epigraph block"},
    {"name": "columns", "detail": "Multi-column list"},
    {"name": "table-small", "detail": "Compact table"},
    {"name": "sortable", "detail": "Sortable table"},
]


MARKDOWN_CHEATSHEET_HTML = """
<details class="markdown-cheatsheet">
<summary>📖 Markdown reference — click to expand</summary>
<div class="mc-body">
  <p class="mc-lead">Pandoc-flavoured Markdown with project extensions. All sections collapsed by default — open the ones you need.</p>

  <details>
    <summary>Inline formatting</summary>
    <table>
      <tr><td class="mc-syntax"><code>**bold**</code></td><td class="mc-desc">Bold</td></tr>
      <tr><td class="mc-syntax"><code>*italic*</code></td><td class="mc-desc">Italic</td></tr>
      <tr><td class="mc-syntax"><code>***bold italic***</code></td><td class="mc-desc">Bold + italic</td></tr>
      <tr><td class="mc-syntax"><code>~~strike~~</code></td><td class="mc-desc">Strikethrough</td></tr>
      <tr><td class="mc-syntax"><code>`inline code`</code></td><td class="mc-desc">Inline code</td></tr>
      <tr><td class="mc-syntax"><code>H~2~O</code></td><td class="mc-desc">Subscript</td></tr>
      <tr><td class="mc-syntax"><code>x^2^</code></td><td class="mc-desc">Superscript (adjacent sub+sup are auto-stacked)</td></tr>
      <tr><td class="mc-syntax"><code>[SPQR]{.smallcaps}</code></td><td class="mc-desc">Small caps</td></tr>
      <tr><td class="mc-syntax"><code>[note here]{.marginnote}</code></td><td class="mc-desc">Margin note (bracketed span, renders in outer margin)</td></tr>
      <tr><td class="mc-syntax"><code>[0123]{.tabular-nums}</code></td><td class="mc-desc">Tabular (lined-up) numerals</td></tr>
      <tr><td class="mc-syntax"><code>[text]{.sans-serif}</code></td><td class="mc-desc">Sans-serif inline run</td></tr>
      <tr><td class="mc-syntax">line 1 <em>(two trailing spaces)</em><br/>line 2</td><td class="mc-desc">Hard line break</td></tr>
      <tr><td class="mc-syntax"><code>*[HTML]: Hyper Text Markup Language</code></td><td class="mc-desc">Abbreviation — expands all occurrences into <code>&lt;abbr&gt;</code></td></tr>
    </table>
    <p class="mc-note">Smart punctuation is automatic: <code>--</code> → en-dash, <code>---</code> → em-dash, <code>...</code> → ellipsis, straight quotes → curly.</p>
  </details>

  <details>
    <summary>Headings &amp; structural blocks</summary>
    <table>
      <tr><td class="mc-syntax"><code># H1</code> … <code>###### H6</code></td><td class="mc-desc">Headings — auto-anchored, auto-sectionized, copy-link button</td></tr>
      <tr><td class="mc-syntax"><code>## Heading {#custom-id}</code></td><td class="mc-desc">Heading with explicit anchor ID</td></tr>
      <tr><td class="mc-syntax"><code>&gt; quote</code></td><td class="mc-desc">Blockquote (nesting supported; nested levels auto-classed)</td></tr>
      <tr><td class="mc-syntax"><code>&gt; {&gt;&gt;} text</code><br/><code>&gt; {&lt;&lt;} text</code></td><td class="mc-desc">Float blockquote right / left</td></tr>
      <tr><td class="mc-syntax"><code>---</code> · <code>***</code> · <code>___</code></td><td class="mc-desc">Horizontal rule (three or more)</td></tr>
      <tr><td class="mc-syntax"><code>```lang<br/>code<br/>```</code></td><td class="mc-desc">Fenced code block with syntax highlighting</td></tr>
      <tr><td class="mc-syntax"><code>&lt;blank line&gt;<br/>    4-space indent</code></td><td class="mc-desc">Indented code block (no highlighting)</td></tr>
      <tr><td class="mc-syntax"><code>term<br/>:   definition</code></td><td class="mc-desc">Definition list</td></tr>
      <tr><td class="mc-syntax"><code>- [ ] todo</code><br/><code>- [x] done</code></td><td class="mc-desc">Task list (display-only checkboxes)</td></tr>
    </table>
  </details>

  <details>
    <summary>Lists</summary>
    <table>
      <tr><td class="mc-syntax"><code>- item</code> · <code>* item</code> · <code>+ item</code></td><td class="mc-desc">Unordered list (indent 4 spaces to nest)</td></tr>
      <tr><td class="mc-syntax"><code>1. item</code> or <code>1) item</code></td><td class="mc-desc">Ordered list</td></tr>
      <tr><td class="mc-syntax"><code>5. item</code></td><td class="mc-desc">Ordered list starting at 5 (fancy-lists)</td></tr>
      <tr><td class="mc-syntax"><code>a. item</code> · <code>I) item</code> · <code>i. item</code></td><td class="mc-desc">Alpha / roman numbering</td></tr>
    </table>
    <p class="mc-note">Nesting auto-classifies levels (<code>.list-level-1</code>, etc.). Mixed ordered/unordered is supported at each level.</p>
  </details>

  <details>
    <summary>Links &amp; decorators</summary>
    <table>
      <tr><td class="mc-syntax"><code>[text](https://example.com)</code></td><td class="mc-desc">External link — auto gets <code>target="_blank"</code>, <code>rel="noopener"</code>, and a domain or file-type icon</td></tr>
      <tr><td class="mc-syntax"><code>[text](/posts/other-slug/)</code></td><td class="mc-desc">Internal link — backlinks auto-extracted on save</td></tr>
      <tr><td class="mc-syntax"><code>[text](url "hover title")</code></td><td class="mc-desc">Link with title attribute</td></tr>
      <tr><td class="mc-syntax"><code>[text](url){.icon-not}</code></td><td class="mc-desc">Suppress the auto link icon</td></tr>
      <tr><td class="mc-syntax"><code>https://example.com</code></td><td class="mc-desc">Bare URL is auto-linked</td></tr>
      <tr><td class="mc-syntax"><code>[text][ref]</code> … <code>[ref]: url</code></td><td class="mc-desc">Reference-style link (defined anywhere in the doc)</td></tr>
    </table>
    <p class="mc-note">Auto-decorated domains include ArXiv, GitHub, Wikipedia, YouTube, Twitter/X, Mastodon, Reddit, NYT, Google Scholar, PubMed, Internet Archive, and more. File-type icons cover PDF, doc, image, video, audio, archive, code.</p>
  </details>

  <details>
    <summary>Images &amp; media</summary>
    <table>
      <tr><td class="mc-syntax"><code>![Alt text](@asset:my-key)</code></td><td class="mc-desc">Global asset by key — responsive srcset, lazy, sized from metadata</td></tr>
      <tr><td class="mc-syntax"><code>![Alt text](@fig1)</code></td><td class="mc-desc">Post-local alias (set on the Post Asset row)</td></tr>
      <tr><td class="mc-syntax"><code>![Alt](@asset:key?width=400)</code></td><td class="mc-desc">Width override (in px); aspect ratio preserved</td></tr>
      <tr><td class="mc-syntax"><code>![Alt](@asset:key "Caption text")</code></td><td class="mc-desc">Image with caption (rendered in a <code>&lt;figure&gt;</code>)</td></tr>
      <tr><td class="mc-syntax"><code>![Alt](@asset:key){.float-right}</code></td><td class="mc-desc">Float right (also <code>.float-left</code>)</td></tr>
      <tr><td class="mc-syntax"><code>![Alt](@asset:key){.width-full}</code></td><td class="mc-desc">Full bleed width</td></tr>
      <tr><td class="mc-syntax"><code>![](@asset:clip)</code></td><td class="mc-desc">Video / audio — asset type is auto-detected, controls added</td></tr>
      <tr><td class="mc-syntax"><code>![](@asset:clip?loop=1&amp;autoplay=1)</code></td><td class="mc-desc">Video query params: <code>loop</code>, <code>autoplay</code>, <code>muted</code></td></tr>
    </table>
  </details>

  <details>
    <summary>Citations</summary>
    <table>
      <tr><td class="mc-syntax"><code>[@smith2020]</code></td><td class="mc-desc">Parenthetical citation</td></tr>
      <tr><td class="mc-syntax"><code>[@smith2020, pp. 42–44]</code></td><td class="mc-desc">With locator</td></tr>
      <tr><td class="mc-syntax"><code>@smith2020</code></td><td class="mc-desc">Narrative ("Smith (2020) showed…")</td></tr>
      <tr><td class="mc-syntax"><code>[-@smith2020]</code></td><td class="mc-desc">Suppress author (year only)</td></tr>
      <tr><td class="mc-syntax"><code>[@a; @b, p. 10; @c]</code></td><td class="mc-desc">Multi-citation (semicolon-separated)</td></tr>
    </table>
    <p class="mc-note">Unknown keys render as <code>[??key]</code>. Keys come from the Source library. Citation style is set per-post or site-wide — see the <em>Rendering &amp; Metadata</em> section.</p>
  </details>

  <details>
    <summary>Footnotes</summary>
    <table>
      <tr><td class="mc-syntax"><code>A claim.[^1]</code><br/><code>[^1]: The footnote body.</code></td><td class="mc-desc">Reference-style footnote (define anywhere)</td></tr>
      <tr><td class="mc-syntax"><code>A claim.^[Inline footnote.]</code></td><td class="mc-desc">Inline footnote (no separate definition)</td></tr>
    </table>
    <p class="mc-note">All footnotes collect into a single "Footnotes" section at the bottom with backlink arrows.</p>
  </details>

  <details>
    <summary>Math</summary>
    <table>
      <tr><td class="mc-syntax"><code>$E = mc^2$</code></td><td class="mc-desc">Inline math</td></tr>
      <tr><td class="mc-syntax"><code>$$<br/>\\int_0^\\infty e^{-x}\\,dx = 1<br/>$$</code></td><td class="mc-desc">Display math (copy-LaTeX button added automatically)</td></tr>
    </table>
    <p class="mc-note">Full LaTeX math via MathJax — custom <code>\\newcommand</code> persists within a post.</p>
  </details>

  <details>
    <summary>Tables</summary>
    <pre>| Right | Left | Center | Default |
|------:|:-----|:------:|---------|
|    12 | foo  |  bar   | baz     |

: Caption goes under the table.</pre>
    <table>
      <tr><td class="mc-syntax"><code>: Caption here</code></td><td class="mc-desc">Caption line after the table</td></tr>
      <tr><td class="mc-syntax"><code>::: {.table-small} … :::</code></td><td class="mc-desc">Compact / dense table variant</td></tr>
      <tr><td class="mc-syntax"><code>::: {.width-full} … :::</code></td><td class="mc-desc">Full-width table</td></tr>
      <tr><td class="mc-syntax"><code>::: {.sortable} … :::</code></td><td class="mc-desc">Client-sortable table</td></tr>
      <tr><td class="mc-syntax"><code>::: {.float-right} … :::</code></td><td class="mc-desc">Floated table</td></tr>
      <tr><td class="mc-syntax">Pandoc grid tables</td><td class="mc-desc">Use <code>+---+---+</code> / <code>|…|</code> grids for multi-line or spanned cells</td></tr>
    </table>
  </details>

  <details>
    <summary>Admonitions (callout boxes)</summary>
    <pre>::: {.admonition-tip}
# Optional title
Body paragraph.
:::

::: {.admonition-note}
Body without a title still works.
:::</pre>
    <p class="mc-note">Four types: <code>tip</code>, <code>note</code>, <code>warning</code>, <code>error</code>. Title is optional — if present, it must be a heading line (<code>#</code>…<code>######</code>) immediately inside the fence; it's converted to a styled title row.</p>
  </details>

  <details>
    <summary>Layout &amp; utility blocks</summary>
    <table>
      <tr><td class="mc-syntax"><code>::: {.epigraph}<br/>&gt; Quote<br/>&gt;<br/>&gt; --- Attribution<br/>:::</code></td><td class="mc-desc">Epigraph — blockquote + right-aligned attribution</td></tr>
      <tr><td class="mc-syntax"><code>::: {.columns}<br/>- a<br/>- b<br/>- c<br/>:::</code></td><td class="mc-desc">Multi-column layout (applies to the nested list)</td></tr>
      <tr><td class="mc-syntax"><code>::: {.text-center} … :::</code></td><td class="mc-desc">Center-align the paragraphs inside</td></tr>
      <tr><td class="mc-syntax"><code>::: {.text-right} … :::</code></td><td class="mc-desc">Right-align</td></tr>
      <tr><td class="mc-syntax"><code>::: {.sans-serif} … :::</code></td><td class="mc-desc">Switch paragraphs to the sans-serif stack</td></tr>
      <tr><td class="mc-syntax"><code>::: {.float-left} … :::</code> · <code>{.float-right}</code> · <code>{.width-full}</code></td><td class="mc-desc">Float or full-bleed any block</td></tr>
    </table>
  </details>

  <details>
    <summary>Dates</summary>
    <table>
      <tr><td class="mc-syntax"><code>[2020-01-15]{.date-since}</code></td><td class="mc-desc">Renders date + subscript "Ny ago"</td></tr>
      <tr><td class="mc-syntax"><code>[1500–1600]{.date-range}</code></td><td class="mc-desc">Date range with duration subscript between the years</td></tr>
      <tr><td class="mc-syntax"><code>[1500–1600]{.date-range-since}</code></td><td class="mc-desc">Range + "years since end date"</td></tr>
    </table>
    <p class="mc-note">Separator must be an en-dash (<code>–</code>), em-dash (<code>—</code>), or <code>--</code>. Year-only, ISO dates, BC/BCE, and natural dates all supported.</p>
  </details>

  <details>
    <summary>Raw HTML &amp; escapes</summary>
    <table>
      <tr><td class="mc-syntax"><code>&lt;div class="my-class"&gt;…&lt;/div&gt;</code></td><td class="mc-desc">Raw HTML is passed through, then sanitized — scripts and event handlers stripped</td></tr>
      <tr><td class="mc-syntax"><code>\\*not italic\\*</code></td><td class="mc-desc">Backslash escape any markdown metacharacter</td></tr>
    </table>
    <p class="mc-note">Allowed tags include all structural, semantic, and media tags plus <code>data-*</code> / <code>aria-*</code> attributes. Disallowed: <code>&lt;script&gt;</code>, <code>&lt;style&gt;</code>, <code>on*=</code> handlers.</p>
  </details>

  <details>
    <summary>Automatic — things you don't have to type</summary>
    <table>
      <tr><td class="mc-syntax">Heading anchors</td><td class="mc-desc">Every heading gets a slugified <code>id</code> + copy-link button</td></tr>
      <tr><td class="mc-syntax">First paragraph</td><td class="mc-desc">Tagged <code>.first-graf</code>; post-level "Intro paragraph small caps" toggle uses it</td></tr>
      <tr><td class="mc-syntax">Smart punctuation</td><td class="mc-desc"><code>"…"</code>, en/em-dashes, ellipsis, no-break spaces for units</td></tr>
      <tr><td class="mc-syntax">Sub/super stacking</td><td class="mc-desc">Adjacent <code>~sub~</code> + <code>^sup^</code> wrapped in <code>.subsup</code> to stack</td></tr>
      <tr><td class="mc-syntax">External link icons</td><td class="mc-desc">Domain / file-type icons attached via <code>data-link-icon</code></td></tr>
      <tr><td class="mc-syntax">Bibliography</td><td class="mc-desc">Appended to post whenever citations resolve</td></tr>
      <tr><td class="mc-syntax">TOC</td><td class="mc-desc">Generated from headings when the <em>Show Table of Contents</em> toggle is on</td></tr>
    </table>
  </details>

  <p class="mc-note">Full pipeline lives in <code>engine/markdown/</code>. If something renders unexpectedly, the preview button below the editor shows the live site CSS applied.</p>
</div>
</details>
"""


class PostAssetInline(admin.StackedInline):
    model = PostAsset
    extra = 1
    min_num = 0
    max_num = 50

    autocomplete_fields = ["asset"]
    ordering = ["order"]

    def get_queryset(self, request):
        # Every readonly display method reads obj.asset.* — pull it in one join
        # instead of a query per attached asset row.
        return super().get_queryset(request).select_related("asset")

    # Verbose names for better UX
    verbose_name = "Asset"
    verbose_name_plural = "Post Assets"

    fieldsets = [
        (
            None,
            {
                "fields": (
                    ("asset_preview", "asset"),
                    ("alias", "order", "markdown_ref_display"),
                ),
                "classes": [],
            },
        ),
        (
            "Custom Overrides (Optional)",
            {
                "fields": (
                    ("custom_alt_text", "asset_default_alt"),
                    ("custom_caption", "asset_default_caption"),
                ),
                "classes": ["collapse"],
                "description": "Override default asset metadata for this post only. The right column shows what will appear on the site if you leave the override blank.",
            },
        ),
    ]

    readonly_fields = [
        "asset_preview",
        "markdown_ref_display",
        "asset_default_alt",
        "asset_default_caption",
    ]

    @admin.display(description="Default alt (fallback)")
    def asset_default_alt(self, obj):
        if not obj or not obj.asset:
            return mark_safe(
                '<div class="mk-override-fallback">Pick an asset first.</div>'
            )
        default = obj.asset.alt_text or ""
        if not default:
            return mark_safe(
                '<div class="mk-override-fallback">'
                '<span class="mk-of-label">No default set</span>'
                "The underlying asset has no <code>alt_text</code>. "
                "Set one here or on the asset itself so screen readers have something to read."
                "</div>"
            )
        return format_html(
            '<div class="mk-override-fallback">'
            '<span class="mk-of-label">Default:</span>{}'
            "</div>",
            default,
        )

    @admin.display(description="Default caption (fallback)")
    def asset_default_caption(self, obj):
        if not obj or not obj.asset:
            return mark_safe(
                '<div class="mk-override-fallback">Pick an asset first.</div>'
            )
        default = obj.asset.caption or ""
        if not default:
            return mark_safe(
                '<div class="mk-override-fallback">'
                '<span class="mk-of-label">No default caption.</span>'
                "Leave blank for no caption, or enter one on the left."
                "</div>"
            )
        return format_html(
            '<div class="mk-override-fallback">'
            '<span class="mk-of-label">Default:</span>{}'
            "</div>",
            default,
        )

    def get_formset(self, request, obj=None, **kwargs):
        """Customize formset to improve UX."""
        formset = super().get_formset(request, obj, **kwargs)

        # Make alias not required
        if "alias" in formset.form.base_fields:
            formset.form.base_fields["alias"].required = False
            formset.form.base_fields[
                "alias"
            ].help_text = 'Optional: Short name for this post (e.g., "fig1")'
            formset.form.base_fields["alias"].widget.attrs.update(
                {"placeholder": "Leave blank to use global key"}
            )

        # Improve order field
        if "order" in formset.form.base_fields:
            formset.form.base_fields[
                "order"
            ].help_text = "Display order (lower numbers first)"

        # Improve custom fields help text
        if "custom_caption" in formset.form.base_fields:
            formset.form.base_fields[
                "custom_caption"
            ].help_text = "Override default caption for this post only"
            formset.form.base_fields["custom_caption"].widget.attrs.update(
                {"rows": 2, "placeholder": "Leave blank to use asset's default caption"}
            )

        if "custom_alt_text" in formset.form.base_fields:
            formset.form.base_fields[
                "custom_alt_text"
            ].help_text = "Override default alt text for this post only"
            formset.form.base_fields["custom_alt_text"].widget.attrs.update(
                {"placeholder": "Leave blank to use asset's default alt text"}
            )

        return formset

    @admin.display(description="Preview")
    def asset_preview(self, obj):
        """Show enhanced preview in inline (theme-aware)."""
        if not obj or not obj.asset or not obj.asset.file:
            return mark_safe(
                '<div class="mk-ap-card mk-ap-empty">'
                '<span class="mk-ap-icon">📎</span>'
                '<span class="mk-ap-label">No asset</span>'
                "</div>"
            )

        if obj.asset.asset_type == "image":
            return format_html(
                '<div class="mk-ap-img">'
                '<img src="{}" class="mk-ap-img-thumb" />'
                '<div class="mk-ap-dims">{} × {}</div>'
                "</div>",
                obj.asset.file.url,
                obj.asset.width or "?",
                obj.asset.height or "?",
            )

        icons_info = {
            "video": ("🎬", "Video"),
            "audio": ("🎵", "Audio"),
            "document": ("📄", "Document"),
            "archive": ("📦", "Archive"),
            "other": ("📎", "File"),
        }
        icon, label = icons_info.get(obj.asset.asset_type, ("📎", "File"))
        return format_html(
            '<div class="mk-ap-card mk-ap-type-{}">'
            '<span class="mk-ap-icon">{}</span>'
            '<span class="mk-ap-label">{}</span>'
            "</div>",
            obj.asset.asset_type,
            icon,
            label,
        )

    @admin.display(description="Reference")
    def markdown_ref_display(self, obj):
        """Show the markdown reference with a copy button (theme-aware).

        The copy button carries the text in ``data-clipboard-text``; the click
        handler is delegated in static/js/admin-post-aux.js (no inline onclick,
        which the site's nonce CSP would block).
        """
        if not (obj and obj.pk and obj.asset):
            return mark_safe('<code class="mk-inline-ref-code">-</code>')
        ref = f"@{obj.alias}" if obj.alias else f"@asset:{obj.asset.key}"
        return format_html(
            '<div class="mk-inline-ref">'
            '<code class="mk-inline-ref-code">{}</code>'
            '<button type="button" class="mk-inline-ref-copy mk-copy-btn" '
            'data-clipboard-text="{}">Copy</button>'
            "</div>",
            ref,
            ref,
        )


class IncomingLinksInline(admin.TabularInline):
    """Inline to show backlinks (incoming links) in Post admin."""

    model = InternalLink
    fk_name = "target_post"
    extra = 0
    max_num = 50
    can_delete = False
    verbose_name = "Backlink"
    verbose_name_plural = "Backlinks (Posts Linking to This Post)"

    fields = ("source_post_link", "link_count", "created_at")
    readonly_fields = ("source_post_link", "link_count", "created_at")

    def get_queryset(self, request):
        # source_post_link reads obj.source_post.title — avoid a query per row.
        return super().get_queryset(request).select_related("source_post")

    def has_add_permission(self, request, obj=None):
        """Backlinks are auto-generated, not manually added."""
        return False

    @admin.display(description="Source Post")
    def source_post_link(self, obj):
        """Display source post with link to admin."""
        if not obj or not obj.pk:
            return "—"
        return admin_change_link(obj.source_post, obj.source_post.title)


class PostSimilarityInline(admin.TabularInline):
    """Read-only inline showing computed similar posts with component breakdown."""

    model = PostSimilarity
    fk_name = "source_post"
    extra = 0
    max_num = 10
    can_delete = False
    verbose_name = "Similar Post"
    verbose_name_plural = "Similar Posts (auto-computed)"
    fields = ("target_post_link", "score", "components_display", "computed_at")
    readonly_fields = (
        "target_post_link",
        "score",
        "components_display",
        "computed_at",
    )
    ordering = ["-score"]

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        # Can't slice here — BaseInlineFormSet.__init__ applies .filter() on
        # the queryset afterward, which errors on sliced querysets. max_num
        # (set on the class) caps the rendered form count instead.
        return super().get_queryset(request).select_related("target_post")

    @admin.display(description="Target Post")
    def target_post_link(self, obj):
        if not obj or not obj.target_post_id:
            return "—"
        return admin_change_link(obj.target_post, obj.target_post.title)

    @admin.display(description="Components")
    def components_display(self, obj):
        if not obj or not obj.components:
            return "—"
        parts = [f"{k}={v}" for k, v in obj.components.items()]
        return format_html("<code>{}</code>", ", ".join(parts))


class PostRevisionInline(admin.TabularInline):
    model = PostRevision
    extra = 0
    can_delete = False
    max_num = 0
    ordering = ["-version"]
    verbose_name = "Revision"
    verbose_name_plural = "Revision History"

    fields = ("version_link", "created_by", "created_at", "size_display")
    readonly_fields = ("version_link", "created_by", "created_at", "size_display")

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        # Defer the (potentially large) markdown body and compute its length in
        # the database instead. size_display previously called
        # len(obj.content_markdown), which loaded the full body of every
        # historical revision on each change-form open.
        from django.db.models.functions import Length

        return (
            super()
            .get_queryset(request)
            .defer("content_markdown")
            .annotate(_md_len=Length("content_markdown"))
        )

    @admin.display(description="Version")
    def version_link(self, obj):
        if not obj or not obj.pk:
            return "-"
        diff_url = reverse(
            "admin:engine_post_revision_diff", args=[obj.post_id, obj.pk]
        )
        return format_html('<a href="{}">v{}</a>', diff_url, obj.version)

    @admin.display(description="Size")
    def size_display(self, obj):
        if not obj or not obj.pk:
            return "-"
        size = getattr(obj, "_md_len", None)
        if size is None:
            size = len(obj.content_markdown)
        if size < 1024:
            return f"{size} B"
        return f"{size / 1024:.1f} KB"


class PostCitationInline(admin.TabularInline):
    model = PostCitation
    extra = 0
    fields = ("source_display", "position", "annotation")
    readonly_fields = ("source_display", "position")
    ordering = ["position"]
    verbose_name = "Cited Source"
    verbose_name_plural = "Cited Sources"

    def get_queryset(self, request):
        # source_display reads obj.source.* — avoid a query per citation row.
        return super().get_queryset(request).select_related("source")

    @admin.display(description="Source")
    def source_display(self, obj):
        if obj.pk and obj.source:
            return f"{obj.source.citation_key}: {obj.source.title[:60]}"
        return "-"

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        # Citations are auto-managed from content — don't allow manual deletes
        return False

    def has_change_permission(self, request, obj=None):
        return False


# --------------------------
# Post admin
# --------------------------
@admin.register(Post)
class PostAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    inlines = [
        PostAssetInline,
        PostCitationInline,
        IncomingLinksInline,
        PostSimilarityInline,
        PostRevisionInline,
    ]
    save_on_top = True
    date_hierarchy = "published_at"

    class Media:
        js = (
            "js/dist/admin-post-editor.js",
            "js/admin-post-aux.js",
            "js/admin-clipboard.js",
        )
        css = {"all": ("css/admin-common.css", "css/admin-post.css")}

    list_display = (
        "post_title_with_status",
        "author",
        "status_badge",
        "completion_status_badge",
        "visibility_badge",
        "featured_pinned_indicators",
        "show_toc",
        "published_at",
        "stats_compact",
    )

    list_filter = (
        "status",
        "completion_status",
        "visibility",
        "is_featured",
        "is_pinned",
        "show_toc",
        "is_deleted",
        "published_at",
        "created_at",
        "updated_at",
        "categories",
        "tags",
        "series",
        "author",
    )

    # content_markdown is intentionally excluded: admin search does an
    # unindexed ILIKE '%term%' over the full body (the search_vector GIN index
    # can't serve it), which is slow at scale. Body text is searchable through
    # the site's full-text search; these fields identify a post for editing.
    search_fields = ("title", "subtitle", "description", "slug")
    ordering = ("-is_pinned", "pin_order", "-published_at", "-created_at")
    list_select_related = ("author", "series")

    # Autocomplete for every editable relation. (published_by / last_edited_by
    # are readonly audit fields, so they aren't listed here — the autocomplete
    # widget would never render for them. filter_horizontal was also removed:
    # when a field is in autocomplete_fields, Django uses the autocomplete
    # widget and ignores filter_horizontal, so it was dead configuration.)
    autocomplete_fields = (
        "author",
        "co_authors",
        "series",
        "categories",
        "tags",
    )

    # Fields excluded from the form entirely — internal caches and
    # derived columns that the Celery pipeline / DB triggers manage.
    exclude = (
        "content_html_cached",
        "table_of_contents",
        "extras",
        "search_vector",
    )

    readonly_fields = (
        # Content aids
        "markdown_cheatsheet",
        "asset_markdown_reference_helper",
        "cite_picker_controls",
        "preview_controls",
        # Derived metrics
        "word_count",
        "reading_time_minutes",
        "view_count",
        "comment_count",
        "like_count",
        # Audit
        "version",
        "published_by",
        "last_edited_by",
        "created_at",
        "updated_at",
        "deleted_at",
    )

    actions = (
        "publish_selected",
        "unpublish_selected",
        "feature_selected",
        "unfeature_selected",
        "rebuild_backlinks_for_selected",
        "attach_referenced_assets",
        "regenerate_html_cache",
        "soft_delete_selected",
        "restore_selected",
        "export_posts_csv",
    )

    # Slug from title is handy for editors
    prepopulated_fields = {"slug": ("title",)}

    # Facet counts are opt-in (append ?_facets to the URL). Computing them on
    # every changelist load ran a COUNT per choice across 14 filters (incl. the
    # categories/tags/series/author M2M-FK filters) — ~75 queries per load.
    show_facets = admin.ShowFacets.ALLOW

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        from django import forms as dj_forms
        from django.contrib.admin.widgets import AdminTextareaWidget

        # Make text fields full-width with better editing experience
        if db_field.name == "content_markdown":
            import json as _json

            # Resolve admin URLs once and stamp them onto the widget so the
            # CM6 bootstrap doesn't need to hardcode them.
            kwargs["widget"] = AdminTextareaWidget(
                attrs={
                    "rows": 30,
                    "cols": 120,
                    "style": "width: 100%; font-family: monospace; font-size: 16px;",
                    "data-cm-citations-url": reverse(
                        "admin:engine_post_autocomplete_citations"
                    ),
                    "data-cm-assets-url": reverse(
                        "admin:engine_post_autocomplete_assets"
                    ),
                    "data-cm-lint-url": reverse("admin:engine_post_lint_content"),
                    "data-cm-post-id": str(
                        request.resolver_match.kwargs.get("object_id", "")
                    )
                    if getattr(request, "resolver_match", None)
                    else "",
                    "data-cm-fence-snippets": _json.dumps(EDITOR_FENCE_SNIPPETS),
                    "data-cm-inline-classes": _json.dumps(EDITOR_INLINE_CLASSES),
                }
            )
            formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
            formfield.help_text = (
                "Pandoc-flavoured Markdown. See the reference panel above for "
                "admonitions, asset (<code>@asset:key</code>), citation "
                "(<code>[@key]</code>), footnote, and math syntax."
            )
            return formfield
        elif db_field.name == "description":
            kwargs["widget"] = AdminTextareaWidget(
                attrs={
                    "rows": 4,
                    "cols": 120,
                    "style": "width: 100%; font-size: 14px;",
                }
            )
            return super().formfield_for_dbfield(db_field, request, **kwargs)
        elif db_field.name == "abstract":
            kwargs["widget"] = AdminTextareaWidget(
                attrs={
                    "rows": 8,
                    "cols": 120,
                    "style": "width: 100%; font-family: monospace; font-size: 14px;",
                }
            )
            return super().formfield_for_dbfield(db_field, request, **kwargs)
        elif db_field.name == "citation_style":
            # Present curated CSL styles as a dropdown without changing the
            # underlying CharField, so unusual styles can still be set via the
            # ORM or a data migration if needed.
            return dj_forms.ChoiceField(
                choices=CITATION_STYLE_CHOICES,
                required=False,
                label=db_field.verbose_name.title(),
                help_text=mark_safe(
                    "Override the site-wide citation style for this post. "
                    "Leave as default unless the post specifically requires a "
                    "different style." + CITATION_STYLE_HELP_HTML
                ),
            )
        elif db_field.name == "certainty":
            formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
            formfield.help_text = (
                "How confident are you in the claims? 1 = highly uncertain / "
                "speculative, 10 = confident / well-evidenced."
            )
            return formfield
        elif db_field.name == "importance":
            formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
            formfield.help_text = (
                "How important is this post to the archive? 1 = trivial / "
                "ephemeral, 10 = core / canonical."
            )
            return formfield
        elif db_field.name == "completion_status":
            formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
            formfield.help_text = (
                "Editorial state shown in page metadata: "
                "<strong>Notes</strong> = raw thoughts, "
                "<strong>Draft</strong> = early pass, "
                "<strong>In Progress</strong> = actively revising, "
                "<strong>Finished</strong> = complete, "
                "<strong>Abandoned</strong> = shelved."
            )
            return formfield
        elif db_field.name == "meta_description":
            formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
            formfield.help_text = (
                "Override the meta description in <code>&lt;head&gt;</code> and "
                "on social cards. If blank, the <em>description</em> field above "
                "is used."
            )
            return formfield
        elif db_field.name == "hero_image_url":
            formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
            formfield.help_text = (
                "Primary featured image for cards / hero banner. If blank, the "
                "first image attached to this post is used; if there are no "
                "attached images, the site's default OG image is used."
            )
            return formfield
        elif db_field.name == "og_image_url":
            formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
            formfield.help_text = (
                "Open Graph override — only set this if you want a different "
                "image for social sharing than the hero image. Leave blank to "
                "reuse <em>hero_image_url</em>."
            )
            return formfield
        elif db_field.name == "canonical_url":
            formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
            formfield.help_text = (
                "For syndicated / cross-posted content, point here at the "
                "authoritative URL. Blank means this post is the canonical."
            )
            return formfield
        elif db_field.name == "rating":
            formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
            formfield.help_text = (
                "Optional author self-rating (0.00–9.99). Purely editorial; not "
                "shown to readers unless a template surfaces it."
            )
            return formfield
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def get_urls(self):
        custom_urls = [
            path(
                "<int:post_id>/revision/<int:revision_id>/diff/",
                self.admin_site.admin_view(self.revision_diff_view),
                name="engine_post_revision_diff",
            ),
            path(
                "<int:post_id>/revision/<int:revision_id>/restore/",
                self.admin_site.admin_view(self.revision_restore_view),
                name="engine_post_revision_restore",
            ),
            path(
                "preview-markdown/",
                self.admin_site.admin_view(self.preview_markdown_view),
                name="engine_post_preview_markdown",
            ),
            path(
                "autocomplete-citations/",
                self.admin_site.admin_view(self.autocomplete_citations_view),
                name="engine_post_autocomplete_citations",
            ),
            path(
                "autocomplete-assets/",
                self.admin_site.admin_view(self.autocomplete_assets_view),
                name="engine_post_autocomplete_assets",
            ),
            path(
                "lint-content/",
                self.admin_site.admin_view(self.lint_content_view),
                name="engine_post_lint_content",
            ),
        ]
        return custom_urls + super().get_urls()

    # ------------------------------------------------------------------
    # CM6 editor support endpoints
    # ------------------------------------------------------------------

    @staticmethod
    def _author_label(authors):
        """Return 'Smith' or 'Smith & Jones' or 'Smith et al.' from CSL names."""
        if not authors:
            return ""
        families = [a.get("family") or a.get("literal") or "" for a in authors]
        families = [f for f in families if f]
        if not families:
            return ""
        if len(families) == 1:
            return families[0]
        if len(families) == 2:
            return f"{families[0]} & {families[1]}"
        return f"{families[0]} et al."

    @staticmethod
    def _issued_year(issued_date):
        """Pull the year out of a CSL ``issued_date`` dict, or ''."""
        if not issued_date:
            return ""
        parts = issued_date.get("date-parts") or []
        if parts and parts[0]:
            return str(parts[0][0])
        return ""

    def autocomplete_citations_view(self, request):
        """Return top Source matches for the citation autocomplete."""
        from django.db.models import Q
        from django.http import JsonResponse

        from engine.models import Source

        if not (request.user.is_staff or request.user.is_superuser):
            return JsonResponse({"results": []}, status=403)

        q = (request.GET.get("q") or "").strip()
        qs = Source.objects.all()
        if q:
            qs = qs.filter(
                Q(citation_key__istartswith=q)
                | Q(citation_key__icontains=q)
                | Q(title__icontains=q)
            )

        qs = qs.order_by("citation_key")[:20]
        results = []
        for s in qs:
            results.append(
                {
                    "key": s.citation_key,
                    "title": (s.title or "")[:140],
                    "author": self._author_label(s.authors or []),
                    "year": self._issued_year(s.issued_date),
                }
            )
        return JsonResponse({"results": results})

    def autocomplete_assets_view(self, request):
        """Return asset matches, post-scoped aliases first then global keys.

        Query params: ``q`` (prefix filter), ``post_id`` (optional; scopes
        alias lookup to the post's attached PostAssets).
        """
        from django.db.models import Q
        from django.http import JsonResponse

        from engine.models import Asset, PostAsset

        if not (request.user.is_staff or request.user.is_superuser):
            return JsonResponse({"results": []}, status=403)

        q = (request.GET.get("q") or "").strip()
        post_id = request.GET.get("post_id") or ""

        results = []
        seen = set()

        # Post-local aliases first — these are what authors typically want.
        if post_id:
            try:
                pa_qs = PostAsset.objects.filter(post_id=int(post_id)).select_related(
                    "asset"
                )
                if q:
                    pa_qs = pa_qs.filter(
                        Q(alias__icontains=q)
                        | Q(asset__key__icontains=q)
                        | Q(asset__title__icontains=q)
                    )
                for pa in pa_qs.order_by("order")[:20]:
                    if not pa.alias or not pa.asset:
                        continue
                    ref_key = pa.alias
                    if ref_key in seen:
                        continue
                    seen.add(ref_key)
                    results.append(
                        {
                            "key": ref_key,
                            "global": False,
                            "type": pa.asset.asset_type,
                            "title": (pa.asset.title or "")[:140],
                        }
                    )
            except ValueError, TypeError:
                pass

        # Then global asset keys.
        asset_qs = Asset.objects.filter(is_deleted=False, status="ready")
        if q:
            asset_qs = asset_qs.filter(Q(key__icontains=q) | Q(title__icontains=q))
        for a in asset_qs.order_by("key")[: 20 - len(results)]:
            if a.key in seen:
                continue
            seen.add(a.key)
            results.append(
                {
                    "key": a.key,
                    "global": True,
                    "type": a.asset_type,
                    "title": (a.title or "")[:140],
                }
            )

        return JsonResponse({"results": results})

    def lint_content_view(self, request):
        """Return CM6-compatible diagnostics for the submitted content.

        Diagnostics carry absolute character offsets (``from`` / ``to``)
        into the source text plus severity + message, matching the shape
        of ``@codemirror/lint`` ``Diagnostic``.
        """
        from django.http import JsonResponse

        from engine.models import Asset, Source

        if request.method != "POST":
            return JsonResponse({"diagnostics": []}, status=405)
        if not (request.user.is_staff or request.user.is_superuser):
            return JsonResponse({"diagnostics": []}, status=403)

        content = request.POST.get("content", "")
        post_id = request.POST.get("post_id") or ""

        post = None
        if post_id:
            try:
                post = Post.all_objects.prefetch_related("post_assets__asset").get(
                    pk=int(post_id)
                )
            except ValueError, Post.DoesNotExist:
                pass

        diagnostics = []

        # Asset references: find every @asset:key / @alias inside a markdown
        # link/image target, then flag any that don't resolve.
        if "@" in content:
            post_assets = (
                list(post.post_assets.select_related("asset").all()) if post else []
            )
            aliases = {pa.alias for pa in post_assets if pa.alias}
            post_keys = {pa.asset.key for pa in post_assets if pa.asset}

            candidate_keys = set()
            candidate_globals = set()
            for m in _ASSET_REF_RE.finditer(content):
                key = m.group(2)
                if m.group(1) == "asset:":
                    candidate_globals.add(key)
                else:
                    candidate_keys.add(key)
            all_candidates = candidate_keys | candidate_globals
            known_globals = (
                set(
                    Asset.objects.filter(
                        key__in=all_candidates, is_deleted=False, status="ready"
                    ).values_list("key", flat=True)
                )
                if all_candidates
                else set()
            )

            for m in _ASSET_REF_RE.finditer(content):
                is_global = m.group(1) == "asset:"
                key = m.group(2)
                if is_global:
                    if key in post_keys or key in known_globals:
                        continue
                    label = f"@asset:{key}"
                else:
                    if key in aliases or key in post_keys or key in known_globals:
                        continue
                    label = f"@{key}"
                # Position the diagnostic on just the @...key span, not the
                # whole image syntax, so the underline lines up with the
                # broken reference.
                frag_start = m.start(1) - 1 if is_global else m.start(2) - 1
                frag_end = m.end(2)
                diagnostics.append(
                    {
                        "from": frag_start,
                        "to": frag_end,
                        "severity": "warning",
                        "message": f"Unresolved asset reference: {label}",
                    }
                )

        # Citations — locate each @key with its source position, then
        # flag anything not present in the Source library.
        if "@" in content:
            stripped_ranges = []  # positions to skip (code + asset refs)
            for pat in (r"```[\s\S]*?```", r"~~~[\s\S]*?~~~", r"`[^`\n]+`"):
                for m in re.finditer(pat, content):
                    stripped_ranges.append((m.start(), m.end()))
            for m in _ASSET_REF_RE.finditer(content):
                stripped_ranges.append((m.start(), m.end()))

            def _in_stripped(pos):
                return any(a <= pos < b for a, b in stripped_ranges)

            found = []  # list of (key, from_offset, to_offset)

            # Bracketed citations: walk each @key occurrence inside the
            # bracket span so multi-cite and locator forms both work.
            for m in re.finditer(r"\[(-?@[^\]]+)\]", content):
                if _in_stripped(m.start()):
                    continue
                base = m.start(1)
                for km in re.finditer(
                    r"-?@([a-zA-Z0-9][\w:#$%&\-+?<>~/]*)",
                    m.group(1),
                ):
                    key = km.group(1).rstrip(".")
                    key_start = base + km.start(1)
                    # Include the leading @ so the underline covers the sigil.
                    found.append((key, key_start - 1, key_start + len(key)))

            # Narrative citations: @key not preceded by another word / [ / @.
            for m in re.finditer(
                r"(?<![@\[\\\w])@([a-zA-Z0-9][\w:#$%&\-+?<>~/]*[a-zA-Z0-9]|[a-zA-Z0-9])",
                content,
            ):
                if _in_stripped(m.start()):
                    continue
                key = m.group(1).rstrip(".")
                found.append((key, m.start(), m.start(1) + len(key)))

            if found:
                keys_seen = {k for k, _, _ in found}
                known = set(
                    Source.objects.filter(citation_key__in=keys_seen).values_list(
                        "citation_key", flat=True
                    )
                )
                for key, s, e in found:
                    if key in known:
                        continue
                    diagnostics.append(
                        {
                            "from": s,
                            "to": e,
                            "severity": "warning",
                            "message": f"Unknown citation key: @{key}",
                        }
                    )

        # Internal links: /posts/<slug>/
        link_pattern = re.compile(r"\]\(/posts/([a-z0-9][a-z0-9\-_]*)/?\)")
        slug_matches = list(link_pattern.finditer(content))
        if slug_matches:
            slugs = {m.group(1) for m in slug_matches}
            known_slugs = set(
                Post.all_objects.filter(slug__in=slugs).values_list("slug", flat=True)
            )
            for m in slug_matches:
                slug = m.group(1)
                if slug in known_slugs:
                    continue
                diagnostics.append(
                    {
                        "from": m.start(1) - len("/posts/"),
                        "to": m.end(1) + 1,
                        "severity": "warning",
                        "message": f"Internal link to unknown slug: /posts/{slug}/",
                    }
                )

        # Unclosed admonition fences — flag the final unclosed opener.
        fence_matches = list(re.finditer(r"^:::+.*$", content, flags=re.MULTILINE))
        if len(fence_matches) % 2 == 1 and fence_matches:
            last = fence_matches[-1]
            diagnostics.append(
                {
                    "from": last.start(),
                    "to": last.end(),
                    "severity": "warning",
                    "message": "Unclosed ::: fence — missing matching ::: below.",
                }
            )

        return JsonResponse({"diagnostics": diagnostics})

    # Site CSS files loaded inside the preview iframe. Matches the set
    # included by templates/base.html so rendered posts look close to the
    # real site within the admin modal.
    _PREVIEW_CSS_FILES = (
        "css/dist/base.css",
        "css/dist/colors.css",
        "css/dist/link-icons.css",
        "css/dist/image-focus.css",
        "css/dist/bibliography.css",
    )

    def preview_markdown_view(self, request):
        """Render markdown through the full pipeline for admin preview.

        Accepts POST with ``content`` (markdown text) and optional
        ``post_id`` so post-scoped alias resolution works for drafts that
        haven't been saved yet. Returns JSON ``{ok, html, lint}`` where
        ``html`` is a complete document (HTML + site CSS links) suitable
        for iframe ``srcdoc`` and ``lint`` is a list of warning strings.
        """
        from django.http import JsonResponse
        from django.templatetags.static import static

        from engine.markdown.renderer import render_markdown

        if request.method != "POST":
            return JsonResponse({"ok": False, "error": "POST required"}, status=405)
        if not (request.user.is_staff or request.user.is_superuser):
            return JsonResponse({"ok": False, "error": "forbidden"}, status=403)

        content = request.POST.get("content", "")
        post_id = request.POST.get("post_id")

        context = {}
        post = None
        if post_id:
            try:
                post = Post.all_objects.prefetch_related("post_assets__asset").get(
                    pk=int(post_id)
                )
                context["post"] = post
            except ValueError, Post.DoesNotExist:
                pass

        lint_items = []
        post_assets = (
            list(post.post_assets.select_related("asset").all()) if post else []
        )

        orphans = self._find_orphan_asset_refs(content, post_assets)
        if orphans:
            lint_items.append("Unresolved asset references: " + ", ".join(orphans))
        missing_cites = self._find_unresolved_citation_keys(content)
        if missing_cites:
            lint_items.append(
                "Unknown citation keys: " + ", ".join(f"@{k}" for k in missing_cites)
            )
        broken_links = self._find_broken_internal_links(content)
        if broken_links:
            lint_items.append(
                "Broken internal links: "
                + ", ".join(f"/posts/{s}/" for s in broken_links)
            )
        if self._find_unmatched_admonitions(content):
            lint_items.append(
                "Odd number of ::: fences — check for an unclosed admonition."
            )

        try:
            rendered = render_markdown(content, context=context)
        except Exception as exc:
            return JsonResponse(
                {"ok": False, "error": f"Render failed: {exc}", "lint": lint_items},
                status=500,
            )

        css_links = "\n".join(
            f'<link rel="stylesheet" href="{static(path)}">'
            for path in self._PREVIEW_CSS_FILES
        )
        iframe_doc = (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"{css_links}"
            "<style>body{margin:0;padding:24px 28px;}"
            ".admin-preview-banner{font:12px/1.4 system-ui,sans-serif;"
            "color:#555;background:#f4f4f4;border:1px solid #ddd;"
            "padding:6px 10px;border-radius:4px;margin-bottom:14px;}"
            "</style></head>"
            "<body>"
            "<div class='admin-preview-banner'>"
            "Admin preview — site CSS is loaded; MathJax and client-side "
            "enhancements are not."
            "</div>"
            '<div id="markdownBody" class="markdownBody">'
            f"{rendered}"
            "</div></body></html>"
        )

        return JsonResponse({"ok": True, "html": iframe_doc, "lint": lint_items})

    def revision_diff_view(self, request, post_id, revision_id):
        post = get_object_or_404(Post.all_objects, pk=post_id)
        if not self.has_view_permission(request, post):
            raise PermissionDenied
        revision = get_object_or_404(PostRevision, pk=revision_id, post=post)

        # Find the previous revision for diffing
        prev_revision = (
            PostRevision.objects.filter(post=post, version__lt=revision.version)
            .order_by("-version")
            .first()
        )

        left_label = f"v{prev_revision.version}" if prev_revision else "(empty)"
        right_label = f"v{revision.version}"
        left_lines = (
            prev_revision.content_markdown if prev_revision else ""
        ).splitlines(keepends=True)
        right_lines = revision.content_markdown.splitlines(keepends=True)

        diff_html = difflib.HtmlDiff(wrapcolumn=80).make_table(
            left_lines,
            right_lines,
            fromdesc=left_label,
            todesc=right_label,
            context=True,
            numlines=5,
        )

        # All revisions for this post for the sidebar
        all_revisions = PostRevision.objects.filter(post=post).order_by("-version")

        restore_url = reverse(
            "admin:engine_post_revision_restore",
            args=[post_id, revision_id],
        )

        context = {
            **self.admin_site.each_context(request),
            "title": f"Revision diff: {post.title}",
            "post": post,
            "revision": revision,
            "prev_revision": prev_revision,
            "diff_html": mark_safe(diff_html),
            "all_revisions": all_revisions,
            "restore_url": restore_url,
            "opts": self.model._meta,
        }
        return TemplateResponse(
            request, "admin/engine/post/revision_diff.html", context
        )

    def revision_restore_view(self, request, post_id, revision_id):
        if request.method != "POST":
            raise Http404
        post = get_object_or_404(Post.all_objects, pk=post_id)
        # Restoring a revision overwrites the post body — require change rights
        # on this object (admin_view only guarantees is_staff).
        if not self.has_change_permission(request, post):
            raise PermissionDenied
        revision = get_object_or_404(PostRevision, pk=revision_id, post=post)

        post.content_markdown = revision.content_markdown
        post.last_edited_by = request.user
        post.save()

        messages.success(
            request,
            f'Restored "{post.title}" to revision v{revision.version}.',
        )
        return HttpResponseRedirect(reverse("admin:engine_post_change", args=[post_id]))

    fieldsets = (
        (
            "Identity",
            {
                "fields": (
                    ("title", "slug"),
                    ("subtitle", "language"),
                    ("author", "co_authors"),
                    ("description",),
                ),
                "description": (
                    "Title, URL slug, language, and a short description used "
                    "as the teaser on cards and as the meta-description fallback."
                ),
            },
        ),
        (
            "Content",
            {
                "fields": (
                    ("markdown_cheatsheet",),
                    ("content_markdown",),
                    ("preview_controls",),
                    ("cite_picker_controls",),
                    ("asset_markdown_reference_helper",),
                    ("abstract",),
                ),
                "description": (
                    "Write your post content in Pandoc-flavoured Markdown. "
                    "The render pipeline processes it on save; the preview button "
                    "renders it live with site CSS."
                ),
            },
        ),
        (
            "Publishing",
            {
                "fields": (
                    ("status", "completion_status"),
                    ("visibility",),
                    ("published_at", "expire_at"),
                    ("is_featured", "is_pinned", "pin_order"),
                ),
                "description": (
                    "Lifecycle state, who can see the post, and scheduled "
                    "go-live / expiry times."
                ),
            },
        ),
        (
            "Taxonomy & Relations",
            {
                "fields": (
                    ("series", "series_order"),
                    ("categories", "tags"),
                ),
                "classes": ["collapse"],
                "description": "Categorize this post. Similar posts are computed automatically — see the PostSimilarity inline below.",
            },
        ),
        (
            "Rendering & Metadata",
            {
                "fields": (
                    ("show_toc", "first_line_caps"),
                    ("citation_style",),
                    ("certainty", "importance"),
                    ("allow_comments", "rating"),
                ),
                "classes": ["collapse"],
                "description": (
                    "Per-post rendering toggles, editorial ratings, and "
                    "comment allowance."
                ),
            },
        ),
        (
            "SEO & Social Sharing",
            {
                "fields": (
                    ("meta_description",),
                    ("hero_image_url",),
                    ("og_image_url",),
                    ("canonical_url",),
                    ("noindex",),
                ),
                "classes": ["collapse"],
                "description": (
                    "Override auto-generated SEO / OG metadata. Fallback "
                    "chain for images: og_image_url → hero_image_url → first "
                    "in-content image → site default."
                ),
            },
        ),
        (
            "Metrics",
            {
                "fields": (
                    ("word_count", "reading_time_minutes"),
                    ("view_count", "comment_count", "like_count"),
                ),
                "classes": ["collapse"],
                "description": "Read-only counters. Updated by the render pipeline and views.",
            },
        ),
        (
            "Audit",
            {
                "fields": (
                    ("version",),
                    ("published_by", "last_edited_by"),
                    ("created_at", "updated_at"),
                ),
                "classes": ["collapse"],
                "description": (
                    "Auto-managed provenance. Version bumps when "
                    "content_markdown changes; published_by is stamped on the "
                    "first publish; last_edited_by updates on every admin save."
                ),
            },
        ),
        (
            "System",
            {
                "fields": (("is_deleted", "deleted_at"),),
                "classes": ["collapse"],
                "description": "Soft-delete state.",
            },
        ),
    )

    @admin.display(description="Post", ordering="title")
    def post_title_with_status(self, obj):
        """Display post title with visual indicators."""
        # Status emoji
        status_icons = {
            "draft": "📝",
            "scheduled": "⏰",
            "published": "✅",
            "archived": "📦",
        }
        icon = status_icons.get(obj.status, "📄")

        # Title with bold if featured
        title_style = "font-weight: 600;" if obj.is_featured else ""

        return format_html(
            '<div style="display: flex; align-items: center; gap: 8px;">'
            '<span style="font-size: 18px;">{}</span>'
            '<span style="{}">{}</span>'
            "</div>",
            icon,
            title_style,
            obj.title,
        )

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        """Display status with color."""
        colors = {
            "draft": "#fff3cd",
            "scheduled": "#cfe2ff",
            "published": "#d4edda",
            "archived": "#e2e3e5",
        }
        text_colors = {
            "draft": "#856404",
            "scheduled": "#084298",
            "published": "#155724",
            "archived": "#383d41",
        }
        return format_html(
            '<span style="background: {}; color: {}; padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: 500;">{}</span>',
            colors.get(obj.status, "#e2e3e5"),
            text_colors.get(obj.status, "#383d41"),
            obj.get_status_display(),
        )

    @admin.display(description="Completion", ordering="completion_status")
    def completion_status_badge(self, obj):
        """Display completion status with color."""
        colors = {
            "finished": "#d4edda",
            "abandoned": "#f8d7da",
            "notes": "#d1ecf1",
            "draft": "#fff3cd",
            "in_progress": "#cfe2ff",
        }
        text_colors = {
            "finished": "#155724",
            "abandoned": "#721c24",
            "notes": "#0c5460",
            "draft": "#856404",
            "in_progress": "#084298",
        }
        return format_html(
            '<span style="background: {}; color: {}; padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: 500;">{}</span>',
            colors.get(obj.completion_status, "#e2e3e5"),
            text_colors.get(obj.completion_status, "#383d41"),
            obj.get_completion_status_display(),
        )

    @admin.display(description="Visibility", ordering="visibility")
    def visibility_badge(self, obj):
        """Display visibility with color."""
        colors = {
            "public": "#d4edda",
            "unlisted": "#fff3cd",
            "private": "#f8d7da",
        }
        text_colors = {
            "public": "#155724",
            "unlisted": "#856404",
            "private": "#721c24",
        }
        icons = {
            "public": "🌐",
            "unlisted": "🔗",
            "private": "🔒",
        }
        return format_html(
            '<span style="background: {}; color: {}; padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: 500;">{} {}</span>',
            colors.get(obj.visibility, "#e2e3e5"),
            text_colors.get(obj.visibility, "#383d41"),
            icons.get(obj.visibility, ""),
            obj.get_visibility_display(),
        )

    @admin.display(description="Features")
    def featured_pinned_indicators(self, obj):
        """Show featured/pinned indicators."""
        badges = []
        if obj.is_featured:
            badges.append('<span class="mk-pill mk-pill-featured">⭐ FEATURED</span>')
        if obj.is_pinned:
            badges.append(
                f'<span class="mk-pill mk-pill-pin">📌 PIN {obj.pin_order}</span>'
            )
        if not badges:
            return mark_safe('<span class="mk-muted">—</span>')
        return mark_safe(" ".join(badges))

    @admin.display(description="Stats")
    def stats_compact(self, obj):
        """Display compact statistics."""
        return format_html(
            '<div class="mk-stats-compact">'
            "<div>👁️ {} | 💬 {} | ❤️ {}</div>"
            "<div>📖 {}min | {} words</div>"
            "</div>",
            obj.view_count,
            obj.comment_count,
            obj.like_count,
            obj.reading_time_minutes,
            obj.word_count,
        )

    @admin.display(description="Markdown reference")
    def markdown_cheatsheet(self, obj=None):
        """Collapsible cheatsheet of supported markdown syntax.

        Rendered above the content textarea so authors can discover
        admonitions, asset/citation syntax, and other custom features
        without leaving the change form.
        """
        return mark_safe(MARKDOWN_CHEATSHEET_HTML)

    @admin.display(description="Preview")
    def preview_controls(self, obj=None):
        """Render the 'Preview markdown' button + iframe modal skeleton.

        Posts the current textarea contents to
        ``engine_post_preview_markdown`` and injects the returned HTML
        document into an iframe so the production site CSS applies and
        there's no style bleed from the admin.
        """
        post_id = obj.pk if obj and obj.pk else ""
        preview_url = reverse("admin:engine_post_preview_markdown")
        return format_html(
            '<div class="markdown-preview-controls" '
            'data-preview-url="{}" data-post-id="{}">'
            "<button type='button' class='markdown-preview-btn'>"
            "🔍 Preview rendered markdown</button>"
            "<span class='markdown-preview-hint'>"
            "Opens in a modal with the live site's CSS loaded — no save required. "
            "MathJax isn't evaluated in the preview."
            "</span></div>"
            '<div id="markdown-preview-modal" class="markdown-preview-modal">'
            '<div class="mk-panel">'
            '<div class="mk-header">'
            "<strong>Markdown preview</strong>"
            "<button type='button' id='markdown-preview-close' class='mk-close' aria-label='Close'>✕</button>"
            "</div>"
            '<div id="markdown-preview-lint" class="mk-lint"></div>'
            '<iframe id="markdown-preview-iframe" class="mk-iframe" '
            'sandbox="allow-same-origin"></iframe>'
            "</div></div>",
            preview_url,
            post_id,
        )

    @admin.display(description="Insert citation")
    def cite_picker_controls(self, obj=None):
        """Render the citation picker button + modal (Phase 4.1).

        The CM6 bootstrap exposes its view via ``window.__atpPostEditorView``.
        Clicking a row inserts ``[@key]`` at the editor's current cursor.
        """
        citations_url = reverse("admin:engine_post_autocomplete_citations")
        return format_html(
            '<div class="mk-cite-controls" data-cite-url="{}">'
            "<button type='button' class='mk-cite-picker-btn'>"
            "📚 Browse &amp; insert citation</button>"
            "<span class='mk-cite-picker-hint'>"
            "Keyboard: <code>↑</code>/<code>↓</code> to navigate, "
            "<code>Enter</code> to insert, <code>Esc</code> to close."
            "</span></div>"
            '<div id="mk-cite-modal" class="mk-cite-modal">'
            '<div class="mk-panel">'
            '<div class="mk-header">'
            "<strong>Insert citation</strong>"
            "<button type='button' id='mk-cite-close' class='mk-close' aria-label='Close'>✕</button>"
            "</div>"
            '<div class="mk-search-row">'
            '<input id="mk-cite-search" type="search" '
            'placeholder="Search by key, title, or author…" autocomplete="off">'
            "</div>"
            '<div id="mk-cite-results" class="mk-results"></div>'
            '<div class="mk-cite-footer">'
            "Inserts <code>[@key]</code> at the current cursor position in the markdown editor."
            "</div></div></div>",
            citations_url,
        )

    @admin.display(description="Asset Markdown References")
    def asset_markdown_reference_helper(self, obj=None):
        """Display assets attached to this post with their markdown references for quick copying."""
        if not obj or not obj.pk:
            return mark_safe(
                '<div class="mk-asset-info">'
                'ℹ️ Asset references will appear here after you save the post and attach assets in the "Post Assets" section below. '
                "Use <code>@asset:key</code> for global references or <code>@alias</code> for post-local aliases inside your markdown."
                "</div>"
            )

        post_assets = obj.post_assets.select_related("asset").order_by("order")
        orphan_html = self._orphan_asset_ref_warning(obj, post_assets)

        if not post_assets.exists():
            no_assets_html = (
                '<div class="mk-asset-none">'
                '⚠️ No assets attached to this post yet. Add assets in the "Post Assets" section below, then save to see their markdown references here.'
                "</div>"
            )
            return mark_safe(orphan_html + no_assets_html)

        parts = []
        parts.append('<div class="mk-asset-list">')
        parts.append(
            format_html(
                '<div class="mk-asset-header">📎 Assets in this Post ({}) — Click to copy:</div>',
                post_assets.count(),
            )
        )
        parts.append('<div class="mk-asset-grid">')

        icons = {
            "image": "🖼️",
            "video": "🎬",
            "audio": "🎵",
            "document": "📄",
            "archive": "📦",
            "other": "📎",
        }

        for post_asset in post_assets:
            asset = post_asset.asset
            if post_asset.alias:
                ref = "@" + post_asset.alias
                ref_type = "Alias"
            else:
                ref = "@asset:" + asset.key
                ref_type = "Global"

            icon = icons.get(asset.asset_type, "📎")
            display_title = asset.title[:40] if len(asset.title) > 40 else asset.title
            order_badge_html = (
                format_html(
                    '<span class="mk-asset-order-badge">#{}</span>',
                    post_asset.order,
                )
                if post_asset.order
                else ""
            )

            parts.append(
                format_html(
                    '<div class="mk-asset-card" data-ref="{}">'
                    '<div class="mk-meta">{}{} {} • {}</div>'
                    '<div class="mk-title" title="{}">{}</div>'
                    "<code>{}</code>"
                    "</div>",
                    ref,
                    mark_safe(order_badge_html) if order_badge_html else "",
                    icon,
                    asset.asset_type.title(),
                    ref_type,
                    asset.title,
                    display_title,
                    ref,
                )
            )

        parts.append("</div></div>")
        parts.append(
            '<div class="mk-asset-tip">💡 <strong>Tip:</strong> Click any asset card above to copy its markdown reference.</div>'
        )
        # Click-to-copy on the cards (data-ref) is handled by delegation in
        # static/js/admin-post-aux.js — no inline <script> (nonce CSP).
        return mark_safe(orphan_html + "".join(parts))

    def _orphan_asset_ref_warning(self, obj, post_assets):
        """Render HTML listing asset references in content that don't resolve."""
        orphans = self._find_orphan_asset_refs(obj.content_markdown or "", post_assets)
        if not orphans:
            return ""

        chips = "".join(
            format_html('<span class="mk-orphan-chip">{}</span>', ref)
            for ref in orphans
        )
        return format_html(
            '<div class="mk-asset-orphan">'
            "⚠️ <strong>Unresolved asset references in content:</strong> {}"
            '<div class="mk-hint">'
            "Attach the matching asset below, fix the key/alias, or remove the reference."
            "</div>"
            "</div>",
            mark_safe(chips),
        )

    @staticmethod
    def _find_orphan_asset_refs(content, post_assets):
        """Return the sorted list of unresolved ``@asset:`` / ``@alias`` refs.

        Compares every reference against the PostAsset aliases attached to
        this post and the global Asset key set.
        """
        if not content or "@" not in content:
            return []

        from engine.models import Asset

        aliases = {pa.alias for pa in post_assets if pa.alias}
        global_keys = {pa.asset.key for pa in post_assets if pa.asset}

        orphans = []
        checked = set()

        for match in _ASSET_REF_RE.finditer(content):
            is_global = match.group(1) == "asset:"
            key = match.group(2)
            cache_key = (is_global, key)
            if cache_key in checked:
                continue
            checked.add(cache_key)

            if is_global:
                if key in global_keys:
                    continue
                if Asset.objects.filter(
                    key=key, is_deleted=False, status="ready"
                ).exists():
                    continue
                orphans.append(f"@asset:{key}")
            else:
                if key in aliases or key in global_keys:
                    continue
                if Asset.objects.filter(
                    key=key, is_deleted=False, status="ready"
                ).exists():
                    continue
                orphans.append(f"@{key}")

        return orphans

    @staticmethod
    def _find_unresolved_citation_keys(content):
        """Return the sorted list of citation keys not in the Source library.

        Matches Pandoc-style bracketed citations ``[@key]`` / ``[-@key]`` /
        ``[@a; @b]`` and bare narrative ``@key``. Code spans, fenced code,
        and asset-reference link targets are stripped first so they don't
        produce false positives (mirrors the production preprocessor
        ordering: asset_resolver runs before citation_escaper).
        """
        if not content or "@" not in content:
            return []

        from engine.models import Source

        # Strip fenced and inline code so citations inside examples don't flag.
        stripped = re.sub(r"```[\s\S]*?```", "", content)
        stripped = re.sub(r"~~~[\s\S]*?~~~", "", stripped)
        stripped = re.sub(r"`[^`\n]+`", "", stripped)
        # Strip markdown link/image targets that contain @ (asset references).
        stripped = _ASSET_REF_RE.sub("", stripped)

        # Keys end in an alphanumeric character — trailing `.` is sentence
        # punctuation, not part of the key.
        key_pat = r"[a-zA-Z0-9][\w:#$%&\-+?<>~/]*[a-zA-Z0-9]|[a-zA-Z0-9]"

        keys = set()
        # Bracketed: [@key] / [-@key] / [@k1; @k2, pp. 3]
        for match in re.finditer(r"\[(-?@[^\]]+)\]", stripped):
            for piece in match.group(1).split(";"):
                piece = piece.strip().lstrip("-").lstrip("@")
                head = piece.split(",", 1)[0].strip()
                m = re.match(r"([a-zA-Z0-9][\w:.#$%&\-+?<>~/]*?)\.?$", head)
                key = m.group(1) if m else ""
                if key:
                    keys.add(key)
        # Narrative: @key (not already inside brackets, not after a word char)
        for match in re.finditer(rf"(?<![@\[\\\w])@({key_pat})", stripped):
            keys.add(match.group(1))

        if not keys:
            return []

        known = set(
            Source.objects.filter(citation_key__in=keys).values_list(
                "citation_key", flat=True
            )
        )
        return sorted(keys - known)

    @staticmethod
    def _find_broken_internal_links(content, current_post_pk=None):
        """Return sorted list of ``/posts/<slug>/`` targets not matching a Post."""
        if not content:
            return []
        slugs = set(re.findall(r"\]\(/posts/([a-z0-9][a-z0-9\-_]*)/?\)", content))
        if not slugs:
            return []
        known = set(
            Post.all_objects.filter(slug__in=slugs).values_list("slug", flat=True)
        )
        return sorted(slugs - known)

    @staticmethod
    def _find_unmatched_admonitions(content):
        """Return diagnostic count of unmatched ``:::`` fenced divs.

        Pandoc fenced divs come in matched pairs: an opener like
        ``::: {.admonition-tip}`` and a bare ``:::`` closer. An odd total
        almost always means the author forgot to close a block.
        """
        if not content:
            return 0
        fences = re.findall(r"^:::+.*$", content, flags=re.MULTILINE)
        return len(fences) % 2

    def _collect_content_lint_messages(self, post):
        """Return a list of (level, message) tuples for save-time lint warnings."""
        messages_out = []
        content = post.content_markdown or ""
        if not content:
            return messages_out

        post_assets = (
            list(post.post_assets.select_related("asset").all()) if post.pk else []
        )

        orphans = self._find_orphan_asset_refs(content, post_assets)
        if orphans:
            messages_out.append(
                (
                    messages.WARNING,
                    "Unresolved asset reference(s): "
                    + ", ".join(orphans)
                    + ". Attach the asset or fix the key/alias.",
                )
            )

        missing_cites = self._find_unresolved_citation_keys(content)
        if missing_cites:
            messages_out.append(
                (
                    messages.WARNING,
                    "Unknown citation key(s) — will render as [??key]: "
                    + ", ".join(f"@{k}" for k in missing_cites)
                    + ". Add to the Source library or correct the key.",
                )
            )

        broken_links = self._find_broken_internal_links(content, post.pk)
        if broken_links:
            messages_out.append(
                (
                    messages.WARNING,
                    "Internal link(s) to unknown slugs: "
                    + ", ".join(f"/posts/{s}/" for s in broken_links)
                    + ".",
                )
            )

        if self._find_unmatched_admonitions(content):
            messages_out.append(
                (
                    messages.WARNING,
                    "Odd number of ::: fences detected — an admonition "
                    "or fenced div is likely unclosed.",
                )
            )

        return messages_out

    def save_model(self, request, obj, form, change):
        # Auto-stamp audit provenance so authors can't forget.
        obj.last_edited_by = request.user
        if obj.status == Post.Status.PUBLISHED and not obj.published_by:
            obj.published_by = request.user

        super().save_model(request, obj, form, change)
        for level, msg in self._collect_content_lint_messages(obj):
            self.message_user(request, msg, level=level)

    @admin.action(description="Publish selected posts")
    def publish_selected(self, request, queryset):
        """Publish selected posts (go-live time + publisher via Post.publish)."""
        count = 0
        for post in queryset:
            post.publish(by=request.user)
            count += 1
        self.message_user(request, f"Published {count} post(s).")

    @admin.action(description="Unpublish selected posts")
    def unpublish_selected(self, request, queryset):
        """Unpublish selected posts."""
        count = queryset.update(status="draft")
        self.message_user(request, f"Unpublished {count} post(s).")

    @admin.action(description="Feature selected posts")
    def feature_selected(self, request, queryset):
        """Mark selected posts as featured."""
        count = queryset.update(is_featured=True)
        self.message_user(request, f"Featured {count} post(s).")

    @admin.action(description="Unfeature selected posts")
    def unfeature_selected(self, request, queryset):
        """Remove featured status from selected posts."""
        count = queryset.update(is_featured=False)
        self.message_user(request, f"Unfeatured {count} post(s).")

    @admin.action(description="Rebuild backlinks for selected posts")
    def rebuild_backlinks_for_selected(self, request, queryset):
        """Rebuild internal links for selected posts by parsing their content."""
        from engine.links.extractor import update_post_links

        total_stats = {
            "posts_processed": 0,
            "links_created": 0,
            "links_updated": 0,
            "links_deleted": 0,
            "links_failed": 0,
        }

        for post in queryset:
            try:
                stats = update_post_links(post)
                total_stats["posts_processed"] += 1
                total_stats["links_created"] += stats["links_created"]
                total_stats["links_updated"] += stats["links_updated"]
                total_stats["links_deleted"] += stats["links_deleted"]
                total_stats["links_failed"] += stats["links_failed"]
            except Exception as e:
                self.message_user(
                    request,
                    f"Error processing '{post.title}': {str(e)}",
                    level=messages.ERROR,
                )

        # Show summary
        self.message_user(
            request,
            f"Processed {total_stats['posts_processed']} post(s): "
            f"{total_stats['links_created']} links created, "
            f"{total_stats['links_updated']} updated, "
            f"{total_stats['links_deleted']} deleted.",
            level=messages.SUCCESS,
        )

        if total_stats["links_failed"] > 0:
            self.message_user(
                request,
                f"Warning: {total_stats['links_failed']} link(s) failed to resolve.",
                level=messages.WARNING,
            )

    @admin.action(description="Regenerate HTML cache & table of contents")
    def regenerate_html_cache(self, request, queryset):
        """Re-render content and rebuild the cached HTML + TOC.

        ``Post.save()`` clears the TOC when content changes and the Celery
        pipeline eventually repopulates ``content_html_cached``. This action
        forces that work synchronously for the selected posts, which is
        useful after pipeline changes or a content/asset migration.
        """
        from engine.markdown.extensions.toc_extractor import extract_toc_from_html
        from engine.markdown.renderer import render_markdown

        count = 0
        failed = 0
        for post in queryset:
            try:
                context = {"post": post}
                html = render_markdown(post.content_markdown or "", context=context)
                post.content_html_cached = html
                try:
                    post.table_of_contents = extract_toc_from_html(html) or []
                except Exception:
                    # TOC extraction is best-effort; leave it empty on failure.
                    post.table_of_contents = []
                post.save(update_fields=["content_html_cached", "table_of_contents"])
                count += 1
            except Exception as exc:
                failed += 1
                self.message_user(
                    request,
                    f"Failed to re-render '{post.title}': {exc}",
                    level=messages.ERROR,
                )
        self.message_user(
            request,
            f"Regenerated HTML + TOC for {count} post(s)"
            + (f", {failed} failed." if failed else "."),
            level=messages.SUCCESS if count else messages.WARNING,
        )

    @admin.action(description="Attach @asset: references found in content")
    def attach_referenced_assets(self, request, queryset):
        """Scan each selected post's content for @asset:key / @alias refs
        and create PostAsset rows for any that resolve to real Assets but
        aren't yet attached."""
        from engine.models import Asset

        total_attached = 0
        total_posts = 0
        total_skipped = 0
        unresolved = set()

        for post in queryset:
            content = post.content_markdown or ""
            if not content or "@" not in content:
                continue

            existing_keys = {
                pa.asset.key
                for pa in post.post_assets.select_related("asset").all()
                if pa.asset
            }
            existing_aliases = {
                pa.alias
                for pa in post.post_assets.select_related("asset").all()
                if pa.alias
            }

            candidate_keys = set()
            for m in _ASSET_REF_RE.finditer(content):
                is_global = m.group(1) == "asset:"
                key = m.group(2)
                if is_global:
                    if key not in existing_keys:
                        candidate_keys.add(key)
                else:
                    if key in existing_aliases or key in existing_keys:
                        continue
                    candidate_keys.add(key)

            if not candidate_keys:
                continue

            # Resolve to real Assets in one query.
            found_assets = {
                a.key: a
                for a in Asset.objects.filter(
                    key__in=candidate_keys, is_deleted=False, status="ready"
                )
            }

            # Figure out a starting order offset so we don't collide.
            next_order = post.post_assets.order_by("-order").values_list(
                "order", flat=True
            )[:1]
            next_order = (next_order[0] if next_order else 0) + 1

            post_touched = False
            for key in candidate_keys:
                asset = found_assets.get(key)
                if not asset:
                    unresolved.add(key)
                    total_skipped += 1
                    continue
                PostAsset.objects.create(post=post, asset=asset, order=next_order)
                next_order += 1
                total_attached += 1
                post_touched = True

            if post_touched:
                total_posts += 1

        self.message_user(
            request,
            f"Attached {total_attached} asset(s) across {total_posts} post(s).",
            level=messages.SUCCESS if total_attached else messages.INFO,
        )
        if unresolved:
            self.message_user(
                request,
                "Unresolved keys (no matching ready Asset): "
                + ", ".join(sorted(unresolved)[:25])
                + ("…" if len(unresolved) > 25 else ""),
                level=messages.WARNING,
            )
        if total_skipped and not unresolved:
            self.message_user(
                request,
                f"Skipped {total_skipped} key(s) — likely aliases already set or missing assets.",
                level=messages.INFO,
            )

    @admin.action(description="Export selected posts as CSV")
    def export_posts_csv(self, request, queryset):
        """Export posts as CSV."""
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="posts_export.csv"'

        writer = csv.writer(response)
        writer.writerow(
            [
                "Title",
                "Slug",
                "Author",
                "Status",
                "Visibility",
                "Published",
                "Word Count",
                "Reading Time",
                "Views",
                "Comments",
                "Likes",
                "Featured",
                "Pinned",
                "Created",
                "Updated",
            ]
        )

        for post in queryset:
            writer.writerow(
                [
                    post.title,
                    post.slug,
                    post.author.username,
                    post.get_status_display(),
                    post.get_visibility_display(),
                    (
                        post.published_at.strftime("%Y-%m-%d %H:%M")
                        if post.published_at
                        else ""
                    ),
                    post.word_count,
                    post.reading_time_minutes,
                    post.view_count,
                    post.comment_count,
                    post.like_count,
                    "Yes" if post.is_featured else "No",
                    "Yes" if post.is_pinned else "No",
                    post.created_at.strftime("%Y-%m-%d %H:%M"),
                    post.updated_at.strftime("%Y-%m-%d %H:%M"),
                ]
            )

        return response


# --------------------------
# Internal Links (Backlinks)
# --------------------------
@admin.register(InternalLink)
class InternalLinkAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    """
    Read-only admin for viewing internal links between posts.

    These links are automatically generated when posts are saved by parsing
    markdown content. Manual creation/editing is disabled since these must
    stay in sync with actual post content.
    """

    list_display = (
        "link_display",
        "link_count",
        "link_type_badge",
        "created_at",
    )
    list_filter = (
        "created_at",
        "is_deleted",
    )
    search_fields = (
        "source_post__title",
        "source_post__slug",
        "target_post__title",
        "target_post__slug",
    )
    list_select_related = ("source_post", "target_post")
    readonly_fields = (
        "source_post",
        "target_post",
        "link_count",
        "created_at",
        "updated_at",
        "is_deleted",
        "deleted_at",
    )
    list_per_page = 100

    fieldsets = (
        (
            "Link Relationship",
            {
                "fields": (
                    ("source_post", "target_post"),
                    "link_count",
                ),
                "description": "Auto-generated from post content. Links are created when a post references another post's slug.",
            },
        ),
        (
            "Timestamps",
            {
                "fields": (("created_at", "updated_at"),),
                "classes": ["collapse"],
            },
        ),
        (
            "System",
            {
                "fields": (("is_deleted", "deleted_at"),),
                "classes": ["collapse"],
            },
        ),
    )

    @admin.display(description="Link", ordering="source_post__title")
    def link_display(self, obj):
        """Display the link relationship."""
        return format_html(
            "{} → {}",
            admin_change_link(obj.source_post, obj.source_post.title[:40]),
            admin_change_link(obj.target_post, obj.target_post.title[:40]),
        )

    @admin.display(description="Type")
    def link_type_badge(self, obj):
        """Display link direction."""
        return mark_safe(
            '<span style="background: #e7f3ff; color: #004085; padding: 4px 8px; '
            'border-radius: 4px; font-size: 10px; font-weight: 500;">Internal Link</span>'
        )


# --------------------------
# Post Revisions
# --------------------------
@admin.register(PostRevision)
class PostRevisionAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("post", "version", "created_by", "created_at", "size_display")
    list_filter = ("created_at",)
    list_select_related = ("post", "created_by")
    search_fields = ("post__title",)
    readonly_fields = (
        "post",
        "version",
        "content_markdown",
        "created_by",
        "created_at",
    )
    ordering = ("-created_at",)

    def get_queryset(self, request):
        # Compute the body length in the DB so the changelist's size column
        # doesn't load every revision's full markdown into memory.
        from django.db.models.functions import Length

        return (
            super()
            .get_queryset(request)
            .defer("content_markdown")
            .annotate(_md_len=Length("content_markdown"))
        )

    @admin.display(description="Size")
    def size_display(self, obj):
        size = getattr(obj, "_md_len", None)
        if size is None:
            size = len(obj.content_markdown)
        if size < 1024:
            return f"{size} B"
        return f"{size / 1024:.1f} KB"


# --------------------------
# Post Similarity (auto-computed)
# --------------------------
@admin.register(PostSimilarity)
class PostSimilarityAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    """Read-only browser over the precomputed similarity table."""

    list_display = ("source_post", "target_post", "score", "computed_at")
    list_filter = ("computed_at",)
    search_fields = (
        "source_post__title",
        "source_post__slug",
        "target_post__title",
        "target_post__slug",
    )
    list_select_related = ("source_post", "target_post")
    readonly_fields = (
        "source_post",
        "target_post",
        "score",
        "components",
        "computed_at",
    )
    list_per_page = 100


@admin.register(PostSlugHistory)
class PostSlugHistoryAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    """Read-only view of former slugs that 301-redirect to their post."""

    list_display = ("old_slug", "post", "created_at")
    search_fields = ("old_slug", "post__title", "post__slug")
    list_select_related = ("post",)
    readonly_fields = ("old_slug", "post", "created_at")
    list_per_page = 100
