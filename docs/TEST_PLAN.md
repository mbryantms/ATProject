# Comprehensive Testing Implementation Plan

## Project Overview
The project is a Django 5.2 application centered on the `engine` app, which manages editorial content, an asset pipeline, markdown rendering, and backlink analysis. Domain models cover posts with extensive metadata, soft deletion, taxonomy, and an advanced asset management system with renditions and metadata extraction.【F:engine/models.py†L23-L415】【F:engine/models.py†L478-L1500】 A bespoke markdown pipeline with preprocessors and postprocessors enriches content presentation, while Celery tasks, signals, and management commands coordinate asynchronous processing and link maintenance.【F:engine/markdown/renderer.py†L10-L37】【F:engine/tasks.py†L30-L200】【F:engine/signals.py†L17-L185】 The primary user-facing view is a post detail page that enforces publication rules and surfaces backlinks.【F:engine/views.py†L36-L93】

## Goals & Coverage Targets
- Reach ≥95% statement coverage for the Python backend, with explicit coverage tracking for models, utilities, management commands, tasks, and template tags.
- Exercise all critical paths: publication states, soft deletion, asset processing, markdown enhancements, backlink extraction, and admin workflows.
- Ensure markdown pipeline correctness through regression-style snapshot tests and targeted unit tests for each processor.
- Validate Celery tasks and management commands via synchronous execution and dependency mocking to avoid external services.
- Capture template-level regressions by testing template tags, inclusion tags, and key view templates.

## Tooling & Infrastructure
1. **Testing framework**: Adopt `pytest` with `pytest-django` to simplify fixtures and parametrization while remaining compatible with existing Django settings.
2. **Coverage**: Configure `coverage.py` via `pyproject.toml` or `.coveragerc` to measure Python modules under `engine`, `ATProject`, and management commands.
3. **Factories**: Use `factory_boy` or `model_bakery` for factories covering `User`, `Post`, taxonomy models, assets, renditions, internal links, and metadata objects to keep tests concise.
4. **Mocking utilities**: Rely on `pytest-mock`/`unittest.mock` for heavy dependencies (`pypandoc`, `Pillow`, `ffprobe`, `mutagen`, `PyPDF2`, Celery tasks) to keep tests fast and deterministic.
5. **Celery**: Configure Celery tasks to run eagerly (`CELERY_TASK_ALWAYS_EAGER = True`) in the test settings to simplify asynchronous testing.【F:engine/tasks.py†L18-L200】
6. **Static/test data**: Store representative markdown files, HTML fragments, and sample metadata responses under `tests/fixtures/` for reuse across markdown and extractor tests.

## Test Data Strategy
- Implement reusable fixtures for common objects (e.g., published post, draft post, asset with image file, asset metadata) in `tests/conftest.py`.
- Create helper utilities to generate in-memory images/documents/audio streams for metadata and rendition tests, avoiding reliance on the filesystem except when validating file path behavior.
- Use Django’s `override_settings` decorator/context manager to adjust settings for tests that touch storage, caching, or timezone-sensitive logic.

## Test Matrix Overview
| Area | Modules / Components | Primary Test Types |
| --- | --- | --- |
| Core models & managers | `engine.models` (soft delete, taxonomy, posts, assets)【F:engine/models.py†L23-L1500】 | Unit, database integration |
| Backlink system | `engine.links.extractor`, `engine.signals`【F:engine/links/extractor.py†L18-L415】【F:engine/signals.py†L17-L185】 | Unit, integration |
| Markdown pipeline | `engine.markdown` preprocessors/postprocessors/renderer【F:engine/markdown/preprocessors/__init__.py†L8-L20】【F:engine/markdown/postprocessors/__init__.py†L27-L57】【F:engine/markdown/renderer.py†L10-L37】 | Unit, snapshot/regression |
| Utilities & tasks | `engine.utils`, `engine.tasks`, `celery_app`【F:engine/utils.py†L12-L200】【F:engine/tasks.py†L30-L200】【F:celery_app.py†L1-L15】 | Unit with mocks |
| Views & routing | `engine.views`, `engine.urls`【F:engine/views.py†L9-L93】【F:engine/urls.py†L1-L11】 | Request/response integration |
| Template tags | `engine/templatetags` filters and tags【F:engine/templatetags/markdown_tags.py†L11-L30】【F:engine/templatetags/gauge_tags.py†L8-L73】【F:engine/templatetags/tooltip_tags.py†L22-L189】 | Unit, template rendering |
| Management commands | `engine/management/commands` suite【F:engine/management/commands/generate_renditions.py†L1-L78】【F:engine/management/commands/populate_asset_metadata.py†L1-L59】【F:engine/management/commands/rebuild_backlinks.py†L1-L249】 | Command execution |
| Admin customizations | `engine.admin` actions/inlines【F:engine/admin.py†L1-L200】 | Admin site integration |
| Metadata extraction | `engine/metadata_extractor` functions【F:engine/metadata_extractor.py†L18-L520】 | Unit with mocks |

## Detailed Test Implementation Plan

### 1. Core Model and Manager Coverage
- **Soft deletion mixins**: Verify `SoftDeleteModel.delete(soft=True)` toggles flags and timestamps, while hard deletion removes records.【F:engine/models.py†L31-L63】 Test manager/queryset filtering for `alive()` vs. `deleted()`.
- **Taxonomy models**: Ensure slug auto-generation, uniqueness when duplicates exist, and ordering for `Tag`, `Category`, and `Series` to cover `_unique_slug` loops.【F:engine/models.py†L71-L158】
- **Post model**:
  - Validate slug creation, word count, and reading time updates in `save`, stubbing `render_markdown`/`extract_toc_from_html` for deterministic outputs.【F:engine/models.py†L204-L366】
  - Exercise `PostQuerySet` scopes (`public`, `published`, etc.) with timezone-controlled fixtures.【F:engine/models.py†L166-L198】
  - Test validation logic: `clean` raising when `expire_at <= published_at`, and the check constraint for published scheduling (simulate `full_clean`).【F:engine/models.py†L283-L309】
  - Cover helper methods: `is_published`, `get_absolute_url`, `_compute_word_count` edge cases (empty text, punctuation).【F:engine/models.py†L400-L424】
- **InternalLink**: Confirm uniqueness, string representation, and manager filtering for soft deletion.【F:engine/models.py†L426-L470】
- **Asset system**:
  - Cover `AssetQuerySet` filters and `Asset` field behaviors (validators, status transitions, file extension validation).【F:engine/models.py†L478-L882】
  - Test computed properties on `AssetMetadata`, `AssetRendition`, and `PostAsset` (e.g., `human_file_size`, `markdown_reference`, alias uniqueness constraint).【F:engine/models.py†L1045-L1412】
  - Validate organizational models (`AssetFolder`, `AssetTag`, `AssetCollection`) for path computation, slug generation, and relational integrity.【F:engine/models.py†L1419-L1500】

### 2. Backlink Extraction & Signals
- Unit test `extract_internal_links` across markdown, HTML, and absolute URL patterns, including duplicate suppression and missing content behavior.【F:engine/links/extractor.py†L18-L85】
- Cover `update_post_links` scenarios: creating, updating, deleting links; dry-run behavior; handling missing targets; ignoring self-links.【F:engine/links/extractor.py†L113-L219】
- Exercise query helpers (`get_backlinks_for_post`, `find_orphaned_posts`, `find_broken_links`, `get_link_statistics`) with sample graph fixtures.【F:engine/links/extractor.py†L283-L415】
- Integration tests for signals: simulate saving published vs. draft posts to ensure `update_post_links` triggers or skips, and verify logging of slug changes and republish handling.【F:engine/signals.py†L17-L185】 Use `pytest`’s `caplog` to assert log messages.

### 3. Markdown Pipeline
- **Preprocessors**: Test `asset_resolver_default` mapping of `@asset:` and alias references, query parameter parsing, fallback behavior, and caching interactions (mock cache).【F:engine/markdown/preprocessors/asset_resolver.py†L13-L158】
- **Renderer**: Patch `pypandoc.convert_text` to return known HTML and assert that preprocessors and postprocessors are invoked in order, passing context correctly.【F:engine/markdown/renderer.py†L10-L37】
- **Postprocessors**: For each processor listed in `POSTPROCESSORS`, craft focused tests that feed minimal HTML and validate expected transformations:
  - Asset enhancers (image, video, document) for metadata parsing, srcset population, captions.【F:engine/markdown/postprocessors/asset_image_enhancer.py†L18-L189】
  - Structural enhancers (lists, tables, blockquotes, admonitions, epigraphs, columns, block marker, first paragraph).【F:engine/markdown/postprocessors/__init__.py†L27-L45】
  - Utility enhancers (typography, date, footnotes, math copy button, external link decoration, sanitizer).【F:engine/markdown/postprocessors/__init__.py†L27-L47】
- Create regression snapshot tests to guard against unintended HTML changes by comparing output of representative markdown files through `render_markdown`.

### 4. Metadata Extraction
- Mock external dependencies (`PIL`, `mutagen`, `PyPDF2`, `ffprobe`) to simulate successful and failing metadata extraction for each asset type, asserting the shape of returned dictionaries and logging behavior.【F:engine/metadata_extractor.py†L18-L520】
- Test `extract_all_metadata` for branching on asset type, handling missing files, unsupported types, and ensuring `AssetMetadata` objects persist or return `None` when no metadata extracted.【F:engine/metadata_extractor.py†L459-L520】

### 5. Asset Utilities & Signals
- For `generate_asset_renditions`, use in-memory images to verify rendition creation, format handling, resizing logic, and skip conditions (non-image assets, widths ≥ original).【F:engine/utils.py†L12-L103】 Mock `Image.open` and `AssetRendition.objects.get_or_create` to control flows.
- Test `populate_asset_metadata` signal handler for MIME type inference, file hash generation, image dimension extraction, and ffprobe-based video metadata, using monkeypatched dependencies to avoid real subprocess calls.【F:engine/utils.py†L106-L200】 Validate that `needs_save` results in `instance.save` when necessary.

### 6. Celery Tasks & Async Flows
- Execute tasks synchronously with eager Celery settings to verify success and error payloads for metadata extraction, rendition generation, and bulk operations, mocking internal helpers and `Asset.objects.get` as needed.【F:engine/tasks.py†L41-L200】
- Include regression tests for retry configuration on `slow_add` (verify autoretry settings via task attributes) and ensure tasks handle missing assets gracefully.

### 7. Views, URLs, and Templates
- Request tests using Django’s test client for `home` (rendering base template) and `PostDetailView`, covering:
  - Access control for anonymous vs. staff users.
  - Publication state gating (draft/unpublished should 404 for anonymous users).
  - View count increments only for eligible requests, verifying database updates and in-memory attribute sync.【F:engine/views.py†L48-L74】
  - Context data including backlinks count via mocked extractor.【F:engine/views.py†L76-L93】
- Confirm URL patterns resolve to expected views and reverse lookups succeed.【F:engine/urls.py†L1-L11】

### 8. Template Tags & Components
- `markdown` filters: mock `render_markdown` to assert invocation and safe output.【F:engine/templatetags/markdown_tags.py†L11-L30】
- `gauge` inclusion tag: test helper functions `_clamp_int`, `_color_for_scheme`, and template context structure (including `use_current_color`). Render template snippets to ensure SVG partial receives expected context.【F:engine/templatetags/gauge_tags.py†L8-L73】
- Tooltip tags: parse template usage to verify generated HTML structure, configuration JSON, UUID uniqueness, and argument parsing (quoted/unquoted). Cover `simple_tooltip` convenience tag as well.【F:engine/templatetags/tooltip_tags.py†L22-L189】

### 9. Signals & App Configuration
- Ensure `EngineConfig.ready` imports register signal modules; test by reloading app config in isolation and asserting no import errors (use `importlib.reload`).【F:engine/apps.py†L4-L10】
- Validate interplay between model saves and signals, e.g., creating posts triggers `update_post_links`, while soft-deleting assets still leaves metadata accessible.

### 10. Management Commands
- For each command (`generate_renditions`, `populate_asset_metadata`, `rebuild_backlinks`), use `call_command` to assert stdout, handling of arguments, dry-run behavior, and error reporting. Mock heavy operations (`generate_asset_renditions`, `update_post_links`, statistics helpers) to isolate command logic.【F:engine/management/commands/generate_renditions.py†L10-L78】【F:engine/management/commands/rebuild_backlinks.py†L62-L249】

### 11. Admin Site Customizations
- Instantiate admins via `AdminSite` to test custom actions (`soft_delete_selected`, `restore_selected`) and list display methods (counts with HTML). Verify queryset overrides to include soft-deleted objects and that CSV export/download logic works where present.【F:engine/admin.py†L31-L111】
- Cover inlines and fieldsets for asset/post admins, ensuring no missing dependencies.

### 12. Celery App Bootstrap
- Minimal test ensuring `celery_app` loads configuration and autodiscovery without raising when environment variables are absent (mock `.env` loading if necessary).【F:celery_app.py†L1-L15】

## Cross-Cutting Concerns
- **Timezones**: Use `freeze_time` or Django’s `override` utilities to stabilize tests dealing with `timezone.now()` (publication filters, metadata timestamps).【F:engine/models.py†L176-L190】
- **File storage**: Configure Django’s default file storage to `InMemoryStorage` or temporary directories to isolate file-based tests.
- **Logging assertions**: Rely on `caplog` to ensure warnings/errors are emitted for failure cases in extractors, signals, and commands.
- **Performance**: Keep heavy loops (e.g., link rebuild) under control with small fixtures but ensure counters aggregate correctly.

## Automation & CI Recommendations
- Add `pytest --cov=engine --cov=ATProject --cov-report=term-missing` to CI scripts to enforce coverage thresholds.
- Integrate linting (existing `ruff`/`black` configs) alongside tests for consistent code style.
- Optionally introduce GitHub Actions workflow that runs tests against SQLite and (optionally) PostgreSQL to capture database-specific behavior (JSONField, constraints).

## Implementation Phasing
1. **Foundational Setup**: Introduce pytest configuration, coverage settings, and base fixtures. Add factories for models and configure Celery eager mode.
2. **Model & Query Tests**: Implement tests for core models, managers, and asset system to establish database coverage.
3. **Markdown & Metadata**: Add tests for preprocessors/postprocessors and metadata extraction utilities with mocks and sample fixtures.
4. **Backlink & Signals**: Cover extractor utilities, signals, and management commands to ensure link maintenance correctness.
5. **Views & Templates**: Implement request tests and template tag coverage.
6. **Async & Admin**: Finalize Celery task tests, command coverage, and admin site actions.
7. **Regression Suites**: Add snapshot markdown tests and ensure final coverage threshold is enforced in CI.

By following this plan, the team will achieve comprehensive automated coverage across the editorial workflow, asset management, and rendering layers, significantly reducing regression risk for future enhancements.
