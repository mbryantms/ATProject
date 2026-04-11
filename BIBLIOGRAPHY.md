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
9. [Deployment Notes](#deployment-notes)
10. [Remaining Steps](#remaining-steps)
11. [Future Improvements](#future-improvements)

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

### Viewing Citations on a Post

In the Post admin, the **Cited Sources** inline shows all sources cited in that post's content, with their citation key and position. The **annotation** field is editable here — use it for per-post notes about a source.

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

### From DOI

When a Source has a DOI:
1. Select it in the Source admin
2. Action → **"Fetch metadata from DOI"**
3. The system queries the CrossRef API, which returns CSL-JSON natively
4. Only **empty** fields are filled (existing data is preserved)

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

### Uploading Files

In the Source admin, expand the **File Archive** section and use the file upload widget to attach a PDF, HTML, or EPUB file.

Files are stored in Cloudflare R2 under the `sources/YYYY/MM/` path via the existing django-storages backend.

### [PDF] Links in Bibliography

When a Source has an `archived_file`, the rendered bibliography entry automatically includes a `[PDF]` link:

```html
<li id="ref-smith2024" class="reference-entry">
  <span class="reference-text">Smith, J. (2024). Climate Change...</span>
  <a href="/media/sources/2024/01/paper.pdf" class="reference-file-link">[PDF]</a>
</li>
```

### File Deduplication

The `archived_file_hash` field exists for SHA-256 deduplication but is **not yet wired up automatically** — see [Remaining Steps](#remaining-steps).

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
# Check 50 URLs (oldest-checked first, skip recently checked)
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

### Rendered Bibliography Behavior

When a source's `url_status` is `broken` or `archived` and it has a `url_archive`, the archive URL is available on the model for future use in rendering. Currently the bibliography renderer uses the primary URL from the CSL-JSON; preferring the archive URL when broken is a planned improvement.

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

### Current Limitation

The citation style is currently hardcoded to `apa` in the postprocessor. The `default_citation_style` field exists in SiteSettings but isn't read yet — see [Remaining Steps](#remaining-steps).

---

## Deployment Notes

### Docker

The Dockerfile uses a multi-stage build:

- **Stage 1** (`node:22-slim`): Builds frontend CSS/JS assets via npm and installs citeproc-js production dependencies
- **Stage 2** (`python:3.13-slim`): Copies the Node.js binary from stage 1 (for citeproc subprocess), copies built assets and citeproc node_modules, installs Python deps, runs collectstatic

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

### Environment Variables

No new environment variables are required. Zotero credentials are stored in SiteSettings (database), not env vars.

---

## Remaining Steps

These are concrete items that should be completed to finish the system as designed.

### 1. Wire up citation style from SiteSettings

The `default_citation_style` field exists in SiteSettings but the citation renderer postprocessor hardcodes `style="apa"`. It should read the setting and pass it to the formatter.

**Files:** `engine/markdown/postprocessors/citation_renderer.py` (line with `style="apa"`)

### 2. File hash deduplication on upload

The `archived_file_hash` field exists on Source but is never populated. On `save()` when `archived_file` changes, compute SHA-256 and check for duplicates.

**Files:** `engine/models/source.py` (add to `save()` or a signal)

### 3. Proactive Wayback Machine archival

`submit_to_wayback()` exists in `link_checker.py` but is never called automatically. Should fire when a Source is created with a URL, or when a URL is added to an existing Source.

**Files:** Add a post_save signal on Source, or call in `save()`

### 4. Render PostCitation annotations in bibliography

The `annotation` field on PostCitation is editable in the admin but not rendered in the bibliography HTML. When present, it should appear below the formatted reference entry.

**Files:** `engine/bibliography/renderer.py`, `engine/markdown/postprocessors/citation_renderer.py`

### 5. Include Source in search

Source has a `search_vector` field but no task updates it and the search service doesn't query it. Add a `search_sources()` function and integrate into the search orchestrator.

**Files:** `engine/search/service.py`, `engine/bibliography/tasks.py` or `engine/tasks.py`

### 6. Prefer archive URL in bibliography when source URL is broken

When `url_status` is "broken" and `url_archive` is set, the bibliography should link to the archive URL instead of the dead primary URL.

**Files:** `engine/markdown/postprocessors/citation_renderer.py`, `engine/bibliography/renderer.py`

---

## Future Improvements

These are enhancements from the original design spec (Section 13 / Phase 8) that would add polish and additional capabilities.

### Bibliography Export

Add an endpoint to export a post's bibliography or the full source library in standard formats:
- **BibTeX** — universal interchange format
- **RIS** — used by many reference managers
- **CSL-JSON** — native format, already stored on each Source

Suggested URL: `/posts/{slug}/bibliography.{format}` or `/api/v1/bibliography/export/`

### Citation Copy Button

Add a small clipboard icon to each bibliography entry. Click copies the formatted reference text. Straightforward JS addition to `citation-tooltip.js`.

### Public Library Page

A browsable, searchable page at `/library/` listing all sources cited in published posts. Filterable by type, year, author. Functions as a reading list and provides SEO value.

### Source Collections

A `SourceCollection` model with M2M to Source for thematic groupings (e.g., "Climate Science", "Philosophy of Mind"). Useful for curated reading lists independent of which posts cite them.

### Citation Metrics

Track and display how many posts cite each source. Surface in admin for library management (`citation_count` as an annotated query) and optionally on the public library page.

### Further Reading Section

A separate `PostFurtherReading` model for sources the author recommends but doesn't directly cite. Rendered as a distinct section after the bibliography.

### Per-Post Citation Style Override

Add a `citation_style` field to the Post model. When set, override the site-wide default for that post. Useful for posts that follow a specific journal's conventions.

### Enhanced Semantic HTML

Extend ARIA roles: `doc-noteref` on inline citations (already present), `doc-biblioref` on bibliography entries, proper `aria-label` on interactive elements (tooltips, copy buttons), full keyboard navigation support.

### Zotero Attachment Download

During Zotero sync, download PDF attachments via the Zotero API and store them as the source's `archived_file`. The `pyzotero` client supports attachment download.

### Domain-Specific URL Metadata

Extend the URL resolver with specialized extractors for:
- **arXiv**: Extract paper ID, authors, abstract from arXiv API
- **YouTube**: Extract video title, channel, duration from oEmbed
- **GitHub**: Extract repo description, stars, language from GitHub API
- **Wikipedia**: Extract article summary from Wikipedia API
