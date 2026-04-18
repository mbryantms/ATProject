# Post editor — CodeMirror 6 reference

The `content_markdown` field on the Post change form uses CodeMirror 6. This
doc describes what the editor does today, what keybindings are wired, and
what is deliberately not yet built.

Throughout, `Mod` means **Cmd on macOS** and **Ctrl on Linux / Windows**.

## Where it applies

- Django admin → Posts → add/edit → the **Content markdown** textarea.
- Nowhere else. Description, abstract, and meta fields stay plain textareas.
- The underlying `<textarea id="id_content_markdown">` stays in the DOM, just
  hidden. Form submission, Django validation, and revision snapshots all read
  from the textarea; the editor mirrors its value back on every edit and one
  more time immediately before the form submits.

## Visual features

- **Line numbers** down the left gutter.
- **Fold gutter** next to the line numbers — triangles appear wherever the
  markdown parser identifies a foldable region (headings, fenced code blocks,
  block HTML, etc.).
- **Active-line highlight** on both the line itself and its gutter number.
- **Bracket matching** — when the cursor is adjacent to `()`, `[]`, or `{}`,
  the paired bracket is highlighted.
- **Selection-match highlights** — select a word and every other occurrence
  in the document gets a subtle highlight.
- **Soft line wrap** — no horizontal scrolling; long lines wrap visually
  without inserting newlines into the source.
- **Theme** reads from the Django admin CSS variables (`--body-bg`,
  `--body-fg`, `--border-color`, `--darkened-bg`, `--selected-row`,
  `--selected-bg`), so it follows the admin's light / dark mode automatically.
- **Max height** capped at `70vh`; the editor scrolls internally past that.

## Markdown-aware behavior

The editor loads `@codemirror/lang-markdown`, which gives you:

- Syntax highlighting for ATX headings (`# … ######`), setext headings,
  emphasis (`*italic*`, `_italic_`), strong (`**bold**`), inline code,
  fenced code blocks (with language name highlighted), indented code blocks,
  blockquotes, ordered / unordered lists, links, images, thematic breaks
  (`---`, `***`, `___`), HTML blocks, and YAML frontmatter.
- **List continuation** — pressing Enter inside a list item inserts the next
  list marker automatically; pressing Enter on an empty item ends the list.
- **Fold regions** — headings, fenced code blocks, and block HTML are foldable.
- **Syntax-aware navigation** — `Mod-i` selects the parent markdown node
  (useful for selecting a whole blockquote, list, or code block), and
  `Alt-ArrowLeft / Right` steps through syntax nodes.

The custom ATProject syntax (`@asset:key`, `[@smith2020]`,
`::: {.admonition-tip}`, footnotes, marked dates) renders as plain text in
the editor — highlighting these is a stretch item (see "Not built yet"
below). It still renders correctly on save because the server-side Pandoc
pipeline handles it.

## Keybinding reference

### Editing

| Keys | Action |
| --- | --- |
| `Enter` | New line with indent |
| `Mod-Enter` | Insert blank line below |
| `Backspace` / `Delete` | Delete char left / right |
| `Mod-Backspace` / `Mod-Delete` | Delete word left / right |
| `Mod-]` | Indent selection |
| `Mod-[` | Dedent selection |
| `Tab` | Indent selection (or insert tab at cursor) |
| `Shift-Tab` | Dedent selection |
| `Mod-Alt-\` | Re-indent whole selection |
| `Shift-Mod-k` | Delete current line |
| `Alt-ArrowUp` / `Alt-ArrowDown` | Move current line up / down |
| `Shift-Alt-ArrowUp` / `Shift-Alt-ArrowDown` | Duplicate current line up / down |
| `Mod-/` | Toggle line comment (respects language mode) |
| `Alt-Shift-a` | Toggle block comment |

### Cursor movement

| Keys | Action |
| --- | --- |
| `ArrowLeft` / `ArrowRight` | Character |
| `Mod-ArrowLeft` / `Mod-ArrowRight` | By word (macOS: `Alt-ArrowLeft/Right`) |
| `Alt-ArrowLeft` / `Alt-ArrowRight` | By syntax node |
| `ArrowUp` / `ArrowDown` | Line |
| `PageUp` / `PageDown` | Page |
| `Home` / `End` | Line start / end |
| `Mod-Home` / `Mod-End` | Document start / end |

### Selection

| Keys | Action |
| --- | --- |
| `Shift-<any cursor key>` | Extend selection by that movement |
| `Mod-a` | Select all |
| `Alt-l` (Linux / Win) / `Ctrl-l` (macOS) | Select current line |
| `Mod-i` | Select parent syntax node (expand outward) |
| `Shift-Mod-\` | Jump to matching bracket |
| `Escape` | Collapse multiple cursors / clear extra selections |

### Multi-cursor & column selection

| Keys | Action |
| --- | --- |
| `Mod-Alt-ArrowUp` / `Mod-Alt-ArrowDown` | Add cursor above / below |
| `Mod-d` | Add next occurrence of current selection to cursors |
| `Mod-Shift-l` | Select all occurrences of current selection |
| `Alt-drag` | Column / rectangular selection (crosshair cursor appears) |

### Undo / redo

| Keys | Action |
| --- | --- |
| `Mod-z` | Undo |
| `Mod-y` (Linux / Win) / `Mod-Shift-z` (macOS) | Redo |
| `Mod-u` | Undo selection change (text state unchanged) |
| `Alt-u` (Linux / Win) / `Mod-Shift-u` (macOS) | Redo selection change |

### Search & replace

| Keys | Action |
| --- | --- |
| `Mod-f` | Open search panel |
| `F3` / `Mod-g` | Find next (Shift for previous) |
| `Escape` | Close search panel |
| `Mod-Alt-g` | Go to line number |

The search panel has toggles for case-sensitive, regex, whole-word, and
replace. It's a real panel inside the editor — not the browser's Ctrl-F.

### Folding

| Keys | Action |
| --- | --- |
| `Ctrl-Shift-[` (macOS: `Cmd-Alt-[`) | Fold at cursor |
| `Ctrl-Shift-]` (macOS: `Cmd-Alt-]`) | Unfold at cursor |
| `Ctrl-Alt-[` | Fold everything foldable |
| `Ctrl-Alt-]` | Unfold everything |

You can also click the triangle in the fold gutter.

### Autocomplete popup

No completion sources are wired yet (citation keys and asset aliases are
stretch items), but the popup infrastructure is live — relevant if you ever
trigger it manually or a language feature opens it:

| Keys | Action |
| --- | --- |
| `Ctrl-Space` | Manually open the popup |
| `ArrowUp` / `ArrowDown` | Move selection |
| `PageUp` / `PageDown` | Page selection |
| `Enter` | Accept current suggestion |
| `Escape` | Close popup |

Auto-close brackets also get a polite deletion:

| Keys | Action |
| --- | --- |
| `Backspace` (inside empty auto-inserted pair) | Delete both sides of the pair |

## Form integration

- The editor writes its current value back to the hidden `<textarea>` on
  **every document change** and again in the `submit` event handler.
- Django's existing save flow therefore sees the same value whether you save
  via **Save**, **Save and continue**, or the "🔍 Preview rendered markdown"
  button from Phase 2 (which `fetch`s the endpoint with the textarea value).
- The Phase 2 save-time linter (orphan assets, unresolved citations, broken
  internal links, unmatched `:::` fences) runs after save and surfaces
  warnings at the top of the change form — independent of the editor.

## Double-bind guard

The mount script sets `data-cm-bound="1"` on the textarea after
initialization. If the admin ever re-renders the form inline (e.g. via a
future HTMX swap), the editor refuses to double-attach to the same textarea.

## Not built yet (stretch work)

None of these are active; they'd each need a follow-up pass.

- **Citation-key autocomplete.** A completion source that queries the Source
  library and suggests keys inside `[@…]` or after a bare `@`.
- **Asset alias / key autocomplete.** Completion source reading the Post's
  attached `PostAsset` set (for `@alias`) and the global `Asset.key` set
  (for `@asset:…`) while inside a markdown link/image target.
- **Token decorations** — colored highlighting for `@asset:*`, `[@cite]`,
  `::: {.admonition-*}`, marked-date spans, so bespoke syntax is visually
  distinct from prose.
- **Inline lint gutter.** Pipe the Phase 2 lint warnings (orphan assets,
  unknown citations, broken internal links, unclosed admonition fences) into
  `@codemirror/lint` so they show as wavy underlines + gutter icons while
  you type instead of only after save.
- **MathJax in the Phase 2 preview iframe.** Currently the preview shows
  rendered HTML with site CSS but no MathJax evaluation.

## Troubleshooting

- **Nothing changed on the Post change form.** The bundle lives at
  `static/js/dist/admin-post-editor.js`. If you just ran `npm install` or
  edited `admin-post-editor-entry.js`, rebuild with
  `npm run build:js:admin-post-editor` (or run `npm run dev` for a watcher)
  and then `uv run python manage.py collectstatic --noinput` so Whitenoise
  serves it. Hard-refresh the admin page.
- **Editor appears but the textarea below is still visible.** The mount
  script hides the textarea via `style.display = 'none'`. If you see both,
  the bundle didn't load — check the browser console for a 404 on
  `admin-post-editor.js`.
- **Tab is inserting a tab instead of indenting.** It is indenting. The file
  is indented with 4 spaces (`EditorState.tabSize.of(4)` +
  `indentWithTab`). If the character looks like a tab, your display font is
  rendering the 4 spaces as one wide glyph.

## Build & wiring pointers

- Editor source: [static/js/admin-post-editor-entry.js](static/js/admin-post-editor-entry.js)
- Bundle (git-ignored, built locally and in Docker): `static/js/dist/admin-post-editor.js`
- Admin hookup: [engine/admin/post.py](engine/admin/post.py) `PostAdmin.Media.js`
- npm scripts: `build:js:admin-post-editor`, `watch:js:admin-post-editor`
- npm deps: `@codemirror/{state,view,commands,language,lang-markdown,autocomplete,search,lint}` + `@lezer/highlight`
