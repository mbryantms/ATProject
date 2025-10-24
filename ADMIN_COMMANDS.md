# Django Admin Commands Reference

Complete reference for all admin actions and management commands in the ATProject.

**Admin Interface**: Standard Django Admin
**Theme**: Django's default admin theme

---

## Table of Contents
- [Admin Actions (Web Interface)](#admin-actions-web-interface)
  - [Post Admin Actions](#post-admin-actions)
  - [Tag Admin Actions](#tag-admin-actions)
  - [Asset Admin Actions](#asset-admin-actions)
  - [Shared Actions (All Models)](#shared-actions-all-models)
- [Management Commands (CLI)](#management-commands-cli)
- [Quick Reference: Async vs Sync](#quick-reference-async-vs-sync)

---

## Admin Actions (Web Interface)

### Post Admin Actions
**Location**: Django Admin → Posts → Select posts → Actions dropdown
**Code**: `engine/admin/post.py:277-286`

| Action | Description | Async? | Code Location |
|--------|-------------|--------|---------------|
| **Publish selected posts** | Sets status to 'published' and sets published_at timestamp | No | post.py:676 |
| **Unpublish selected posts** | Sets status to 'draft' | No | post.py:690 |
| **Feature selected posts** | Marks posts as featured | No | post.py:696 |
| **Unfeature selected posts** | Removes featured flag | No | post.py:702 |
| **Rebuild backlinks for selected posts** | Scans markdown content and rebuilds internal link references | No | post.py:708 |
| **Export selected posts as CSV** | Downloads CSV file with post metadata | No | post.py:753 |
| **Soft delete selected** | Marks posts as deleted without removing from database | No | mixins.py:23 |
| **Restore selected** | Restores soft-deleted posts | No | mixins.py:35 |

---

### Tag Admin Actions
**Location**: Django Admin → Tags → Select tags → Actions dropdown
**Code**: `engine/admin/taxonomy.py:69-74`

| Action | Description | Async? | Code Location |
|--------|-------------|--------|---------------|
| **Activate selected tags** | Sets is_active=True for selected tags | No | taxonomy.py:234 |
| **Deactivate selected tags** | Sets is_active=False for selected tags | No | taxonomy.py:244 |
| **Update usage counts** | Recalculates usage_count from actual post relationships | No | taxonomy.py:254 |
| **Export selected tags to CSV** | Downloads CSV file with tag data (name, namespace, rank, usage, etc.) | No | taxonomy.py:267 |

---

### Asset Admin Actions
**Location**: Django Admin → Assets → Select assets → Actions dropdown
**Code**: `engine/admin/asset.py:412-425`

| Action | Description | Async? | Code Location |
|--------|-------------|--------|---------------|
| **Extract extended metadata (EXIF, audio tags, etc.)** | Extracts comprehensive metadata synchronously (camera data, GPS, audio tags, document info, colors) | No | asset.py:917 |
| **Extract metadata (async with Celery)** | Queues metadata extraction as background Celery task | **Yes** ✓ | asset.py:961 |
| **Generate renditions for selected images** | Creates responsive image renditions at multiple widths (400w, 800w, 1200w, 1600w) | No | asset.py:825 |
| **Update usage count** | Recalculates usage_count from actual post relationships | No | asset.py:837 |
| **Regenerate keys with organized format** | Regenerates asset keys using collection/type-title format | No | asset.py:848 |
| **Mark as Ready** | Sets asset status to 'ready' | No | asset.py:992 |
| **Mark as Archived** | Sets asset status to 'archived' | No | asset.py:998 |
| **Export metadata as CSV** | Downloads CSV with comprehensive asset metadata | No | asset.py:1004 |
| **Delete orphaned renditions** | Deletes renditions of soft-deleted assets, shows storage freed | No | asset.py:1086 |
| **Delete unused assets (not in posts)** | Deletes selected assets not used in any posts, cascades to renditions | No | asset.py:1118 |
| **Soft delete selected** | Marks assets as deleted without removing from database | No | mixins.py:23 |
| **Restore selected** | Restores soft-deleted assets | No | mixins.py:35 |

#### Deprecated/Removed Actions
- ~~`populate_metadata`~~ - Function still exists (asset.py:890) but removed from actions list. Use "Extract extended metadata" instead.

---

### Shared Actions (All Models)

These actions are available on all models that inherit from `SoftDeleteModel`:

**Code**: `engine/admin/mixins.py:23-47`

| Action | Description | Models |
|--------|-------------|--------|
| **Soft delete selected** | Marks items as deleted (is_deleted=True) without removing from database | Post, Asset |
| **Restore selected** | Clears soft delete flag (is_deleted=False) and deleted_at timestamp | Post, Asset |

---

## Management Commands (CLI)

### cleanup_assets
**Purpose**: Clean up orphaned renditions and unused assets
**Location**: `engine/management/commands/cleanup_assets.py`
**Async**: No (runs synchronously from CLI)

#### Usage Examples:
```bash
# Preview orphaned renditions (dry run)
python manage.py cleanup_assets --orphaned-renditions --dry-run

# Delete orphaned renditions
python manage.py cleanup_assets --orphaned-renditions

# Delete unused assets older than 30 days
python manage.py cleanup_assets --unused-assets --days 30

# Clean up soft-deleted assets and their renditions
python manage.py cleanup_assets --unused-assets --soft-deleted

# Combined cleanup with dry run
python manage.py cleanup_assets --orphaned-renditions --unused-assets --dry-run
```

#### Options:
| Option | Description |
|--------|-------------|
| `--orphaned-renditions` | Delete renditions whose parent assets no longer exist or are deleted |
| `--unused-assets` | Delete assets that are not used in any posts |
| `--soft-deleted` | Include soft-deleted assets in cleanup |
| `--dry-run` | Show what would be deleted without actually deleting |
| `--days N` | Only delete items older than N days (for unused assets) |

#### Features:
- Shows storage size that will be freed
- Displays breakdown by asset type
- Shows example items before deletion
- Counts cascade deletions (renditions)

---

### generate_renditions
**Purpose**: Generate responsive image renditions for assets
**Location**: `engine/management/commands/generate_renditions.py`
**Async**: No (runs synchronously from CLI)

#### Usage Examples:
```bash
# Generate renditions for all images
python manage.py generate_renditions

# Generate for specific asset
python manage.py generate_renditions --asset-key img-hero-banner

# Custom widths
python manage.py generate_renditions --widths 300,600,900,1800

# Force regenerate (delete existing first)
python manage.py generate_renditions --force

# Combine options
python manage.py generate_renditions --asset-key img-logo --widths 200,400 --force
```

#### Options:
| Option | Description |
|--------|-------------|
| `--asset-key KEY` | Generate renditions for specific asset by key |
| `--widths W1,W2,...` | Comma-separated list of widths (default: 400,800,1200,1600) |
| `--force` | Regenerate even if renditions already exist (deletes existing first) |

---

### rebuild_backlinks
**Purpose**: Rebuild internal link references between posts
**Location**: `engine/management/commands/rebuild_backlinks.py`
**Async**: No (runs synchronously from CLI)

#### Usage Examples:
```bash
# Rebuild backlinks for all posts
python manage.py rebuild_backlinks

# Rebuild for specific post
python manage.py rebuild_backlinks --post-slug my-blog-post

# Verbose output
python manage.py rebuild_backlinks --verbosity 2
```

#### Options:
| Option | Description |
|--------|-------------|
| `--post-slug SLUG` | Rebuild backlinks for specific post by slug |
| `--verbosity LEVEL` | Control output detail (0=minimal, 1=normal, 2=verbose) |

#### What it does:
- Scans markdown content for internal links (e.g., `[link](slug:other-post)`)
- Creates `InternalLink` records in database
- Tracks bidirectional relationships (outgoing and incoming links)
- Used for "Related Posts" features and link integrity checks

---

## Quick Reference: Async vs Sync

### Asynchronous Operations (Use Celery)
These operations run in the background via Celery workers. You can continue working while they process.

**Admin Actions:**
- ✓ **Extract metadata (async with Celery)** - asset.py:961
  - Uses task: `engine.tasks.bulk_extract_metadata`
  - Shows task ID for tracking in django_celery_results admin

**Requirements:**
- Redis server must be running
- Celery worker must be running: `celery -A ATProject worker -l info`
- `django_celery_results` must be in INSTALLED_APPS

---

### Synchronous Operations
These operations run immediately in the web request/command. Browser waits until complete.

**All other admin actions are synchronous:**
- Post actions (publish, unpublish, feature, export, etc.)
- Tag actions (activate, deactivate, update counts, export)
- Most asset actions (extract metadata sync, generate renditions, cleanup, export)
- Soft delete/restore actions

**All management commands are synchronous:**
- `cleanup_assets`
- `generate_renditions`
- `rebuild_backlinks`

---

## Tips and Best Practices

### When to use Admin Actions vs Management Commands

**Use Admin Actions when:**
- Working with specific subset of records (filtered/searched)
- Need visual confirmation of selected items
- Quick operations on small batches
- Prefer GUI over terminal

**Use Management Commands when:**
- Processing large batches of records
- Running scheduled/automated tasks
- Need advanced filtering (age-based, complex queries)
- Scripting/automation (cron jobs, deployment scripts)
- Dry-run capabilities needed

### Performance Considerations

**Synchronous operations** - Safe for:
- < 100 records
- Operations completing in < 30 seconds
- Quick database updates

**Asynchronous operations** (Celery) - Use for:
- > 100 records
- File processing (images, videos, documents)
- External API calls
- Operations taking > 30 seconds

### Storage Cleanup Workflow

Recommended cleanup workflow to free storage:

1. **Soft delete assets** (admin action)
   - Review and soft-delete unwanted assets first
   - This marks them is_deleted=True but keeps files

2. **Delete orphaned renditions** (admin action)
   - Removes renditions of soft-deleted assets
   - Frees storage immediately
   - Shows GB/MB freed

3. **Delete unused assets** (CLI with dry-run)
   ```bash
   python manage.py cleanup_assets --unused-assets --soft-deleted --days 30 --dry-run
   ```
   - Review what will be deleted

4. **Delete unused assets** (CLI final)
   ```bash
   python manage.py cleanup_assets --unused-assets --soft-deleted --days 30
   ```
   - Permanent deletion of soft-deleted assets older than 30 days

---

## Related Documentation

- **Celery Configuration**: `ATProject/settings.py:284-286`
- **Celery Tasks**: `engine/tasks.py`
- **Model Definitions**: `engine/models/`
- **Admin Customizations**: `engine/admin/`

---

**Last Updated**: 2025-10-10
**Django Version**: 5.2.7
**Admin Theme**: Django Default
