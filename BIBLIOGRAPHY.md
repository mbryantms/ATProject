# Bibliography & Citation System

A complete guide to the bibliography and citation system — how it works, how to use every feature, what's automated, and what's planned next.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Writing Citations in Posts](#writing-citations-in-posts)
3. [Managing Sources](#managing-sources)
4. [Zotero Integration](#zotero-integration)
5. [Auto-Populating Metadata](#auto-populating-metadata)
6. [Archiving Source Files](#archiving-source-files)
7. [Link Rot Detection](#link-rot-detection)
8. [Citation Formatting Engine](#citation-formatting-engine)
9. [Public Library, Exports & Further Reading](#public-library-exports--further-reading)
10. [Deployment Notes](#deployment-notes)
11. [Remaining Steps](#remaining-steps)
12. [Future Improvements](#future-improvements)

---

## Architecture Overview

The system has four layers:

```
Markdown Content        [@key] syntax in posts
        ↓
Rendering Pipeline      preprocessor → Pandoc → postprocessor (citeproc-js)
        ↓
Data Layer              Source model + PostCitation join table
        ↓
Presentation            Inline citations, bibliography section, tooltips
```

**Key components:**

| Component | Location | Purpose |
|-----------|----------|---------|
| Source model | `engine/models/source.py` | Universal source library — every citable item |
| PostCitation model | `engine/models/citation.py` | Tracks which posts cite which sources |
| Citation escaper | `engine/markdown/preprocessors/citation_escaper.py` | Protects `[@key]` from Pandoc |
| Citation renderer | `engine/markdown/postprocessors/citation_renderer.py` | Resolves citations, generates HTML |
| citeproc bridge | `engine/bibliography/citeproc_bridge.js` | Node.js subprocess for formatting |
| Python formatter | `engine/bibliography/formatter.py` | Calls citeproc-js, handles fallback |
| Zotero sync | `engine/bibliography/zotero_sync.py` | Import/sync from Zotero |
| Metadata resolvers | `engine/bibliography/metadata_resolvers.py` | DOI, ISBN, URL auto-population |
| Link checker | `engine/bibliography/link_checker.py` | URL health + Wayback Machine |
| Celery tasks | `engine/bibliography/tasks.py` | Async sync, URL checks, metadata |

**What's automated:**

- Citation key generation (on Source save, if blank)
- CSL-JSON rebuild (on Source save, always)
- Citation rendering + bibliography section (on Post save, via Celery task)
- PostCitation join table sync (on Post save, via Celery task)
- Archived-file SHA-256 hashing + deduplication (on SourceFile save)
- Archived-file kind detection, size/filename capture (on SourceFile save)
- Full-text extraction from archived files (async, on upload; feeds search)
- Proactive Wayback Machine submission (on Source create / URL change)
- Source search vector refresh (on Source/SourceFile save; sources appear in site search)
- Citing-post re-render (on SourceFile upload/replace/delete/visibility change — the `[PDF]`-style links in cached bibliographies stay current)

---

## Writing Citations in Posts

### Syntax Reference

Use Pandoc-compatible citation syntax in your markdown:

| Syntax | Renders As | Use Case |
|--------|-----------|----------|
| `[@smith2024climate]` | (Smith, 2024) | Standard parenthetical citation |
| `[@smith2024climate, pp. 42-56]` | (Smith, 2024, pp. 42–56) | With page numbers |
| `[@smith2024climate, ch. 3]` | (Smith, 2024, ch. 3) | With chapter locator |
| `[@key1; @key2]` | (Jones, 2023; Smith, 2024) | Multiple sources, one bracket |
| `@smith2024climate` | Smith (2024) | Narrative / in-text citation |
| `[-@smith2024climate]` | (2024) | Suppress author (year only) |

### Locator Types

Supported locator prefixes: `p.`, `pp.`, `page`, `ch.`, `chap.`, `chapter`, `sec.`, `section`, `para.`, `paragraph`, `vol.`, `volume`, `fig.`, `figure`, `no.`, `l.`, `line`, `n.`, `note`.

### What Happens When You Save a Post

1. The Celery task `update_post_derived_content` fires
2. The **citation escaper** preprocessor converts `[@key]` to `%%CITE:key%%` placeholders
3. Pandoc converts the rest of the markdown to HTML
4. The **citation renderer** postprocessor:
   - Finds all `%%CITE:...%%` placeholders
   - Batch-queries the Source table for all keys
   - Sends resolved CSL-JSON to citeproc-js for formatting
   - Replaces placeholders with styled `<a>` elements
   - Appends a bibliography section before any footnotes
   - Records which keys resolved (for PostCitation sync)
5. The task syncs **PostCitation** records (creates/deletes to match content)
6. The rendered HTML is cached in `content_html_cached`

### Unresolved Citations

If a citation key doesn't match any Source, it renders as:

```html
<span class="citation-unresolved">[??unknownkey]</span>
```

This is visually distinct (red text) so you can find and fix typos.

### Coexistence with Footnotes

Citations and footnotes use separate systems and don't conflict. The bibliography section is inserted *before* the footnotes section in the HTML. Both have their own IDs (`#references` and `#footnotes`).

---

## Managing Sources

### Creating Sources While Writing

The fastest path: in the post editor, open **📚 Browse & insert citation** and use the **"New source"** row at the bottom of the modal. Paste a **DOI, URL, ISBN, or plain title** and hit *Create & insert*:

- The identifier is classified automatically (DOI resolver-URL prefixes like `https://doi.org/…` are stripped; ISBNs may include hyphens).
- Metadata is fetched synchronously — CrossRef for DOIs, Open Library for ISBNs, OpenGraph/meta tags for URLs — and a Source is created with an auto-generated citation key.
- `[@key]` is inserted at your cursor. If a source with that identifier already exists, its key is inserted instead of creating a duplicate.
- A plain title creates a bare source you can flesh out later; a failed metadata lookup creates nothing and shows the error in the modal.

### Adding Sources via Admin

Go to **Admin → Engine → Sources → Add Source**.

**Required fields:**
- **Title** — the source title
- **Source type** — select from CSL types (Article, Book, Web Page, etc.)

**Auto-generated fields:**
- **Citation key** — leave blank and it auto-generates from `{author}{year}{title}` (e.g., `smith2024climate`). Once set, treat it as permanent — changing it breaks existing citations.
- **CSL-JSON** — rebuilt from structured fields on every save. Read-only in admin.

**Recommended fields to fill:**
- Authors (JSON format: `[{"family": "Smith", "given": "John"}]`)
- Issued date (JSON format: `{"date-parts": [[2024, 3, 15]]}` — partial dates like `[[2024]]` are fine)
- DOI, URL, ISBN (enable auto-population and link checking)
- Container title (journal name, website name, etc.)

### Citation Key Rules

- Format: lowercase letters, digits, hyphens only (regex: `^[a-z0-9][a-z0-9_-]*$`)
- Auto-generated pattern: `{first_author_family}{year}{first_significant_title_word}`
- Collision avoidance: appends `a`, `b`, `c` suffixes when needed
- Uniqueness is enforced across all sources including soft-deleted ones
- **Never rename** a citation key that's used in published content

### Bulk Actions (Admin)

Select sources in the list view, then use the action dropdown:

| Action | What It Does |
|--------|-------------|
| **Fetch metadata from DOI** | Queries CrossRef API, fills empty fields |
| **Fetch metadata from URL** | Scrapes OpenGraph/meta tags, fills empty fields |
| **Check URLs for availability** | HTTP HEAD check + Wayback Machine lookup |
| **Sync selected from Zotero** | Re-imports metadata from Zotero for sources with zotero_key |
| **Soft delete selected** | Marks as deleted (preserves data, hides from queries) |
| **Restore selected** | Un-deletes soft-deleted sources |

Bulk actions run asynchronously on Celery. For a **single source**, use the buttons at the bottom of its change form instead — **Fetch metadata from DOI**, **Fetch metadata from URL**, and **Check URL health now** run synchronously, so the fields fill in on the page reload. (The buttons appear once the source has a saved DOI/URL.)

### Seeing Where a Source Is Cited

The Source changelist has a sortable **Cited** column and a "cited in posts" filter (cited / uncited — the uncited view doubles as a cleanup report). Each source's change form has a **Citations** section listing every citing post with a link and status badge.

### Viewing Citations on a Post

In the Post admin, the **Cited Sources** inline shows all sources cited in that post's content, with their citation key and position. The **annotation** field is editable here — use it for per-post notes about a source. Saved annotations render below the corresponding reference entry in the post's bibliography (annotated bibliography); saving an annotation queues a re-render of the cached HTML automatically.

---

## Zotero Integration

### Initial Setup

1. Go to **Admin → Engine → Site Settings**
2. Expand the **Zotero Integration** section
3. Fill in:
   - **Library ID** — your **numeric** user ID (find at zotero.org/settings/keys — it says "Your userID for use in API calls is XXXXXXX"). This is NOT your username.
   - **Library type** — "User" for personal library, "Group" for shared
   - **API key** — generate at [zotero.org/settings/keys](https://www.zotero.org/settings/keys). Grant read access to the library.

### Syncing

**Incremental sync** (default — only fetches items modified since last sync):
```bash
uv run python manage.py sync_zotero
```

**Full re-import** (fetches everything):
```bash
uv run python manage.py sync_zotero --full
```

**Preview without saving:**
```bash
uv run python manage.py sync_zotero --dry-run
```

### What Sync Does

- Requests items from Zotero in CSL-JSON format (`pyzotero` with `format='csljson'`)
- For each item:
  - If the Zotero key matches an existing Source → updates metadata (but **never overwrites** the citation key)
  - If new → creates a Source with auto-generated citation key
- Updates `zotero_key`, `zotero_version`, `zotero_raw` on each synced Source
- Records the library version for incremental sync next time

### Scheduled Sync via Celery Beat

To sync automatically on a schedule:

1. Go to **Admin → Periodic Tasks → Add**
2. Set:
   - Name: "Zotero Sync"
   - Task: `engine.bibliography.tasks.sync_zotero_library`
   - Schedule: e.g., every 6 hours via Interval, or a cron expression
   - Kwargs: `{"full": false}` (or `true` for full re-import)

### Re-importing Individual Sources

Select sources in the Source admin list → action **"Sync selected from Zotero (re-import)"**. This fetches fresh data from Zotero for each selected source that has a `zotero_key`.

---

## Auto-Populating Metadata

Metadata can be fetched three ways: the **create-source flow in the post editor** (see [Creating Sources While Writing](#creating-sources-while-writing)), the **per-source buttons** on the change form (synchronous), and the **bulk changelist actions** (async via Celery). All share the same resolvers and fill only empty fields.

Every outbound fetch in the bibliography subsystem — resolvers, link checker, Wayback submission — goes through a shared helper (`engine/bibliography/net.py`) that (a) refuses non-http(s) schemes and hosts resolving to private/internal addresses, and (b) rate-limits to **one request per second per host**, so batch loops don't hammer CrossRef, Open Library, or archive.org. The throttle is per-process (politeness, not a global SLA).

### From DOI

When a Source has a DOI:

1. Open it and click **"Fetch metadata from DOI"** (or select several in the changelist and use the bulk action)
2. The system queries the CrossRef API, which returns CSL-JSON natively
3. Only **empty** fields are filled (existing data is preserved)

Fields populated from DOI: title, authors, container-title, publisher, volume, issue, page, issued date, URL, ISSN, ISBN, abstract.

### From URL

When a Source has a URL:
1. Select it in the Source admin
2. Action → **"Fetch metadata from URL"**
3. The system fetches the page and extracts:
   - OpenGraph tags (og:title, og:site_name, og:description)
   - HTML meta tags (author, date, description)
   - Dublin Core metadata
4. Domain-specific handling: arXiv → article type, YouTube → motion_picture type, GitHub → software type

### From ISBN

Available programmatically via `engine.bibliography.metadata_resolvers.resolve_isbn()`. Uses the Open Library API to fetch book metadata including authors (resolved via additional API calls).

### Async Metadata Fetching

For background processing:
```python
from engine.bibliography.tasks import fetch_metadata_for_source
fetch_metadata_for_source.delay(source_id=42, resolve_type="doi")
```

---

## Archiving Source Files

### The SourceFile Model

Each Source can hold **multiple archived files** (`SourceFile` rows, `source.files`): the published PDF, an author-manuscript DOCX, an HTML snapshot, supplements. Per file:

- **kind** — auto-detected from the extension (pdf / doc / html)
- **label** — optional role note ("Preprint", "Supplement")
- **is_public** — whether a link renders in bibliographies (note: media storage itself is public; this only gates rendering)
- **provenance** — manual upload vs. Zotero attachment
- **sha256 / size / original_filename** — captured automatically on save
- **extracted_text** — full text pulled asynchronously for search indexing

### Uploading Files

In the Source admin, use the **Source files** inline — upload, label, and toggle visibility per file. Each row shows a download link, detected kind, size, and hash prefix.

Uploading, replacing, deleting, or toggling visibility on a file automatically queues a re-render of every post citing the source, so the `[PDF]`-style links appear in (or vanish from) published bibliographies without re-saving the post.

**Accepted formats:** PDF, DOC/DOCX, and HTML — these cover the overwhelming majority of research papers and primary literature. Enforced by extension validation plus a magic-byte sniff (a `.pdf` that isn't a PDF is rejected).

**Future formats** (accepted-list candidates, in rough priority order): EPUB, TXT/MD, RTF, JATS XML (`.xml`/`.nxml` — PubMed Central full text), LaTeX source bundles (`.tex`/`.tar.gz`), ODT, PPTX, DjVu, PostScript, MHTML/WARC web archives.

Files are stored in Cloudflare R2 under the `sources/YYYY/MM/` path via the existing django-storages backend.

### File Links in Bibliography

Every **public** file on a cited source renders as a type-labeled link after the reference entry — `[PDF]`, `[DOC]`, `[HTML]` — with PDFs listed first:

```html
<li id="ref-smith2024" class="reference-entry">
  <span class="reference-text">Smith, J. (2024). Climate Change...</span>
  <a href="/media/sources/2024/01/paper.pdf" class="reference-file-link">[PDF]</a>
  <a href="/media/sources/2024/01/manuscript.docx" class="reference-file-link">[DOC]</a>
</li>
```

### File Deduplication

On save, a new or replaced file gets a SHA-256 hash. If any SourceFile already holds identical bytes, the new row **reuses the existing stored object** instead of uploading a duplicate — including across different sources and for Zotero downloads.

### Full-Text Extraction

New and replaced files are text-extracted in the background (`extract_source_file_text` task): PDF via pypdf, HTML via BeautifulSoup, DOCX via pandoc (legacy binary `.doc` is archived but not extractable). Extracted text feeds the source's search vector at weight D, so library search matches the *content* of archived papers, not just their metadata. Extraction failures are silent by design — a file that can't be extracted is still a valid archive.

---

## Link Rot Detection

### Manual URL Checking

Select sources in the admin → action **"Check URLs for availability"**.

For each source with a URL:
1. Sends an HTTP HEAD request (falls back to GET if HEAD returns 405)
2. Records status: `ok`, `redirect`, `broken`
3. If broken, checks the Wayback Machine for an archived snapshot
4. If found, stores the archive URL and sets status to `archived`

### Batch URL Checking (Command)

```bash
# Check 50 URLs (never-checked first, then oldest-checked; skips recently checked)
uv run python manage.py check_source_urls

# Larger batch, re-check after 1 day
uv run python manage.py check_source_urls --batch-size 100 --max-age 1
```

### Scheduled URL Checking via Celery Beat

1. Go to **Admin → Periodic Tasks → Add**
2. Set:
   - Name: "Check Source URLs"
   - Task: `engine.bibliography.tasks.check_source_urls_task`
   - Schedule: daily (e.g., Interval every 86400 seconds, or cron `0 3 * * *`)
   - Kwargs: `{"batch_size": 50, "max_age_days": 7}`

### URL Status in Admin

The Source list view shows a colored URL status badge:
- **OK** (green) — URL responds normally
- **Redirect** (yellow) — URL redirects to a different location
- **Broken** (red) — URL is unreachable
- **Archived** (purple) — URL is broken but a Wayback Machine snapshot exists
- **Unchecked** (gray) — hasn't been checked yet

Filter the list by URL status to find all broken links.

### Proactive Archival

When a Source is created with a URL (or an existing source's URL changes), the `archive_source_url` Celery task submits the URL to the Wayback Machine's Save Page Now API and backfills `url_archive` with an existing snapshot if one is available. Controlled by the `WAYBACK_AUTO_SUBMIT` env var (default on; forced off under test).

### Rendered Bibliography Behavior

When a source's `url_status` is `broken` or `archived` and it has a `url_archive`, the bibliography **renders the archive URL instead of the dead primary URL** (the swap happens in the CSL-JSON handed to citeproc, so every citation style picks it up). The stored `csl_json` keeps the primary URL.

---

## Citation Formatting Engine

### How It Works

The system uses **citeproc-js** — the same CSL processor used by Zotero and Mendeley — running as a Node.js subprocess.

```
Python (formatter.py)
  → subprocess.run(["node", "citeproc_bridge.js"])
    → reads CSL-JSON + style from stdin
    → loads .csl style file from engine/bibliography/styles/
    → runs citeproc-js
    → writes formatted HTML to stdout
  → Python reads result
```

This runs only during the Celery task (on post save), never during page views. Results are cached in `content_html_cached`.

### Available Styles

Bundled in `engine/bibliography/styles/`:

| Style | Filename |
|-------|----------|
| APA 7th Edition | `apa.csl` |
| Chicago Author-Date | `chicago-author-date.csl` |
| Chicago Notes-Bibliography | `chicago-notes-bibliography.csl` |
| MLA | `modern-language-association.csl` |
| IEEE | `ieee.csl` |
| Harvard | `harvard-cite-them-right.csl` |
| Vancouver | `vancouver.csl` |
| Nature | `nature.csl` |

Additional styles can be downloaded from the [CSL Style Repository](https://github.com/citation-style-language/styles) and placed in the `styles/` directory.

### Fallback Behavior

If the Node.js subprocess fails (e.g., node not found, script error), the formatter falls back to simple text-based citations: `(Author, Year)` with a plain-text bibliography. Posts never break.

### Style Resolution

The style used for a post resolves as: **per-post override** (`Post.citation_style`, a curated dropdown in the post admin) → **site default** (`SiteSettings.default_citation_style`) → `apa` as the last-resort fallback.

---

## Public Library, Exports & Further Reading

### The /library/ Page

`/library/` is a public, browsable listing of **every source cited in a published public post** (uncited sources and draft-only citations stay private). Features:

- Search (`?q=`) across title, citation key, container, and authors
- Type facets and a year filter (`?type=article-journal`, `?year=2024`)
- Sort by most-cited (default) or A–Z; per-entry cited-count
- Each entry shows author/year/title (linked to the source URL), its `@key`, type-labeled archived-file links, and "Cited in" links jumping straight to the `#ref-` anchor in each citing post
- Export links for the whole library

### Bibliography Export

Three formats, generated from the structured Source fields (no citeproc round-trip):

- **Full library**: `/library/export.bib`, `/library/export.ris`, `/library/export.json` — publicly cited sources only
- **Per post**: `/posts/<slug>/bibliography.bib` (or `.ris` / `.json`) — that post's citations in document order; respects post visibility (staff can export drafts), 404 when a post has no citations

Converters live in `engine/bibliography/export.py`; CSL-JSON is the stored native format, BibTeX/RIS are mapped from the CSL type taxonomy.

### Copy-Reference Buttons

Every bibliography entry carries a clipboard button (visible on hover) that copies the formatted reference as plain text. Handled by `citation-tooltip.js`; entries render the button at post re-render time, so run `regenerate_html_cache` once after deploying to add it to existing posts.

### Further Reading

A curated, manually ordered reading list per post — sources you recommend but don't cite. Managed in the post admin's **Further Reading (curated)** inline (source autocomplete, position, optional note). Rendered as a distinct `#further-reading` section directly after References (or standing alone on posts with no citations), with the same visual treatment: archive-aware links, type-labeled file links, and notes as annotations. Editing the inline queues a re-render automatically.

---

## Deployment Notes

### Docker

The Dockerfile uses a multi-stage build:

- **Stage 1** (`node:22-slim`): Builds frontend CSS/JS assets via npm and installs citeproc-js production dependencies
- **Stage 2** (`python:3.14-slim`): Copies the Node.js binary from stage 1 (for citeproc subprocess), copies built assets and citeproc node_modules, installs Python deps, runs collectstatic

No new Railway services are needed. The Node subprocess runs inside the existing web/worker containers.

### Frontend Assets

CSS/JS dist files are **gitignored** and built inside Docker. For local development:
```bash
npm run dev    # Watch mode — rebuilds on change
npm run build  # One-off production build
```

### New Dependencies

| Dependency | Purpose | Where |
|-----------|---------|-------|
| `citeproc` (npm) | Citation formatting engine | `engine/bibliography/package.json` |
| `pyzotero` (pip) | Zotero API client | `pyproject.toml` |
| `pypdf` (pip) | PDF text extraction for search | `pyproject.toml` |

### Environment Variables

No new environment variables are required. Zotero credentials are stored in SiteSettings (database), not env vars.

---

## Remaining Steps

**All complete.** The six items originally tracked here have shipped:

1. **Citation style from SiteSettings** — done; see [Style Resolution](#style-resolution) (per-post override → site default → `apa`).
2. **File hash deduplication on upload** — done; `Source.save()` hashes and dedups (see [File Deduplication](#file-deduplication)).
3. **Proactive Wayback Machine archival** — done; `archive_source_url` task fires on source create / URL change (see [Proactive Archival](#proactive-archival)).
4. **PostCitation annotations in bibliography** — done; annotations render below their reference entry, and annotation edits queue a re-render.
5. **Source in search** — done; `search_sources()` runs in the search orchestrator, `search_vector` refreshes on save (and via `rebuild_search_vectors`). Only sources cited in visible posts surface; results link to the citing post's `#ref-` anchor.
6. **Archive URL preference for broken links** — done; see [Rendered Bibliography Behavior](#rendered-bibliography-behavior).

Also fixed along the way: the citation escaper no longer mangles email addresses (`user@example.com` was previously parsed as a narrative citation).

A final hardening pass added: per-host rate limiting on all outbound fetches (see [Auto-Populating Metadata](#auto-populating-metadata)), `soft_time_limit`/`time_limit` on every bibliography Celery task, unit tests for the link checker / Zotero sync / metadata resolver internals, a fix so never-checked URLs are prioritized ahead of stale ones in the batch checker (Postgres sorts NULLs last), and removal of the dead pre-Pandoc citation-extraction path (`extract_citations` — superseded by the escaper → Pandoc → renderer pipeline).

---

## Future Improvements

These are enhancements from the original design spec (Section 13 / Phase 8) that would add polish and additional capabilities. (Bibliography export, the copy button, the public library page, public citation metrics, and Further Reading all shipped — see [Public Library, Exports & Further Reading](#public-library-exports--further-reading).)

### Source Collections

A `SourceCollection` model with M2M to Source for thematic groupings (e.g., "Climate Science", "Philosophy of Mind"). Useful for curated reading lists independent of which posts cite them.

### Enhanced Semantic HTML

Extend ARIA roles: `doc-noteref` on inline citations (already present), `doc-biblioref` on bibliography entries, proper `aria-label` on interactive elements (tooltips, copy buttons), full keyboard navigation support.

### File Archive — Next Steps

The multi-file `SourceFile` model shipped (see [Archiving Source Files](#archiving-source-files)); still open:

- **Expanded format support**: EPUB, TXT/MD, RTF, JATS XML, LaTeX bundles, ODT, PPTX, DjVu, PostScript, MHTML/WARC (current accepted set: PDF, DOC/DOCX, HTML).
- **PDF normalization**: convert DOCX/ODT/RTF to a PDF view-rendition (LibreOffice headless in the worker image) so every source has a browser-readable artifact next to the original.
- **True private files**: `is_public` currently gates rendering only; storage-level privacy needs a non-public bucket or signed-URL storage class.

### Domain-Specific URL Metadata

Extend the URL resolver with specialized extractors for:
- **arXiv**: Extract paper ID, authors, abstract from arXiv API
- **YouTube**: Extract video title, channel, duration from oEmbed
- **GitHub**: Extract repo description, stars, language from GitHub API
- **Wikipedia**: Extract article summary from Wikipedia API
