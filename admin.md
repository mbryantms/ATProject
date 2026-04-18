Admin Authoring Workflow Improvement Plan
Current State Summary
Strengths: 8 well-organized fieldsets (engine/admin/post.py:482-574), rich asset inline with preview + copy-to-clipboard (engine/admin/post.py:23-182), revision diff viewer with restore (engine/admin/post.py:415-463), comprehensive model-level help_text, 23+ markdown postprocessors.

Core gaps: plain <textarea> for content (no editor, no preview, no validation), no discoverability of custom syntax (admonitions, @asset:key, [@citekey], internal links), unlabeled certainty/importance/citation_style choices.

Plan — grouped by impact
Phase 1 — Discoverability (high ROI, low risk)
1.1 Markdown cheatsheet panel on the Post change form

New collapsed fieldset "Markdown Reference" above content_markdown, or a floating side-panel via admin template override at templates/admin/engine/post/change_form.html (new file extending admin/change_form.html).
Tabbed content: Basics (headings, emphasis, lists, links, code) / Admonitions (the 4 types from engine/markdown/postprocessors/admonition_enhancer.py) / Assets (@asset:key, @alias) / Citations ([@key], [@key, pp. 42], [-@key], @key) / Advanced (footnotes [^1], math $…$ / $$…$$, epigraph divs, columns, marked dates).
Each row: syntax on the left (copyable), rendered example on the right. Source of truth: enumerate from the postprocessor modules so it stays in sync.
1.2 Inline help_text upgrades on engine/admin/post.py

content_markdown: replace "Author in markdown only" with a 1-line summary + a link to the cheatsheet anchor.
citation_style: convert from free-text to a ChoiceField populated by scanning installed CSL styles (or a curated allowlist: chicago-author-date, apa, mla, ieee, nature…). Keep the DB field as CharField — only the admin form gets the dropdown.
certainty, importance, completion_status: add human-readable help_text describing the 1–10 scale and what each end means.
show_toc, first_line_caps: add a short preview thumbnail in help_text, or at minimum a one-line description of the visible effect.
1.3 Asset reference helper — promote from hidden to prominent (engine/admin/post.py:715-837)

Today it only appears on change (after save). Move it to the top of the Content fieldset and, on add, render a short placeholder explaining how to attach assets first.
Add the post's currently-orphaned @asset:key references detected in content_markdown as a warning list under the helper ("Referenced but not attached: @foo, @bar").

Phase 2 — Validation & feedback (prevents silent failures)
2.1 Save-time markdown linter

Override PostAdmin.save_model() (or ModelForm.clean_content_markdown) to run a dry-render pass and collect warnings:
Unresolvable @asset:key / @alias → warn via messages.warning.
Unresolvable [@citekey] → warn (the renderer already produces [??key]; surface that count before the author sees it on the live page).
Internal links (/posts/slug/) pointing at non-existent slugs.
Malformed admonition fences (::: without matching close).
Non-blocking — these are warnings, not errors, so authors can still save drafts.
2.2 "Preview draft" button on the change form

Top-right submit-row button that saves then opens the post detail page with ?preview=1 + visibility=PRIVATE bypass for the author. Requires a small view-level guard in engine/views/.
Cheaper alternative: a "Render preview" AJAX endpoint that returns HTML from the existing markdown pipeline and renders it in a modal on the change form — no DB write, no routing changes.

Phase 3 — Editor surface (higher effort, transformative)
3.1 Swap the textarea for EasyMDE or CodeMirror 6

Load as an admin-only widget on content_markdown via formfield_for_dbfield override at engine/admin/post.py:367-398.
Minimum toolbar: bold / italic / heading / list / link / image / code / quote / admonition-template / citation-template / preview-toggle.
"Insert asset" and "Insert citation" buttons open a modal with autocomplete over the attached PostAsset set and the Source model respectively; on select, inserts the correct @alias or [@key] at cursor.
Persist editor state (cursor, scroll, preview-open) in localStorage keyed by post id so the form survives reloads.

3.2 Live preview pane

Side-by-side split view inside the editor; debounced POST to the preview endpoint from 2.2; renders inside a sandboxed iframe so site CSS applies.

Phase 4 — Source/citation workflow (engine/admin/source.py)
4.1 Citation insertion from the post admin

Read-only PostCitationInline already shows what the rendered content cites (engine/admin/post.py:247-271). Add a sibling editor-side widget: a searchable source picker above content_markdown that inserts [@key] at cursor (ties into 3.1's "Insert citation" button).
Show each source's citation key, year, author, and truncated title — currently the autocomplete only shows the key.
4.2 Surface citation style choices

Add a small "?" tooltip next to citation_style listing the 4–6 most common styles with a sample formatted citation each, rendered server-side from a fixture source.
Phase 5 — Asset workflow (engine/admin/post.py:23-182)

5.1 Richer asset autocomplete

Override the autocomplete result template to show thumbnail + type badge + key, not just the key string. Register a custom AutocompleteJsonView on AssetAdmin.
5.2 Bulk attach from markdown

"Scan content for @asset:key references and attach" admin action — reduces the manual add-asset step when importing existing markdown.
5.3 Inline previews of overrides

When custom_caption / custom_alt_text is set on a PostAsset, render a small "as it will appear" preview beside the inputs.

Phase 6 — Small cleanups
Move content_html_cached out of the "Advanced" fieldset entirely — it's an internal cache; make it readonly and collapse it further, or hide from the form and expose only via a "Regenerate cache" admin action.
table_of_contents is auto-generated; same treatment.
search_vector is already auto-managed but still appears in the model — confirm it's not on the form; if so, exclude.
version, published_by, last_edited_by should be readonly on the form (auto-set via save_model), not editable fields.
Consolidate hero_image_url / og_image_url help_text to explain the fallback chain explicitly: hero → og → first image in content.

Recommended sequencing
Ship Phase 1 first — pure template/help_text/form work, no model changes, immediate author impact.
Phase 2 alongside Phase 1 — same PR if scope allows.
Phase 5.1 + 6 as a "polish" PR — small, safe, reviewable.
Phase 3 as its own PR — introduces a JS dependency and needs design review.
Phases 4.1 + 5.2 ride on Phase 3's editor infrastructure.
Want me to start on Phase 1 (cheatsheet + help_text upgrades + orphaned-reference warning)? That's the highest-leverage chunk and touches only admin code.