# ATProject

Personal publishing platform built with Django 6.0, PostgreSQL, and modern frontend tooling.

## First-time local setup

```bash
docker compose up -d                              # start Postgres + Redis (see compose.yaml)
cp .env.example .env                              # then edit secrets as needed
uv sync                                           # install Python deps
npm install                                       # install JS deps
uv run python manage.py migrate                   # apply migrations
uv run python manage.py collectstatic --noinput   # populate Whitenoise manifest (required before tests)
uv run python manage.py createsuperuser           # optional, for admin access
```

`compose.yaml` brings up Postgres (`pgdata` volume) and Redis (`redisdata` volume) — both persist across `docker compose stop`/`start`. Use `docker compose down -v` to nuke them. Production Postgres is Neon and production Redis is Railway-managed (see [DEPLOYMENT.md](DEPLOYMENT.md)).

If Docker isn't available on your host (broken daemon, restricted sandbox), run native Postgres + Redis instead — the app only cares that the `DATABASE_URL` and `REDIS_URL` env vars resolve to reachable services.

There is **no CI** — the GitHub Actions workflow was removed. Run tests locally before pushing.

## Daily commands

```bash
# Run the app
docker compose up -d                 # ensure Postgres + Redis are up
uv run python manage.py runserver    # Django dev server
npm run dev                          # Watch CSS/JS (run in parallel terminal)
uv run celery -A ATProject worker    # Task worker (optional — signals use .delay() but fall back to sync)

# Database
uv run python manage.py migrate      # Apply new migrations
uv run python manage.py makemigrations

# Tests (require Postgres running + collectstatic having been run at least once)
# Redis is NOT required — settings.py flips CELERY_TASK_ALWAYS_EAGER=True when
# ``manage.py test`` is detected, so signal handlers that call ``.delay()``
# run inline instead of blocking on a broker connection.
uv run python manage.py test
uv run python manage.py test engine.tests.test_feeds   # single module

# Frontend builds (dist files are gitignored, built in Docker for deploy)
npm run build                        # Production CSS/JS bundle
npm run format                       # Prettier formatting

# Code quality
uv run pre-commit run --all-files    # Run all checks
uv run ruff check --fix .            # Python linting
uv run ruff format .                 # Python formatting
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
  bibliography/         # Citation system (citeproc-js bridge, formatter)
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

- **Backend**: Django 6.0, PostgreSQL (Neon in prod, Docker locally), Celery + Redis
- **Content**: Pandoc via pypandoc, BeautifulSoup4, Bleach + nh3 (sanitization)
- **Storage**: Cloudflare R2 via django-storages (S3-compatible)
- **Frontend**: PostCSS, esbuild (ES2017), @floating-ui/dom
- **Citations**: citeproc-js via Node.js subprocess, CSL styles
- **Observability**: Sentry SDK (Django + Celery integrations); see [SENTRY.md](SENTRY.md)
- **Deployment**: Railway, Docker (multi-stage: Node builder + Python 3.13-slim), Gunicorn, WhiteNoise

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

### Syndication Feeds

`engine/feeds.py` exposes RSS 2.0 and Atom 1.0 for: global (`/feed/`), featured (`/feed/featured/`), per-tag (`/feed/tag/<slug>/`, alias-aware), per-category (`/feed/category/<slug>/`), and per-series (`/feed/series/<slug>/`). All share `BasePostFeed`; subclasses override `items()` and channel metadata. Items carry full HTML content (`content_html_cached`), stable `post:<pk>` GUIDs, both tag and category names, and a hero-image enclosure when available.

## Management Commands

```bash
uv run python manage.py rebuild_backlinks          # Rebuild InternalLink records
uv run python manage.py generate_renditions        # Generate image variants
uv run python manage.py generate_video_renditions  # Transcode videos + extract posters
uv run python manage.py regenerate_html_cache      # Re-render cached post HTML
uv run python manage.py cleanup_assets             # Remove orphaned assets (DB only)
```

### Video Rendition Generation

**Via management command:**
```bash
# Preview which videos would be processed
uv run python manage.py generate_video_renditions --dry-run

# Process a single asset by key
uv run python manage.py generate_video_renditions --asset-key vid-nyt-analysis

# Custom resolution set (default: 720,1080; heights in px, never upscales)
uv run python manage.py generate_video_renditions --resolutions 720

# Only (re-)grab posters; skip MP4/WebM transcoding
uv run python manage.py generate_video_renditions --skip-renditions

# Only transcode; skip poster extraction
uv run python manage.py generate_video_renditions --skip-poster
```

The command runs synchronously (per-asset output) — useful for backfills and debugging. For production/async, call `engine.tasks.generate_video_renditions_async.delay(asset.pk)` which has a 30-minute time limit and runs on the Celery worker.

**What it emits per asset:**
- Poster: `preset="poster"`, two AssetRendition rows (format `webp` + `auto`/JPEG fallback). Also populates `AssetMetadata.lqip_data_url` + `average_color` + `dominant_colors` from the poster frame.
- Video: for each requested resolution ≤ source height, two AssetRendition rows (H.264 MP4 via libx264/AAC, VP9 WebM via libvpx-vp9/Opus), with `preset="video-720p"` etc. and `codec` populated.

**After running**: execute `regenerate_html_cache` for posts embedding the video so `asset_video_enhancer` picks up the new renditions in `content_html_cached` and emits the multi-`<source>` tags.

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

- Python: Ruff (linting + formatting, configured in pyproject.toml)
- JavaScript: Prettier + ESLint
- Templates: djlint
- Pre-commit hooks enforce formatting

## Testing

```bash
uv run python manage.py test
```

Requires:
- Postgres running (`docker compose up -d`).
- `collectstatic` to have been run at least once. Templates extend `base.html` which references `{% static 'img/favicon.ico' %}` resolved through Whitenoise's `CompressedManifestStaticFilesStorage`; without a populated manifest, any test that renders the 404 page (or any base-extending template) raises `ValueError: Missing staticfiles manifest entry`.

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — system architecture overview
- [DEPLOYMENT.md](DEPLOYMENT.md) — Neon + Railway deployment guide
- [SENTRY.md](SENTRY.md) — Sentry setup
- [BIBLIOGRAPHY.md](BIBLIOGRAPHY.md) — citation system usage
- [bibliography-design.md](bibliography-design.md) — citation system design notes
