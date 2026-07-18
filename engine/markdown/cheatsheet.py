"""Data-driven Markdown reference for the Post editor.

The old cheatsheet was ~190 lines of hand-written HTML embedded in the admin —
awkward to edit and impossible to reuse. This module holds the same knowledge as
plain data so it can drive two surfaces from one source:

- :func:`reference_html` renders the browsable reference shown under the editor
  (and the no-JS fallback), generated from the data below; and
- :func:`palette_payload` serialises the data to JSON for the in-editor
  "Markdown helper" command palette (``admin-markdown-helper``), which filters as
  you type and inserts the ``insert`` snippet at the CodeMirror cursor.

Authoring rules for the data:

- ``syntax`` is the literal example shown to the reader (HTML-escaped on render).
- ``insert`` is a CodeMirror snippet template — ``${1:placeholder}`` tab-stops and
  a final ``$0`` — applied via ``@codemirror/autocomplete``'s ``snippet()`` so it
  behaves exactly like the ``{.`` autocompletions. ``None`` marks a reference-only
  row (things that are automatic, or that you don't "insert").
- ``desc`` is short prose. Backtick code spans (`` `like this` ``) are the only
  markup; everything else is escaped. Keep it to one line.
"""

from __future__ import annotations

import html
import json
import re

_CODE_SPAN_RE = re.compile(r"`([^`]+)`")


def _i(syntax, insert, desc):
    """Build one reference item."""
    return {"syntax": syntax, "insert": insert, "desc": desc}


# Each section: title, an emoji icon (purely decorative), and its items.
CHEATSHEET_SECTIONS = [
    {
        "title": "Inline formatting",
        "icon": "✍️",
        "items": [
            _i("**bold**", "**${1:bold}**", "Bold"),
            _i("*italic*", "*${1:italic}*", "Italic"),
            _i("***bold italic***", "***${1:text}***", "Bold + italic"),
            _i("~~strike~~", "~~${1:text}~~", "Strikethrough"),
            _i("`inline code`", "`${1:code}`", "Inline code"),
            _i("H~2~O", "~${1:2}~", "Subscript"),
            _i("x^2^", "^${1:2}^", "Superscript (adjacent sub+sup auto-stack)"),
            _i("[SPQR]{.smallcaps}", "[${1:SPQR}]{.smallcaps}", "Small caps"),
            _i(
                "[note]{.marginnote}",
                "[${1:note}]{.marginnote}",
                "Margin note — renders in the outer margin",
            ),
            _i(
                "[0123]{.tabular-nums}",
                "[${1:0123}]{.tabular-nums}",
                "Tabular (lined-up) numerals",
            ),
            _i("[text]{.sans-serif}", "[${1:text}]{.sans-serif}", "Sans-serif run"),
            _i(
                "line 1␣␣⏎ line 2",
                None,
                "Hard line break — end a line with two trailing spaces",
            ),
            _i(
                "*[HTML]: Hyper Text Markup Language",
                "*[${1:ABBR}]: ${2:Expansion}",
                "Abbreviation — expands every occurrence into `<abbr>`",
            ),
            _i(
                "Smart punctuation",
                None,
                "Automatic: `--` → en-dash, `---` → em-dash, `...` → ellipsis, "
                "straight quotes → curly",
            ),
        ],
    },
    {
        "title": "Headings & blocks",
        "icon": "🔠",
        "items": [
            _i(
                "# H1 … ###### H6",
                "# ${1:Heading}",
                "Heading — auto-anchored, sectionized, copy-link button",
            ),
            _i(
                "## Heading {#custom-id}",
                "## ${1:Heading} {#${2:custom-id}}",
                "Heading with an explicit anchor id",
            ),
            _i("> quote", "> ${1:quote}", "Blockquote (nesting supported)"),
            _i(
                "> {>>} text",
                "> {>>} ${1:text}",
                "Float blockquote right (`{<<}` floats left)",
            ),
            _i("---", "\n---\n\n$0", "Horizontal rule (three or more)"),
            _i(
                "```lang … ```",
                "```${1:python}\n${2:code}\n```\n$0",
                "Fenced code block with syntax highlighting",
            ),
            _i(
                "term\n:   definition",
                "${1:term}\n:   ${2:definition}\n$0",
                "Definition list",
            ),
            _i(
                "- [ ] todo",
                "- [ ] ${1:todo}",
                "Task list — display-only checkboxes (`- [x]` = done)",
            ),
            _i("<blank>+4-space indent", None, "Indented code block (no highlighting)"),
        ],
    },
    {
        "title": "Lists",
        "icon": "•",
        "items": [
            _i("- item", "- ${1:item}", "Unordered list (indent 4 spaces to nest)"),
            _i("1. item", "1. ${1:item}", "Ordered list"),
            _i("5. item", "5. ${1:item}", "Ordered list starting at 5 (fancy-lists)"),
            _i(
                "a. item · i. item",
                None,
                "Alpha / roman numbering (fancy-lists)",
            ),
            _i(
                "Nesting",
                None,
                "Levels auto-classed (`.list-level-1`…); mixed ordered/unordered ok",
            ),
        ],
    },
    {
        "title": "Links",
        "icon": "🔗",
        "items": [
            _i(
                "[text](https://example.com)",
                "[${1:text}](${2:https://example.com})",
                "External link — gets `target=_blank`, `rel=noopener`, domain icon",
            ),
            _i(
                "[text](/posts/other-slug/)",
                "[${1:text}](/posts/${2:other-slug}/)",
                "Internal link — backlinks auto-extracted on save",
            ),
            _i(
                '[text](url "hover title")',
                '[${1:text}](${2:url} "${3:hover title}")',
                "Link with a title attribute",
            ),
            _i(
                "[text](url){.icon-not}",
                "[${1:text}](${2:url}){.icon-not}",
                "Suppress the automatic link icon",
            ),
            _i(
                "[text][ref] … [ref]: url",
                "[${1:text}][${2:ref}]\n\n[${2:ref}]: ${3:https://example.com}\n$0",
                "Reference-style link (define anywhere)",
            ),
            _i("https://example.com", None, "A bare URL is auto-linked"),
            _i(
                "Auto-decorated domains",
                None,
                "ArXiv, GitHub, Wikipedia, YouTube, X, Mastodon, Reddit, NYT, "
                "Google Scholar, PubMed, Internet Archive, and more",
            ),
        ],
    },
    {
        "title": "Images & media",
        "icon": "🖼️",
        "items": [
            _i(
                "![Alt](@asset:my-key)",
                "![${1:Alt text}](@asset:${2:my-key})",
                "Global asset by key — responsive srcset, lazy, auto-sized",
            ),
            _i(
                "![Alt](@fig1)",
                "![${1:Alt text}](@${2:fig1})",
                "Post-local alias (set on the Post Asset row)",
            ),
            _i(
                "![Alt](@asset:key?width=400)",
                "![${1:Alt text}](@asset:${2:my-key}?width=${3:400})",
                "Width override in px; aspect ratio preserved",
            ),
            _i(
                '![Alt](@asset:key "Caption")',
                '![${1:Alt text}](@asset:${2:my-key} "${3:Caption text}")',
                "Image with caption (rendered in a `<figure>`)",
            ),
            _i(
                "![Alt](@asset:key){.float-right}",
                "![${1:Alt text}](@asset:${2:my-key}){.float-right}",
                "Float right (also `.float-left`, `.width-full`)",
            ),
            _i(
                "![](@asset:clip)",
                "![](@asset:${1:clip})",
                "Video / audio — asset type auto-detected, controls added",
            ),
            _i(
                "![](@asset:clip?loop=1&autoplay=1)",
                "![](@asset:${1:clip}?loop=1&autoplay=1&muted=1)",
                "Video params: `loop`, `autoplay`, `muted`",
            ),
        ],
    },
    {
        "title": "Citations",
        "icon": "📚",
        "items": [
            _i("[@smith2020]", "[@${1:smith2020}]", "Parenthetical citation"),
            _i(
                "[@smith2020, pp. 42–44]",
                "[@${1:smith2020}, ${2:pp. 42–44}]",
                "With a locator",
            ),
            _i("@smith2020", "@${1:smith2020}", "Narrative — “Smith (2020) showed…”"),
            _i("[-@smith2020]", "[-@${1:smith2020}]", "Suppress author (year only)"),
            _i(
                "[@a; @b, p. 10; @c]",
                "[@${1:a}; @${2:b}]",
                "Multi-citation (semicolon-separated)",
            ),
            _i(
                "Unknown keys",
                None,
                "Render as `[??key]`; keys come from the Source library",
            ),
        ],
    },
    {
        "title": "Footnotes",
        "icon": "†",
        "items": [
            _i(
                "A claim.[^1] … [^1]: body",
                "[^${1:1}]\n\n[^${1:1}]: ${2:The footnote body.}\n$0",
                "Reference-style footnote (define anywhere)",
            ),
            _i(
                "A claim.^[Inline footnote.]",
                "^[${1:Inline footnote.}]",
                "Inline footnote — no separate definition",
            ),
            _i(
                "Collected",
                None,
                "All footnotes gather into one section at the bottom with backlinks",
            ),
        ],
    },
    {
        "title": "Math",
        "icon": "∑",
        "items": [
            _i("$E = mc^2$", "$${1:E = mc^2}$", "Inline math"),
            _i(
                "$$ … $$",
                "$$\n${1:\\int_0^\\infty e^{-x}\\,dx = 1}\n$$\n$0",
                "Display math (copy-LaTeX button added)",
            ),
            _i(
                "\\newcommand",
                None,
                "Full LaTeX via MathJax; custom `\\newcommand` persists within a post",
            ),
        ],
    },
    {
        "title": "Tables",
        "icon": "▦",
        "items": [
            _i(
                "| a | b |",
                "| ${1:Right} | ${2:Left} |\n|------:|:------|\n"
                "| ${3:12} | ${4:foo} |\n\n: ${5:Caption}\n$0",
                "Pipe table — `:` in the rule sets column alignment",
            ),
            _i(": Caption here", ": ${1:Caption}", "Caption line after the table"),
            _i(
                "::: {.table-small} … :::",
                "::: {.table-small}\n${1:| a | b |\n|---|---|\n| 1 | 2 |}\n:::\n$0",
                "Compact / dense table variant",
            ),
            _i(
                "::: {.sortable} … :::",
                "::: {.sortable}\n${1:| a | b |\n|---|---|\n| 1 | 2 |}\n:::\n$0",
                "Client-sortable table",
            ),
            _i(
                "Pandoc grid tables",
                None,
                "Use `+---+---+` / `|…|` grids for multi-line or spanned cells",
            ),
        ],
    },
    {
        "title": "Admonitions",
        "icon": "💡",
        "items": [
            _i(
                "::: {.admonition-tip} … :::",
                "::: {.admonition-tip}\n# ${1:Title}\n\n${2:Body}\n:::\n$0",
                "Tip callout",
            ),
            _i(
                "::: {.admonition-note} … :::",
                "::: {.admonition-note}\n# ${1:Title}\n\n${2:Body}\n:::\n$0",
                "Neutral note callout",
            ),
            _i(
                "::: {.admonition-warning} … :::",
                "::: {.admonition-warning}\n# ${1:Title}\n\n${2:Body}\n:::\n$0",
                "Warning callout",
            ),
            _i(
                "::: {.admonition-error} … :::",
                "::: {.admonition-error}\n# ${1:Title}\n\n${2:Body}\n:::\n$0",
                "Error / pitfall callout",
            ),
            _i(
                "Title is optional",
                None,
                "If present it must be a `#` heading line just inside the fence",
            ),
        ],
    },
    {
        "title": "Layout blocks",
        "icon": "🧱",
        "items": [
            _i(
                "::: {.epigraph} … :::",
                "::: {.epigraph}\n> ${1:Quote}\n>\n> --- ${2:Attribution}\n:::\n$0",
                "Epigraph — blockquote + right-aligned attribution",
            ),
            _i(
                "::: {.columns} … :::",
                "::: {.columns}\n- ${1:a}\n- ${2:b}\n- ${3:c}\n:::\n$0",
                "Multi-column layout (applies to the nested list)",
            ),
            _i(
                "::: {.text-center} … :::",
                "::: {.text-center}\n${1:Content}\n:::\n$0",
                "Center-align the paragraphs inside",
            ),
            _i(
                "::: {.text-right} … :::",
                "::: {.text-right}\n${1:Content}\n:::\n$0",
                "Right-align",
            ),
            _i(
                "::: {.sans-serif} … :::",
                "::: {.sans-serif}\n${1:Content}\n:::\n$0",
                "Switch paragraphs to the sans-serif stack",
            ),
            _i(
                "::: {.float-right} … :::",
                "::: {.float-right}\n${1:Content}\n:::\n$0",
                "Float a block (also `.float-left`, `.width-full`)",
            ),
        ],
    },
    {
        "title": "Dates",
        "icon": "📅",
        "items": [
            _i(
                "[2020-01-15]{.date-since}",
                "[${1:2020-01-15}]{.date-since}",
                "Date + subscript “N years ago”",
            ),
            _i(
                "[1500–1600]{.date-range}",
                "[${1:1500–1600}]{.date-range}",
                "Date range with a duration subscript",
            ),
            _i(
                "[1500–1600]{.date-range-since}",
                "[${1:1500–1600}]{.date-range-since}",
                "Range + “years since end date”",
            ),
            _i(
                "Separator",
                None,
                "Must be en-dash `–`, em-dash `—`, or `--`; BC/BCE and ISO ok",
            ),
        ],
    },
    {
        "title": "Raw HTML & escapes",
        "icon": "⚙️",
        "items": [
            _i(
                '<div class="…">…</div>',
                '<div class="${1:my-class}">\n${2:…}\n</div>\n$0',
                "Raw HTML passes through, then is sanitized (scripts stripped)",
            ),
            _i("\\*not italic\\*", "\\${1:*}", "Backslash-escape any metacharacter"),
            _i(
                "Disallowed",
                None,
                "`<script>`, `<style>`, and `on*=` handlers are stripped",
            ),
        ],
    },
    {
        "title": "Automatic — no typing",
        "icon": "✨",
        "items": [
            _i("Heading anchors", None, "Every heading gets a slug `id` + copy-link"),
            _i(
                "First paragraph",
                None,
                "Tagged `.first-graf` for the intro-small-caps toggle",
            ),
            _i(
                "Smart punctuation", None, "Curly quotes, dashes, ellipsis, unit spaces"
            ),
            _i("Sub/super stacking", None, "Adjacent `~sub~` + `^sup^` auto-stacked"),
            _i("External link icons", None, "Domain / file-type icons attached"),
            _i("Bibliography", None, "Appended whenever citations resolve"),
            _i(
                "Table of contents",
                None,
                "Generated from headings when the toggle is on",
            ),
        ],
    },
]


def _render_desc(text):
    """Escape ``text`` and turn backtick spans into ``<code>`` (safe HTML)."""
    escaped = html.escape(text)
    return _CODE_SPAN_RE.sub(r"<code>\1</code>", escaped)


def _render_syntax(text):
    """Escape a syntax example; multi-line examples keep their line breaks."""
    return html.escape(text).replace("\n", "<br>")


def reference_html():
    """Render the browsable ``<details>`` reference from the section data.

    This is the progressive-enhancement fallback: it works with no JavaScript,
    and the palette hides it once ``admin-markdown-helper`` has mounted.
    """
    parts = [
        '<div class="mc-body" data-md-reference>',
        '<p class="mc-lead">Pandoc-flavoured Markdown with project extensions. '
        "Open a section to browse, or use the search-and-insert helper above.</p>",
    ]
    for section in CHEATSHEET_SECTIONS:
        parts.append(
            "<details><summary>{} {}</summary><table>".format(
                html.escape(section["icon"]), html.escape(section["title"])
            )
        )
        for item in section["items"]:
            parts.append(
                '<tr><td class="mc-syntax"><code>{}</code></td>'
                '<td class="mc-desc">{}</td></tr>'.format(
                    _render_syntax(item["syntax"]), _render_desc(item["desc"])
                )
            )
        parts.append("</table></details>")
    parts.append("</div>")
    return "".join(parts)


def palette_payload():
    """Return the section data as a JSON string for the in-editor palette."""
    return json.dumps(CHEATSHEET_SECTIONS, ensure_ascii=False)
