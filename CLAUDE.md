# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ATProject is a Django-based blog/content management platform with a custom Markdown rendering pipeline. The project
emphasizes content authoring in Markdown with extensible pre/post processing and a hierarchical taxonomy system (
Categories, Tags, Series).

## Development Commands

### Django

```bash
# Run development server (configured for 127.1.1.1)
python manage.py runserver 127.1.1.1:8000

# Create and apply migrations
python manage.py makemigrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Run Django shell
python manage.py shell

# Run tests
python manage.py test
```

### CSS (PostCSS)

```bash
# Build CSS once
npm run build-css

# Watch CSS for changes
npm run watch-css

# Format all code (CSS, HTML, JS, JSON)
npm run format

# Check formatting
npm run format:check

# Lint JavaScript
npm run lint:js
```

## Architecture

### Core Application: `engine`

The `engine` app is the main content management system containing:

- **Models** (`engine/models.py`): Post, Category, Tag, Series with soft-delete support
- **Views** (`engine/views.py`): PostDetailView and demo pages
- **Markdown Pipeline** (`engine/markdown/`): Custom rendering system

### Markdown Pipeline

The markdown rendering system follows a three-stage pipeline:

1. **Preprocessors** (`engine/markdown/preprocessors/`): Process raw markdown before conversion
    - Currently minimal; extensible for mention handling, input sanitization, etc.
    - Registered in `preprocessors/__init__.py` PREPROCESSORS list

2. **Markdown Conversion** (`engine/markdown/renderer.py`):
    - Uses singleton `get_markdown_instance()` for performance
    - Configuration in `engine/markdown/config.py`
    - Extensions: PyMdown, custom header_attributes, paragraph_classes
    - Supports: tables, fenced code, syntax highlighting, task lists, footnotes, etc.

3. **Postprocessors** (`engine/markdown/postprocessors/`): Process HTML after conversion
    - `sanitize_html`: Bleach-based HTML sanitization
    - `modify_external_links`: Adds attributes to external links
    - Registered in `postprocessors/__init__.py` POSTPROCESSORS list
    - Order matters - they run sequentially

**Key files:**

- `engine/markdown/renderer.py`: Main `render_markdown()` function
- `engine/markdown/config.py`: Markdown extensions and their configurations
- `engine/markdown/extensions/`: Custom markdown extensions (header_attributes, paragraph_classes, toc_extractor)
- `engine/templatetags/markdown_tags.py`: Django template filters (`|markdown`, `{% markdown_with_context %}`)

### Models Architecture

**Post Model** (`engine/models.py:201-415`):

- Markdown-first authoring (source of truth: `content_markdown`)
- Optional HTML caching (`content_html_cached`)
- Status workflow: DRAFT → SCHEDULED → PUBLISHED → ARCHIVED
- Visibility levels: PUBLIC, UNLISTED, PRIVATE
- Soft-delete support (never hard-delete, use `is_deleted` flag)
- Auto-computed: word_count, reading_time_minutes, table_of_contents
- Relationships: author, co_authors, series, categories, tags, related_posts

**Taxonomy Models**:

- `Tag` (engine/models.py:68-91): Flat tagging system
- `Category` (engine/models.py:93-127): Hierarchical with optional parent
- `Series` (engine/models.py:129-156): Multi-part post grouping

**Base Mixins**:

- `TimeStampedModel`: Auto-managed created_at/updated_at
- `SoftDeleteModel`: Implements soft-delete pattern with `is_deleted`/`deleted_at`
- Custom managers: `objects` (excludes deleted), `all_objects` (includes deleted)

### Static Assets

- **Source CSS**: `static/css/src/` (PostCSS with nested syntax)
- **Built CSS**: `static/css/dist/` (processed by PostCSS)
- **JavaScript**: `static/js/`
- **Templates**: `templates/` (Django templates)

### URL Routing

- Main URLs: `ATProject/urls.py` → includes `engine.urls`
- Engine URLs: `engine/urls.py` → demo pages + post detail view
- Post detail: `/posts/<slug>/` → `PostDetailView`

## Key Design Patterns

### Markdown Rendering

Rendering happens **outside the model** via:

- Template filter: `{{ post.content_markdown|markdown }}`
- Template tag: `{% markdown_with_context post.content_markdown %}`
- Direct call: `render_markdown(text, context={})`

The `content_html_cached` field is available for performance optimization but not required.

### Soft Delete

Always use soft delete for Posts and related models:

```python
post.delete()  # soft=True by default
post.delete(soft=False)  # hard delete if absolutely necessary
```

Query soft-deleted items:

```python
Post.objects.all()  # excludes deleted
Post.all_objects.all()  # includes deleted
Post.all_objects.deleted()  # only deleted
```

### Custom QuerySet Methods

Use specialized querysets for filtering:

```python
Post.objects.published()  # status=PUBLISHED + published_at <= now
Post.objects.public()  # visibility=PUBLIC
Post.objects.featured()  # is_featured=True
Post.objects.drafts()  # status=DRAFT
```

## Development Workflow

1. **CSS changes**: Always run `npm run watch-css` during development
2. **Markdown extensions**: Add to `engine/markdown/extensions/` and register in `config.py`
3. **Pre/post processors**: Add to respective `__init__.py` PREPROCESSORS/POSTPROCESSORS lists
4. **Model changes**: Create migrations immediately (`makemigrations` → `migrate`)
5. **Testing templates**: Use demo URLs (/, /lorem/, /admonitions/, /lists/, /block-elements/, /links/)

## Important Constraints

- Database: SQLite (development) - `db.sqlite3`
- Allowed hosts: `127.1.1.1` (non-standard localhost)
- Markdown is source of truth - never manually edit `content_html_cached`
- Posts require `published_at` when status is PUBLISHED or SCHEDULED (CheckConstraint)
- Slugs auto-generate from title with uniqueness checks

## Extending the Markdown Pipeline

### Adding a Preprocessor

1. Create processor in `engine/markdown/preprocessors/my_processor.py`
2. Function signature: `def my_processor(text: str, context: dict) -> str`
3. Register in `preprocessors/__init__.py` PREPROCESSORS list

### Adding a Postprocessor

1. Create processor in `engine/markdown/postprocessors/my_processor.py`
2. Function signature: `def my_processor(html: str, context: dict) -> str`
3. Register in `postprocessors/__init__.py` POSTPROCESSORS list
4. Order matters - consider placement in the list

### Adding a Markdown Extension

1. Create extension in `engine/markdown/extensions/my_extension.py`
2. Add to `extensions` list in `config.py`
3. Optionally configure in `extension_configs` dict

## Special Markdown Syntax

### Margin Notes

Use Pandoc span attributes to create margin notes:

```markdown
[Your margin note text]{.marginnote}
```

- **Inline** (<1497px): Appears italicized within paragraph
- **Sidenote** (≥1497px): Positioned to the right of main content
- **Aggregated**: Collected at section start if ≥3 notes exist

See `MARGINNOTES.md` for complete documentation.

### Date Enhancements

Explicitly mark dates for time-since and duration annotations:

```markdown
[1500]{.date-since}                    → 1500₅₂₅ᵧₐ
[1500–1600]{.date-range}               → 1500–¹⁰⁰ʸ1600
[1500–1600]{.date-range-since}         → 1500–¹⁰⁰ʸ1600₄₂₅ᵧₐ
```

Four types:
1. **`.date-since`** - Time since single date or end of range
2. **`.date-range`** - Duration between two dates
3. **`.date-range-since`** - Both duration and time-since
4. **`.date-since`** (with range) - Only time-since from end date

Supports flexible formats: `YYYY`, `YYYY-MM`, `YYYY-MM-DD`, `Month DD, YYYY`, etc.

See `DATE_ENHANCER.md` for complete documentation.
