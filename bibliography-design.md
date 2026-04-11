# Bibliography & Citation System — Feature Specification

## Purpose

Add a complete bibliography and citation system to this application. The system should allow an author to maintain a library of citable sources, reference them inline within markdown-formatted post content, and render both inline citations and a per-post bibliography section that matches the site's visual design. The system should integrate tightly with Zotero, handle source archival, combat link rot, and provide a rich admin experience.

---

## 1. Source Library

### End State

A centralized, universal source library exists in the database. Every citable item — journal articles, books, chapters, web pages, blog posts, videos, reports, legislation, software, datasets, interviews, and any other reference type — is stored as a single record in a unified model. There are no separate models per source type.

### Recommendations

- Use the CSL (Citation Style Language) type taxonomy as the source type vocabulary. CSL defines roughly 60 types and is the standard used by Zotero, Mendeley, Pandoc, and every major reference manager. Adopting it ensures interoperability rather than inventing a custom taxonomy.
- Store both structured, queryable fields (title, authors, DOI, URL, dates, etc.) and a complete CSL-JSON representation on each record. The structured fields power admin search, filtering, and display. The CSL-JSON blob is the canonical input for citation formatting engines. Keep these in sync automatically.
- Author/editor/translator data should be stored as structured JSON following the CSL name-variable specification (supporting both personal names with family/given fields and organizational/literal names).
- Date fields should use the CSL date-parts format to support partial dates (year-only, year-month, full date) which are common in bibliographic records.
- Each source must have a globally unique, human-readable citation key (e.g., `smith2024climate`). This key is what authors type in their markdown content. It must be auto-generated from author + year + title but editable. Once set and used in any published content, it must never change automatically — it is the stable contract between content and data.
- Sources are reusable across all posts. A source cited in one post is the same record cited in another. There is no per-post duplication of source data.

---

## 2. Markdown Citation Syntax & Rendering

### End State

Authors write citations in their post's markdown content using a concise, readable syntax. The rendering pipeline resolves these references against the source library and outputs styled inline citations in the published HTML.

### Recommendations

- Use Pandoc-compatible citation syntax: `[@key]`, `[@key, pp. 42-56]`, `[@key1; @key2]`, `@key` (narrative/in-text), `[-@key]` (suppress author). This syntax is a well-established standard, portable to other systems, and documented extensively.
- The citation processing should integrate into the existing markdown rendering pipeline as a custom extension — not as a separate rendering pass or a replacement of the existing markdown engine. It should work within whatever preprocessor/postprocessor architecture the project already uses.
- Each inline citation in the rendered HTML should be an anchor element linking to the corresponding entry in the post's bibliography section. It should carry a data attribute containing the full formatted reference text, which powers the tooltip (see Section 7).
- Citation resolution must be done in a single batched database query per render — collect all citation keys from the content, resolve them all at once. Never one query per citation.
- If a citation key doesn't resolve to a known source, render it visibly as an unresolved reference (e.g., `[??key]`) rather than failing silently or crashing the page.
- Note that this entire reference section should not conflict with the existing footnotes / sidenotes features.

---

## 3. Bibliography Section

### End State

Each post that contains citations has a "References" section appended at the end of its rendered content. This section lists only the sources actually cited in that post, formatted according to the selected citation style.

### Recommendations

- The bibliography is auto-generated from the citations present in the post content. Authors never manually maintain a bibliography list — they just write `[@key]` in their markdown and the system handles the rest.
- The system should maintain a join/through table linking posts to sources. This table is derived from the rendered content (the markdown is the source of truth), but having it in the database enables queries like "which posts cite this source?" and "show all sources cited across the site."
- Only sources with at least one `[@key]` reference in the post content appear in the bibliography. Unreferenced sources are excluded.
- If a post contains zero citations, no bibliography section is rendered.
- Each bibliography entry should have an HTML `id` anchor so that inline citations can link directly to it, and clicking a citation scrolls to and briefly highlights the corresponding entry.

---

## 4. Citation Style Support

### End State

The system can format both inline citations and bibliography entries in any of the thousands of standard citation styles (APA, Chicago, MLA, IEEE, Vancouver, Nature, Harvard, Turabian, and journal-specific styles).

### Recommendations

- Use a CSL (Citation Style Language) processor as the formatting engine — either `citeproc-js` or `citeproc-py`, as evaluated in Section 10. Both consume CSL-JSON source data plus any `.csl` style file to produce correctly formatted output. The CSL style repository contains 10,000+ styles covering virtually every journal and publisher format.
- This is strongly preferred over building custom formatting logic. Even a single style like APA has hundreds of formatting edge cases (multiple authors, institutional authors, missing dates, editions, translated works, legal citations, etc.) that a CSL processor already handles correctly.
- The system should have a concept of a site-wide default citation style, with the option for individual posts to override it.
- Store the available styles as database records pointing to CSL files, with a management command to load/update them from the CSL style repository (available as the `citeproc-py-styles` Python package or directly from the `citation-style-language/styles` GitHub repository).

---

## 5. Zotero Integration

### End State

The system has deep, bidirectional-aware integration with Zotero. Sources can be imported from a Zotero library (personal or group) either in bulk or individually. The system tracks which sources originated from Zotero and supports incremental sync to pick up changes.

### Recommendations

- Use `pyzotero` as the Zotero API client. It is the officially recognized Python wrapper for the Zotero Web API v3 and handles pagination, rate limiting, authentication, and all Zotero item types.
- Implement incremental sync using Zotero's library versioning system. Each source record should store its Zotero key and version number. On sync, only fetch items modified since the last known version. This avoids re-downloading the entire library on every sync.
- Zotero items should be mapped to the universal source model, not stored in a separate Zotero-specific model. The Zotero key is just an identifier field on the source record that enables sync tracking.
- When importing from Zotero, request data in CSL-JSON format directly (pyzotero supports `format='csljson'`), which maps cleanly onto the source model's CSL-JSON field. Also store the raw Zotero JSON for any fields CSL doesn't cover (Zotero-specific tags, notes, related items).
- When a Zotero item has PDF attachments, download them via the Zotero API and store them as the source's archived file (see Section 11).
- The sync should be runnable as both a management command and an async background task (for scheduled periodic sync).
- The admin interface should include a "Sync from Zotero" action and a sync status indicator showing the last sync time and any errors.
- Never auto-overwrite the `citation_key` field during sync — it may have been customized and is used in published content.

---

## 6. Theme-Matched Styling

### End State

Inline citations, the bibliography section, and citation tooltips all visually match the site's existing design system — colors, typography, spacing, and any distinctive visual treatments used elsewhere on the site.

### Recommendations

- Inline citations should be styled as subtle, recognizable links — visually distinct from regular hyperlinks but not disruptive to reading flow. They should have a hover state.
- The bibliography section should have a clear visual separator from the post content (a rule, heading, or spacing change). Entries should use a hanging indent, which is the universal convention for bibliographies and improves readability.
- When a user clicks an inline citation and scrolls to the bibliography entry, that entry should briefly highlight (a fade-in/fade-out background color) to orient the reader.
- All CSS should use the project's existing design tokens, variables, or conventions rather than introducing hardcoded values.

---

## 7. Citation Tooltips

### End State

Hovering over an inline citation displays a tooltip showing the full formatted reference for that source. On mobile, tapping the citation shows the same information. The tooltip matches the site's visual theme.

### Recommendations

- The tooltip content should be the fully formatted bibliography entry for that source in the active citation style. This is the same text that appears in the bibliography section.
- Store the tooltip content as a data attribute on the citation's HTML element. The rendering pipeline already has access to the formatted reference when building the inline citation — embed it there so the tooltip doesn't require an additional network request.
- Implement the tooltip using whatever JavaScript framework the project already uses for interactive UI components. If Alpine.js is in use, build it as an Alpine component. If vanilla JS or another framework is used, use that. Do not introduce a separate tooltip library.
- Desktop behavior: show on hover with a small delay (100-150ms) to prevent flicker during casual mouse movement. Dismiss on mouse leave.
- Mobile behavior: show on tap. Dismiss on tap elsewhere or on scroll.
- Position the tooltip above the citation by default, flipping below if the citation is near the top of the viewport.
- The tooltip should include a semi-transparent, slightly blurred background consistent with any glassmorphism or card-style treatments used elsewhere in the theme.

---

## 8. Universal Citation Keys & Collision Avoidance

### End State

Citation keys are globally unique identifiers that work consistently across all posts without collisions. The same `[@key]` always refers to the same source, regardless of which post it appears in.

### Recommendations

- Enforce uniqueness on the citation key field at the database level.
- Auto-generate keys using a deterministic pattern: first author's family name (lowercased) + year + first significant word of title (lowercased). Example: `smith2024climate`.
- When the auto-generated key collides with an existing one, append a letter suffix: `smith2024a`, `smith2024b`. The generation logic must check for existing keys and find the next available suffix.
- Once a citation key is created, it is considered immutable for the purposes of automatic processes. Zotero sync, metadata enrichment, and other automated updates must never change a citation key. Manual edits through the admin are allowed but should display a warning if the key is referenced in any published content.
- The resolution mechanism looks up keys against the global source table, not against any per-post scope. This is what makes keys universal — there is one namespace.

---

## 9. Admin Interface

### End State

The Django admin provides a complete, efficient interface for managing sources, with auto-population capabilities that minimize manual data entry.

### Recommendations

**Source management:**
- The source admin should have organized fieldsets grouping related fields (identity, metadata, publication details, identifiers, files, link health, Zotero data).
- List display should show the citation key, truncated title, primary author, year, source type, verification status, and URL health status.
- Filters for source type, verification status, URL health status, and tags.
- Full-text search across citation key, title, authors, DOI, ISBN, and abstract.
- Fields that are auto-populated or system-managed (CSL-JSON, Zotero raw data, file hashes, URL check timestamps) should be read-only.

**Auto-population from Zotero import:**
- When sources are imported via Zotero sync, all available fields should be populated from the Zotero data without manual intervention.

**Auto-population from DOI:**
- When a DOI is entered, the system should fetch metadata from CrossRef or DataCite and populate all available fields (title, authors, journal, volume, issue, pages, publisher, dates). CrossRef returns CSL-JSON natively, making this mapping straightforward.
- This should be triggerable from the admin form — either via an explicit "Fetch metadata" button or automatically on save when a DOI is present and core fields are empty.

**Auto-population from URL:**
- When a URL is entered, the system should extract metadata from the page: OpenGraph tags, Dublin Core metadata, Schema.org JSON-LD, and standard HTML meta tags (author, description, published date).
- For known domains (arXiv, YouTube, GitHub, etc.), apply domain-specific extraction logic that maps to the appropriate source type and fields.

**Post integration:**
- The post admin should show an inline or sidebar listing of all sources cited in that post's content, derived from the `PostCitation` records.
- Source references should use autocomplete for easy lookup.

**Admin actions:**
- Bulk URL checking
- Bulk Zotero re-import
- Bulk CSL-JSON regeneration
- Bulk source archiving

---

## 10. Industry-Standard Libraries

### End State

The system uses well-maintained, standards-based libraries for citation formatting and Zotero integration rather than custom implementations of these complex domains.

### Recommendations

#### Citation Formatting Engine — `citeproc-js` vs `citeproc-py`

This is the most consequential library decision in the system. Both are implementations of the CSL specification, but they differ dramatically in completeness and real-world validation. The implementing model should evaluate the project's deployment constraints and choose one of the following approaches.

**Option A: `citeproc-js` via `citeproc-js-server`**

`citeproc-js` is the reference CSL implementation. It is the engine used by both Zotero and Mendeley for citation formatting, passes over 1,300 integration tests, and handles multilingual content and legal citations with precision no other implementation matches. It has over a decade of production use and field testing.

Zotero maintains `citeproc-js-server`, a Node.js-based HTTP microservice that accepts CSL-JSON data via POST and returns formatted citations and bibliographies. The Django application would call this service internally. This approach gives you the exact same formatting output that Zotero produces — which matters for consistency when sources are imported from Zotero.

The tradeoff is operational: you are running and maintaining a separate Node.js process alongside the Django application. If the project's deployment environment can accommodate a sidecar service (e.g., a second process in the same container, a separate container, or a persistent background service), this is the stronger choice. The rendered output can and should be cached aggressively to minimize how often the service is actually called. Consider if this shoudl or could be a separate railway service.

**Option B: `citeproc-py` + `citeproc-py-styles`**

`citeproc-py` is a pure Python CSL processor. It is simpler to deploy — just a pip install with no external binary or service. However, it passes only ~60% of the CSL test suite. Its own documentation acknowledges multiple unimplemented features including punctuation handling and certain disambiguation behaviors. It is at major version 0, its API is not yet considered stable, and it is 100% volunteer-maintained.

For a blog that primarily uses common styles (APA, Chicago, MLA, IEEE), the ~40% of failing tests are unlikely to surface — they mostly involve obscure edge cases around punctuation squeezing, multilingual sort keys, and legal citation formats. But the gap is real, and it means output may differ from what Zotero would produce for the same source and style, which could be confusing when a source is imported from Zotero and then rendered differently.

This option is appropriate if adding a Node.js dependency is untenable for the project.

**Option C: `citeproc-js` via Node subprocess**

A middle ground: invoke Node.js with a small citeproc-js script as a subprocess, passing CSL-JSON via stdin and receiving formatted HTML via stdout. No persistent server to maintain, but Node.js must be available in the deployment environment. Adds subprocess overhead per render, but caching eliminates this for repeat renders. This is simpler to operate than a full microservice but gives you the same formatting correctness as Option A.


#### Other Potential Libraries

**Use:**
- `pyzotero`: Zotero API access. Officially recognized Python wrapper for the Zotero Web API v3, handles the full API surface, actively maintained.
- `citeproc-py-styles` (if using citeproc-py): Bundles the full CSL style repository as a Python package.

**Do not use unless the project already does:**
- `pypandoc` / Pandoc: Only consider if the project already uses Pandoc for markdown rendering. Adding Pandoc solely for citations is unnecessary overhead when a dedicated CSL processor (either JS or Python) is available.
- `bibtexparser`: Only needed if importing bibliographies from BibTeX files outside of Zotero. Since Zotero can export CSL-JSON directly, this adds no value for the primary workflow.

**Defer to the implementing model's judgment:**
- PDF text extraction library choice (pdfplumber, pypdf, etc.)
- URL fetching and parsing library choice
- Any async task framework integration details

---

## 11. Source File Ingestion & Storage

### End State

The system can store copies of the source documents themselves (PDFs, single-file HTML snapshots) alongside the bibliographic metadata. These files are available for reference and serve as insurance against link rot.

### Recommendations

- Support at minimum PDF and single-file HTML formats. EPUB is a nice-to-have for book sources.
- Store files in whatever object storage the project already uses for media assets. Do not introduce a new storage backend.
- Deduplicate files by computing a hash (SHA-256) on upload. If a file with the same hash already exists, link to the existing file rather than storing a duplicate.
- Source files should be uploadable through the admin interface, importable from Zotero attachments during sync, and receivable from the archiving system.
- Provide a way to serve or link to these files from the bibliography section — e.g., a `[PDF]` link next to the formatted reference for sources that have a stored file.
- Optionally extract text from PDFs for full-text search indexing, but this should be done asynchronously as a background task, not during upload or page render.

---

## 12. Link Rot Detection & Remediation

### End State

The system periodically checks all source URLs for availability and takes corrective action when links break. Broken links are flagged, and the system attempts to locate archived versions.

### Recommendations

- Implement a periodic background task that checks source URLs using HTTP HEAD requests. Stagger checks across time and rate-limit outbound requests to avoid hammering external servers.
- Track URL status (ok, redirect, broken, archived, unchecked), last check timestamp, and check count on each source record.
- Check the oldest-checked URLs first so that all URLs are eventually covered.
- When a URL is found broken:
  1. If the source has a DOI, the DOI is the permanent link — update the primary URL to the DOI resolver URL.
  2. Check the Wayback Machine API (`https://archive.org/wayback/available?url={url}`) for an existing snapshot.
  3. If a project-specific archiving system exists, check there as well.
  4. Store any archive URL found on the source record.
  5. In the rendered bibliography, prefer the archive URL when the primary URL is broken.
- Surface broken/unchecked URLs in the admin interface — a filtered view or dashboard showing link health across the source library.
- Proactively archive source URLs at the time of source creation, not just when rot is detected. Submit to the Wayback Machine's Save Page Now API (`https://web.archive.org/save/{url}`) as a baseline.

---

## 13. Additional Recommended Systems

These are enhancements that round out the bibliography feature into a complete, professional system.

### 13.1 DOI & ISBN Metadata Resolution

Beyond the admin auto-populate feature, provide a reusable service that resolves DOIs via CrossRef and ISBNs via Open Library or Google Books. This service should be callable from sync tasks, import pipelines, and the admin interface. CrossRef in particular returns CSL-JSON natively, making it the ideal metadata source for journal articles and conference papers.

### 13.2 Annotated Bibliographies

Allow per-post annotations on cited sources — a brief note explaining why the source is relevant or what it contributes. Store this on the post-source join record. Render it below the formatted reference in the bibliography section when present.

### 13.3 Further Reading Section

Support a separate "Further Reading" or "Related Sources" list on posts — sources the author recommends but doesn't directly cite in the text. This is a separate relationship from the citation-derived bibliography and is manually curated.

### 13.4 Bibliography Export

Provide endpoints or buttons to export a post's bibliography (or the full source library) in standard formats: BibTeX, RIS, and CSL-JSON. These are the three formats that every reference manager can import.

### 13.5 Citation Copy Button

On each bibliography entry, include a small button to copy the formatted reference to the clipboard. This is a common feature on academic sites and is trivial to implement with existing JS.

### 13.6 Public Bibliography/Library Page

Create a browsable, searchable page listing all sources in the library (or all sources cited in published posts). Filterable by type, year, author, and tag. This functions as a reading list or reference library for the site and provides SEO value.

### 13.7 Citation Metrics

Track and display how many posts cite each source. Surface this in the admin for library management and optionally on the public bibliography page.

### 13.8 Source Collections

Allow grouping sources into thematic collections (e.g., "Climate Science," "Philosophy of Mind") independent of which posts cite them. Useful for curated reading lists and admin organization.

### 13.9 Semantic HTML & Accessibility

Use appropriate ARIA roles on bibliography markup: `doc-bibliography` on the references section, `doc-noteref` on inline citation links, proper `id` anchors for navigation between citations and bibliography entries. All interactive elements (tooltips, copy buttons) should have accessible labels and keyboard support.

---

## 14. Implementation Sequencing

Build in this order so that each phase produces a functional increment:

1. **Source model & admin** — the data layer and basic CRUD
2. **Citation rendering pipeline** — markdown extension + citeproc-py formatting + bibliography generation
3. **Styling & tooltips** — visual integration with the site theme
4. **Zotero integration** — import, sync, attachment handling
5. **Admin auto-population** — DOI, URL, and ISBN metadata fetching
6. **Source file storage** — upload, deduplication, serving
7. **Link rot detection** — URL checking, archiving, remediation
8. **Polish** — exports, public bibliography page, collections, metrics

---

## 15. Potential Library Dependencies

- `pyzotero` — Zotero API client

**Citation engine (choose one based on Section 10 evaluation):**
- Option A/C: `citeproc-js` (via `citeproc-js-server` microservice or Node subprocess) — complete CSL implementation, 1,300+ passing tests, same engine used by Zotero and Mendeley. Requires Node.js in the deployment environment.
- Option B: `citeproc-py` + `citeproc-py-styles` — pure Python, simpler to deploy, but ~60% CSL test pass rate with known gaps in punctuation handling and disambiguation. Acceptable for common citation styles on a blog.

**Everything else** (HTTP clients, PDF libraries, async task runners, storage backends) should use whatever the project already has installed. Do not introduce new infrastructure dependencies without confirming they are necessary.