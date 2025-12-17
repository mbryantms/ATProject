# ATProject Architecture

A Django-based personal publishing platform with advanced content features including markdown processing, backlinks, similarity detection, and responsive media management.

## Project Structure

```
ATProject/
├── ATProject/           # Django project settings
├── engine/              # Primary Django application
│   ├── models/          # Data models (post, taxonomy, asset)
│   ├── admin/           # Admin customizations
│   ├── markdown/        # Markdown processing pipeline
│   │   ├── preprocessors/
│   │   ├── postprocessors/
│   │   ├── extensions/
│   │   └── filters/
│   ├── links/           # Internal link/backlinks system
│   ├── management/      # Custom Django commands
│   ├── templatetags/    # Custom template tags
│   └── templates/       # App templates
├── templates/           # Global templates
├── static/
│   ├── css/src/         # Source CSS (PostCSS)
│   ├── css/dist/        # Compiled CSS
│   └── js/              # JavaScript modules
└── docs/                # Documentation
```

## Core Models

### Content Models

| Model | Purpose |
|-------|---------|
| `Post` | Primary content with markdown, metadata, status workflow |
| `InternalLink` | Bidirectional post connections for backlinks |

### Taxonomy Models

| Model | Purpose |
|-------|---------|
| `Tag` | Hierarchical tags with namespaces, colors, icons |
| `TagAlias` | Synonym mapping to canonical tags |
| `Category` | Simple hierarchical categories |
| `Series` | Multi-part content grouping |

### Asset Models

| Model | Purpose |
|-------|---------|
| `Asset` | Global media library (images, video, audio, documents) |
| `AssetMetadata` | EXIF, audio tags, color analysis |
| `AssetRendition` | Responsive image variants |
| `PostAsset` | Post-to-asset junction with context |
| `AssetFolder` | Hierarchical organization |
| `AssetTag` | Asset-specific tagging |
| `AssetCollection` | Curated asset groupings |

### Base Patterns

| Model | Purpose |
|-------|---------|
| `TimeStampedModel` | `created_at`, `updated_at` timestamps |
| `SoftDeleteModel` | `is_deleted`, `deleted_at` with dual managers |

## Key Features

### Content Management
- **Status Workflow**: Draft → Scheduled → Published → Archived
- **Visibility**: Public, Unlisted, Private
- **Completion Tracking**: Finished, In Progress, Notes, Draft, Abandoned
- **Soft Delete**: Recoverable deletion with `all_objects` manager

### Markdown Pipeline
Pandoc-based processing with extensible pre/post processors:

1. **Preprocessors**: Asset resolution (`@asset:key`)
2. **Pandoc Conversion**: Extended markdown → HTML5
3. **Postprocessors** (20+):
   - HTML sanitization (bleach)
   - Responsive images with lazy loading
   - List/blockquote/table enhancement
   - Admonitions (note, warning, tip, error)
   - Link decoration with type icons
   - Math copy buttons
   - Typography improvements
   - Footnote enhancement

### Backlinks System
- Automatic link extraction from markdown content
- Pattern matching: `[text](/posts/slug/)`, absolute URLs
- Signal-triggered on post save/publish
- Queryable for reverse citations

### Post Similarity
Multi-factor scoring algorithm:
- Tag overlap (Jaccard similarity, 40%)
- Category overlap (20%)
- Series membership (35%)
- Content tokens (cosine similarity, 40%)
- Recency boost (365-day decay, 10%)

### Asset Processing
- Metadata extraction: EXIF, audio tags, GPS, color analysis
- Responsive renditions: 400, 800, 1200, 1600px widths
- File hash deduplication
- Focal point specification for smart cropping

## Technology Stack

### Backend
- **Framework**: Django 5.2+
- **Database**: PostgreSQL
- **Task Queue**: Celery + Redis
- **Scheduler**: django-celery-beat
- **Storage**: S3/Cloudflare R2

### Content Processing
- **Markdown**: pypandoc (Pandoc wrapper)
- **Syntax Highlighting**: Pygments
- **HTML Parsing**: BeautifulSoup4
- **Sanitization**: Bleach
- **Images**: Pillow

### Frontend Build
- **CSS**: PostCSS (autoprefixer, cssnano, nested, mixins)
- **JavaScript**: esbuild (ES2017 target)
- **Tooltips**: @floating-ui/dom

### Key Dependencies
```
django>=5.2.7
celery>=5.5.3
pypandoc>=1.15
pillow>=11.3.0
django-storages>=1.14.6
boto3>=1.40.49
beautifulsoup4>=4.14.2
bleach>=6.2.0
```

## Database Design

### Indexes
- Posts: status/published_at, visibility/published_at
- Tags: namespace/name, parent/name, is_active/usage_count
- Assets: key, file_hash, asset_type/created_at
- InternalLinks: source_post, target_post

### Constraints
- Post published/scheduled requires published_at
- Tag name unique per namespace
- Tag no self-parent (circular prevention)
- Asset focal points in [0.0, 1.0]

## Background Tasks

| Task | Purpose |
|------|---------|
| `extract_metadata_async` | EXIF, audio tags, color extraction |
| `generate_renditions_async` | Responsive image generation |
| `bulk_extract_metadata` | Batch metadata processing |
| `bulk_generate_renditions` | Batch rendition generation |

## Management Commands

| Command | Purpose |
|---------|---------|
| `rebuild_backlinks` | Rebuild InternalLink records |
| `generate_renditions` | Generate responsive images |
| `cleanup_assets` | Remove orphaned assets |

## URL Structure

| Pattern | View | Purpose |
|---------|------|---------|
| `/` | `PostArchiveView` | Posts by year |
| `/posts/<slug>/` | `PostDetailView` | Single post |
| `/tags/<slug>/` | `TagArchiveView` | Posts by tag |

## Admin Features

- Soft-delete recovery with strikethrough display
- Asset preview thumbnails
- Tag hierarchy visualization
- Backlinks statistics
- Metadata inline editing
- GPS map integration
- Color palette preview

## Security

- CSRF protection enabled
- HTML sanitization via Bleach
- WhiteNoise static serving with Brotli
- S3/R2 signed URLs (configurable)
- PostgreSQL SSL required
- Statement/lock timeouts configured

## Architecture Patterns

1. **Signal Handlers**: Post lifecycle automation
2. **Custom QuerySets**: Domain filtering (`.published()`, `.public()`)
3. **Soft Delete**: Dual manager pattern
4. **Pipeline**: Markdown pre/post processors
5. **Async Tasks**: Heavy operations via Celery
6. **Hierarchical Models**: Parent/child relationships
7. **Model Mixins**: Timestamp and soft-delete injection
