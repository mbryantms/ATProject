# ATProject

Personal publishing platform built with Django 5.2, PostgreSQL, and modern frontend tooling.

## Quick Reference

```bash
# Development
uv run python manage.py runserver    # Start Django dev server
npm run dev                          # Watch CSS/JS (run in parallel)
uv run celery -A ATProject worker    # Task worker (optional)

# Database
uv run python manage.py migrate      # Apply migrations
uv run python manage.py makemigrations

# Frontend builds
npm run build                        # Production CSS/JS
npm run format                       # Prettier formatting

# Code quality
uv run pre-commit run --all-files    # Run all checks
uv run ruff check --fix .            # Python linting
uv run black .                       # Python formatting
npm run lint:js                      # JavaScript linting
```

## Project Structure

```
ATProject/              # Django project settings
engine/                 # Primary Django app
  models/               # Domain models (post, asset, taxonomy)
  admin/                # Admin customizations
  api/                  # REST API (presigned uploads)
  markdown/             # Markdown processing pipeline
  links/                # Internal link/backlinks system
  management/commands/  # Custom management commands
templates/              # Global templates
static/
  css/src/              # PostCSS source files
  css/dist/             # Compiled CSS
  js/                   # JavaScript modules
  js/dist/              # esbuild bundles
posts-md/               # Markdown content files
```

## Tech Stack

- **Backend**: Django 5.2, PostgreSQL (Neon), Celery + Redis
- **Content**: Pandoc via pypandoc, BeautifulSoup4, Bleach (sanitization)
- **Storage**: Cloudflare R2 via django-storages (S3-compatible)
- **Frontend**: PostCSS, esbuild (ES2017), @floating-ui/dom
- **Deployment**: Railway, Docker (Python 3.13-slim), Gunicorn, WhiteNoise

## Key Patterns

### Model Conventions

- Models inherit `TimeStampedModel` (created_at, updated_at) and `SoftDeleteModel`
- Default manager returns only non-deleted objects; use `all_objects` for everything
- Custom QuerySets provide domain filtering: `Post.objects.public().published()`

### Post Status/Visibility

```python
# Status: DRAFT, SCHEDULED, PUBLISHED, ARCHIVED
# Visibility: PUBLIC, UNLISTED, PRIVATE
# Completion: FINISHED, IN_PROGRESS, NOTES, DRAFT, ABANDONED
```

### Markdown Pipeline

Located in `engine/markdown/`. Processing order:
1. Preprocessors (asset resolution)
2. Pandoc conversion with Lua filters
3. 20+ postprocessors (sanitization, enhancement, TOC, footnotes, etc.)

### Asset System

- Assets stored in R2 with automatic rendition generation (400, 800, 1200, 1600px widths)
- Presigned upload API for large files (>100MB direct to R2)
- Metadata extraction via EXIF/mutagen for images/audio

**File deletion behavior:**
- Soft delete (`is_deleted=True`) preserves R2 files for recovery
- `cleanup_assets` command deletes DB records only by default
- Use `--delete-files` flag to also remove files from R2 storage
- Recommendation: Always use `--dry-run` first, then `--delete-files --days 30` for production cleanup

### Internal Links

`InternalLink` model tracks bidirectional links between posts. Rebuilt via:
```bash
uv run python manage.py rebuild_backlinks
```

## Management Commands

```bash
uv run python manage.py rebuild_backlinks    # Rebuild InternalLink records
uv run python manage.py generate_renditions  # Generate image variants
uv run python manage.py cleanup_assets       # Remove orphaned assets (DB only)
```

### Asset Cleanup

**Via management command:**
```bash
# Preview what would be deleted
uv run python manage.py cleanup_assets --orphaned-renditions --dry-run
uv run python manage.py cleanup_assets --unused-assets --days 30 --dry-run

# Delete DB records only (R2 files remain - useful for debugging)
uv run python manage.py cleanup_assets --soft-deleted --unused-assets --days 30

# Delete DB records AND R2 files (recommended for production)
uv run python manage.py cleanup_assets --soft-deleted --unused-assets --days 30 --delete-files
```

**Via Django admin:**
- Go to Assets > "Cleanup Assets" button
- Preview changes before executing
- Option to run sync or async (via Celery)

**Scheduled cleanup (Celery Beat):**
- Task: `engine.tasks.cleanup_orphaned_assets`
- Recommended schedule: Weekly (e.g., Sunday 3am)
- Kwargs: `{"delete_files": true, "days_old": 30}`
- Configure at `/admin/django_celery_beat/periodictask/`

## Environment Variables

Required in `.env` (see `.env.example`):

```ini
SECRET_KEY=...
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET_NAME=...
R2_S3_ENDPOINT_URL=...
R2_CUSTOM_DOMAIN=...
```

## Code Style

- Python: Black + Ruff (configured in pyproject.toml)
- JavaScript: Prettier + ESLint
- Templates: djlint
- Pre-commit hooks enforce formatting

## Testing

```bash
uv run python manage.py test
```

## Documentation

- `ARCHITECTURE.md` - System architecture overview
- `DEPLOYMENT.md` - Neon + Railway deployment guide
- `ROADMAP.md` - Feature roadmap and TODOs
