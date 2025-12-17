# ATProject Roadmap

Living document tracking planned and in-progress features.

## Status Legend
- `planned` - Identified for implementation
- `in-progress` - Currently being worked on
- `blocked` - Waiting on dependency or decision
- `done` - Completed (move to CHANGELOG)

---

## Infrastructure

### Deployment & Hosting
| Feature | Status | Notes |
|---------|--------|-------|
| Migrate to Neon (PostgreSQL) | planned | Serverless PostgreSQL, connection pooling |
| Deploy to Railway | planned | Container hosting with Neon integration |
| CI/CD pipeline | planned | GitHub Actions for testing/deployment |
| Staging environment | planned | Preview deployments for PRs |

### Database
| Feature | Status | Notes |
|---------|--------|-------|
| Connection pooling optimization | planned | PgBouncer or Neon's built-in pooling |
| Database backups automation | planned | Scheduled dumps to R2/S3 |
| Migration safety checks | planned | Pre-deploy validation |

---

## Code Quality

### Cleanup & Optimization
| Feature | Status | Notes |
|---------|--------|-------|
| Remove unused imports/code | planned | Ruff/flake8 sweep |
| Consolidate duplicate logic | planned | DRY refactoring pass |
| Type hints coverage | planned | Add mypy, gradual typing |
| Test coverage baseline | planned | pytest, coverage reporting |
| Template linting | planned | djlint integration |
| CSS dead code removal | planned | PurgeCSS or manual audit |

### Performance
| Feature | Status | Notes |
|---------|--------|-------|
| Query optimization audit | planned | django-debug-toolbar, EXPLAIN analysis |
| N+1 query detection | planned | Add prefetch/select_related where needed |
| HTML caching strategy | planned | Evaluate `content_html_cached` usage |
| Static asset CDN | planned | CloudFlare or R2 public bucket |

---

## Admin & Maintenance

### Admin Commands
| Feature | Status | Notes |
|---------|--------|-------|
| Audit existing commands | planned | Document, test, standardize |
| `check_broken_links` command | planned | Validate internal link targets exist |
| `update_word_counts` command | planned | Batch recalculate word counts |
| `export_posts` command | planned | Markdown/JSON export for backup |
| `import_posts` command | planned | Bulk import from markdown files |
| `sync_usage_counts` command | planned | Recalculate tag/category usage |
| `generate_sitemap` command | planned | XML sitemap generation |
| `validate_assets` command | planned | Check file integrity, missing files |

### Admin Interface
| Feature | Status | Notes |
|---------|--------|-------|
| Dashboard with stats | planned | Post counts, recent activity |
| Bulk tag operations | planned | Merge, rename, reassign |
| Asset usage report | planned | Which posts use which assets |
| Draft preview improvements | planned | Side-by-side markdown/HTML |
| Scheduled post calendar | planned | Visual scheduling interface |

---

## Content Features

### Citations & References
| Feature | Status | Notes |
|---------|--------|-------|
| Automatic citation extraction | planned | Parse `[@cite]` syntax |
| Bibliography model | planned | BibTeX/JSON citation storage |
| Citation rendering | planned | Footnote or inline styles |
| Cross-post citation linking | planned | Link to other posts as citations |
| Citation import (BibTeX) | planned | Bulk import from .bib files |

### Navigation & Discovery
| Feature | Status | Notes |
|---------|--------|-------|
| Site-wide menu bar | planned | Header navigation component |
| Category archive pages | planned | Similar to tag archives |
| Series navigation | planned | Prev/next within series |
| Search functionality | planned | Full-text search (PostgreSQL FTS) |
| Tag cloud/index page | planned | All tags with usage counts |
| RSS/Atom feeds | planned | Per-tag, per-category, global |

### Content Enhancements
| Feature | Status | Notes |
|---------|--------|-------|
| Reading progress indicator | planned | Scroll-based progress bar |
| Anchor link copy buttons | planned | Click header to copy link |
| Code block copy buttons | planned | One-click code copying |
| Image lightbox | planned | Full-screen image viewing |
| Print stylesheet | planned | Optimized print layout |
| Dark mode toggle | planned | User-controlled theme switching |

---

## Asset Management

### Improvements
| Feature | Status | Notes |
|---------|--------|-------|
| Asset upload drag-and-drop | planned | Admin interface enhancement |
| Batch asset upload | planned | Multiple file upload |
| Asset search by metadata | planned | Camera, date, location filters |
| Automatic alt text generation | planned | AI-powered (optional) |
| Image optimization on upload | planned | Auto-compress, strip metadata |
| Video transcoding | planned | Web-optimized formats |
| Asset versioning | planned | Replace without breaking links |

### Organization
| Feature | Status | Notes |
|---------|--------|-------|
| Smart folders | planned | Auto-categorize by date/type |
| Duplicate detection UI | planned | Surface hash collisions |
| Unused asset cleanup UI | planned | Admin action for orphans |

---

## API & Integration

### API
| Feature | Status | Notes |
|---------|--------|-------|
| REST API (read-only) | planned | DRF for posts, tags |
| API authentication | planned | Token-based for external tools |
| Webhook support | planned | Post publish notifications |

### External Services
| Feature | Status | Notes |
|---------|--------|-------|
| Webmention support | planned | Send/receive webmentions |
| Analytics integration | planned | Privacy-respecting (Plausible/Umami) |
| Social sharing metadata | planned | OpenGraph, Twitter cards |
| Email newsletter | planned | Digest of new posts |

---

## Frontend

### JavaScript
| Feature | Status | Notes |
|---------|--------|-------|
| Bundle size optimization | planned | Tree shaking, code splitting |
| Service worker | planned | Offline support, caching |
| Lazy load below-fold content | planned | Intersection Observer |

### CSS
| Feature | Status | Notes |
|---------|--------|-------|
| CSS custom property audit | planned | Consolidate variables |
| Component documentation | planned | Style guide page |
| Responsive breakpoint review | planned | Mobile optimization |

---

## Documentation

| Feature | Status | Notes |
|---------|--------|-------|
| CONTRIBUTING.md | planned | Development setup guide |
| API documentation | planned | If API implemented |
| Deployment guide | planned | Railway/Neon setup steps |
| Content authoring guide | planned | Markdown features, asset usage |

---

## Backlog (Future Consideration)

- Multi-author workflows with review
- Content scheduling calendar UI
- A/B testing for titles
- Reading time accuracy improvements
- Automatic related post suggestions
- Comment system (optional)
- Revision history/diff viewing
- Post templates for common formats
- Keyboard shortcuts for navigation
- PWA manifest for installability

---

## Recently Completed

| Feature | Date | Notes |
|---------|------|-------|
| Tag archive view | 2024-12 | Hierarchical tag navigation |
| Table header hover fix | 2024-12 | CSS background-clip fix |
| Escape sequence warning fix | 2024-12 | math_copy_button.py docstring |

---

*Last updated: 2024-12*
