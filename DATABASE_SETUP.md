# PostgreSQL Database Setup for ATProject (Arch Linux)

This guide walks you through setting up PostgreSQL on Arch Linux for the ATProject Django application.

## Overview

ATProject is a Django-based content management system with the following database structure:
- **Posts**: Content management with markdown support, taxonomy, and internal linking
- **Assets**: Media library with renditions, metadata extraction, and organization
- **Taxonomy**: Tags, categories, and series for content organization
- **Celery**: Background task processing with Django-Celery-Beat for scheduling

## Prerequisites

- Arch Linux system
- Python 3.13+ installed
- Basic terminal knowledge

## 1. Install PostgreSQL

### Install PostgreSQL package
```bash
sudo pacman -S postgresql
```

### Initialize the database cluster
```bash
sudo -u postgres initdb -D /var/lib/postgres/data
```

### Enable and start PostgreSQL service
```bash
sudo systemctl enable postgresql.service
sudo systemctl start postgresql.service
```

### Verify PostgreSQL is running
```bash
sudo systemctl status postgresql.service
```

## 2. Create Database and User

### Switch to postgres user
```bash
sudo -u postgres psql
```

### Execute the following SQL commands

```sql
-- Create database
CREATE DATABASE atproject;

-- Create user with password
CREATE USER atproject_user WITH PASSWORD 'your_secure_password_here';

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE atproject TO atproject_user;

-- Connect to the database
\c atproject

-- Grant schema privileges (PostgreSQL 15+)
GRANT ALL ON SCHEMA public TO atproject_user;

-- Grant default privileges for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO atproject_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO atproject_user;

-- Exit psql
\q
```

## 3. Install Redis (for Celery)

ATProject uses Celery with Redis as the message broker.

### Install Redis
```bash
sudo pacman -S redis
```

### Enable and start Redis service
```bash
sudo systemctl enable redis.service
sudo systemctl start redis.service
```

### Verify Redis is running
```bash
redis-cli ping
# Should return: PONG
```

## 4. Configure Environment Variables

Create a `.env` file in the project root (`/home/matthew/Documents/ATProject/.env`):

```bash
# =============================================================================
# DJANGO CORE SETTINGS
# =============================================================================

# Django Secret Key (generate a new one for production)
# Generate with: python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
SECRET_KEY=django-insecure-REPLACE_WITH_SECURE_KEY_FOR_PRODUCTION

# Debug mode (set to False in production)
DEBUG=True

# Allowed hosts (comma-separated list)
ALLOWED_HOSTS=localhost,127.0.0.1

# Admin emails (comma-separated list of email addresses)
ADMINS=admin@example.com

# =============================================================================
# DATABASE SETTINGS
# =============================================================================

# Database URL format: postgres://USER:PASSWORD@HOST:PORT/NAME
DATABASE_URL=postgres://atproject_user:your_secure_password_here@localhost:5432/atproject

# Connection pooling and performance settings
DB_CONN_MAX_AGE=60
DB_HEALTH_CHECKS=True
DB_USE_ATOMIC_REQUESTS=False

# SSL settings (set to False for local development, True for production)
DB_SSL_REQUIRE=False

# Timeout settings (in milliseconds/seconds)
DB_CONNECT_TIMEOUT_S=5
DB_STATEMENT_TIMEOUT_MS=15000
DB_IDLE_TX_TIMEOUT_MS=10000
DB_LOCK_TIMEOUT_MS=2000

# Application name (shows in pg_stat_activity)
DB_APP_NAME=atproject

# Target session attributes
DB_TARGET_SESSION_ATTRS=read-write

# Disable server-side cursors (set to True if using PgBouncer transaction pooling)
DB_DISABLE_SERVER_SIDE_CURSORS=False

# =============================================================================
# REDIS/CELERY SETTINGS
# =============================================================================

# Redis URL for Celery broker
REDIS_URL=redis://localhost:6379/0

# =============================================================================
# CLOUDFLARE R2 / S3 STORAGE SETTINGS
# =============================================================================
# Required for media storage (images, videos, documents)

# R2 Access credentials
R2_ACCESS_KEY_ID=cadd7a178e795f2e0ae2565c55d3bd65
R2_SECRET_ACCESS_KEY=your_r2_secret_access_key

# R2 Bucket configuration
R2_BUCKET_NAME=your_bucket_name
R2_S3_ENDPOINT_URL=https://ACCOUNT_ID.r2.cloudflarestorage.com

# R2 Region and signature
R2_REGION=auto
R2_SIG_VERSION=s3v4
R2_ADDRESSING_STYLE=path

# URL behavior (False for public URLs, True for signed URLs)
R2_SIGNED_URLS=False

# Custom domain for R2 bucket (optional)
# Leave blank if not using a custom domain
# Example: cdn.example.com or pub-xxxx.r2.dev
R2_CUSTOM_DOMAIN=

# Cache control header
R2_CACHE_CONTROL=public, max-age=31536000, immutable
```

## 5. Install Python Dependencies

### Using uv (recommended - already set up in the project)
```bash
cd /home/matthew/Documents/ATProject
uv sync
```

### Or using pip
```bash
cd /home/matthew/Documents/ATProject
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## 6. Run Database Migrations

### Activate virtual environment (if not already activated)
```bash
source .venv/bin/activate
```

### Apply migrations
```bash
python manage.py migrate
```

This will create all necessary database tables:
- **Auth & Admin**: Django built-in authentication and admin tables
- **Celery**: django_celery_results and django_celery_beat tables
- **Posts**: Post, InternalLink tables
- **Taxonomy**: Tag, TagAlias, Category, Series tables
- **Assets**: Asset, AssetMetadata, AssetRendition, PostAsset tables
- **Organization**: AssetFolder, AssetTag, AssetCollection tables

## 7. Create Superuser

Create an admin account to access the Django admin interface:

```bash
python manage.py createsuperuser
```

Follow the prompts to set username, email, and password.

## 8. Collect Static Files

```bash
python manage.py collectstatic --noinput
```

## 9. Start the Development Server

### Terminal 1: Django development server
```bash
python manage.py runserver
```

### Terminal 2: Celery worker (for background tasks)
```bash
celery -A ATProject worker --loglevel=info
```

### Terminal 3: Celery Beat (for scheduled tasks)
```bash
celery -A ATProject beat --loglevel=info
```

### Optional: Flower (Celery monitoring web UI)
```bash
celery -A ATProject flower
```
Access at: http://localhost:5555

## 10. Access the Application

- **Main Application**: http://localhost:8000
- **Admin Interface**: http://localhost:8000/admin
- **Flower (if running)**: http://localhost:5555

## Database Management Commands

### Backup database
```bash
pg_dump -U atproject_user atproject > backup_$(date +%Y%m%d_%H%M%S).sql
```

### Restore database
```bash
psql -U atproject_user atproject < backup_file.sql
```

### Access database via psql
```bash
psql -U atproject_user -d atproject
```

### Check database size
```sql
SELECT pg_size_pretty(pg_database_size('atproject'));
```

## Custom Management Commands

ATProject includes several useful management commands:

### Rebuild internal backlinks between posts
```bash
python manage.py rebuild_backlinks
```

### Generate asset renditions (thumbnails, responsive images)
```bash
python manage.py generate_renditions
```

### Cleanup unused assets
```bash
python manage.py cleanup_assets
```

## Troubleshooting

### PostgreSQL connection refused
- Check if PostgreSQL is running: `sudo systemctl status postgresql`
- Check if PostgreSQL is listening: `sudo ss -tlnp | grep 5432`
- Verify DATABASE_URL in .env file

### Redis connection error
- Check if Redis is running: `sudo systemctl status redis`
- Test connection: `redis-cli ping`

### Permission denied errors
- Ensure the user has proper permissions on the database
- Re-run the GRANT commands from step 2

### Static files not loading
- Run: `python manage.py collectstatic`
- Check STATIC_ROOT and STATIC_URL in settings.py

### Celery tasks not running
- Ensure Redis is running
- Check REDIS_URL in .env
- Verify Celery worker and beat are running

### Asset uploads failing
- Verify R2/S3 credentials in .env
- Check R2_BUCKET_NAME and R2_S3_ENDPOINT_URL
- For local development, you may want to configure local media storage

## Production Deployment Notes

For production deployment:

1. **Set DEBUG=False** in .env
2. **Generate a new SECRET_KEY** (don't use the development key)
3. **Enable SSL for database**: Set DB_SSL_REQUIRE=True
4. **Configure ALLOWED_HOSTS** with your domain
5. **Use a production WSGI server** (gunicorn, uwsgi)
6. **Set up a reverse proxy** (nginx, caddy)
7. **Configure R2/S3 properly** for media storage
8. **Use a process supervisor** (systemd, supervisor) for Celery workers
9. **Set up proper logging** and monitoring
10. **Configure backups** for database and media files

## Security Considerations

- **Change default passwords** in .env file
- **Use strong SECRET_KEY** for production
- **Enable SSL/TLS** for PostgreSQL in production
- **Restrict database access** using PostgreSQL pg_hba.conf
- **Use Redis password** in production
- **Keep dependencies updated**: `uv sync --upgrade`
- **Configure firewall** to restrict access to PostgreSQL and Redis

## Additional Resources

- Django Documentation: https://docs.djangoproject.com/
- PostgreSQL Documentation: https://www.postgresql.org/docs/
- Celery Documentation: https://docs.celeryq.dev/
- Arch Wiki - PostgreSQL: https://wiki.archlinux.org/title/PostgreSQL
- Cloudflare R2 Documentation: https://developers.cloudflare.com/r2/
