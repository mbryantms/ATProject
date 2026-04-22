# Deployment Guide: Neon + Railway

This guide walks through deploying ATProject to **Neon** (serverless PostgreSQL) and **Railway** (application hosting with Redis and Celery workers).

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Railway                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Web        │  │   Worker     │  │   Beat       │          │
│  │  (Gunicorn)  │  │  (Celery)    │  │  (Celery)    │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
│         │                 │                 │                   │
│         └────────┬────────┴────────┬────────┘                   │
│                  │                 │                            │
│           ┌──────▼──────┐   ┌──────▼──────┐                    │
│           │    Redis    │   │   Shared    │                    │
│           │   (Broker)  │   │   Env Vars  │                    │
│           └─────────────┘   └─────────────┘                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │      Neon       │
                    │   PostgreSQL    │
                    │  (Serverless)   │
                    └─────────────────┘
```

---

## Part 1: Set Up Neon Database

### Step 1.1: Create Neon Account & Project

1. Go to [neon.tech](https://neon.tech) and sign up
2. Click **"New Project"**
3. Configure:
   - **Name**: `atproject-prod` (or your preference)
   - **Region**: Choose closest to your Railway region (e.g., `us-east-1`)
   - **PostgreSQL Version**: 16 (recommended)
4. Click **"Create Project"**

### Step 1.2: Get Connection Details

1. In your Neon dashboard, go to **Connection Details**
2. Select **"Pooled connection"** (recommended for serverless)
3. Copy the connection string. It will look like:
   ```
   postgresql://username:password@ep-xxx-xxx-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require
   ```

4. Note the **Endpoint ID** from the hostname (the `ep-xxx-xxx` part) - you'll need this for `NEON_ENDPOINT_ID`

### Step 1.3: Understanding Neon Connection Types

| Type | Hostname | Use Case |
|------|----------|----------|
| **Direct** | `ep-xxx.us-east-1.aws.neon.tech` | Migrations, long-running queries |
| **Pooled** | `ep-xxx-pooler.us-east-1.aws.neon.tech` | Application connections (recommended) |

**For this deployment, use the pooled connection** for the web app and workers.

---

## Part 2: Set Up Railway Project

### Step 2.1: Create Railway Account & Project

1. Go to [railway.app](https://railway.app) and sign up
2. Click **"New Project"** → **"Empty Project"**
3. Name it `atproject` or your preference

### Step 2.2: Add Redis Service

1. In your Railway project, click **"+ New"** → **"Database"** → **"Redis"**
2. Railway will provision a Redis instance
3. Note: The `REDIS_URL` will be automatically available to linked services

### Step 2.3: Deploy Web Service from GitHub

1. Click **"+ New"** → **"GitHub Repo"**
2. Select your ATProject repository
3. Railway will detect the `Procfile` and `requirements.txt`
4. **Important**: In the service settings:
   - Go to **Settings** → **Deploy**
   - Set **Start Command** to: `web` (this uses the `web:` line from Procfile)
   - Or manually: `gunicorn ATProject.wsgi:application --bind 0.0.0.0:$PORT`

### Step 2.4: Deploy Celery Worker Service

1. Click **"+ New"** → **"GitHub Repo"** (same repo)
2. In service settings:
   - Rename to `worker`
   - Go to **Settings** → **Deploy**
   - Set **Start Command** to: `celery -A ATProject worker --loglevel=info --concurrency=2`

### Step 2.5: Deploy Celery Beat Service

1. Click **"+ New"** → **"GitHub Repo"** (same repo)
2. In service settings:
   - Rename to `beat`
   - Go to **Settings** → **Deploy**
   - Set **Start Command** to: `celery -A ATProject beat --loglevel=info`
   - **Note**: The default scheduler is file-based (`celery.beat:PersistentScheduler`), which avoids constant DB polling. Only use `--scheduler django_celery_beat.schedulers:DatabaseScheduler` if you need to edit schedules dynamically via the Django admin (this polls the DB every 5 seconds, adding ~17K queries/day).

### Step 2.6 (Optional): Deploy Flower Dashboard

Flower is already in `pyproject.toml`; use it for a persistent, full-featured Celery dashboard beyond the in-admin **Live Celery status** page. Skip this step if the admin page is enough — Flower costs a small amount per month for a dedicated service.

1. Click **"+ New"** → **"GitHub Repo"** (same repo)
2. In service settings:
   - Rename to `flower`
   - Go to **Settings** → **Deploy**
   - Set **Start Command** to (the outer `sh -c '…'` is required — Railway runs start commands without a shell, so `$PORT` and `$FLOWER_BASIC_AUTH` would otherwise be passed to Flower literally and crash on `int('$PORT')`):
     ```
     sh -c 'celery -A ATProject flower --address=0.0.0.0 --port=$PORT --basic_auth=$FLOWER_BASIC_AUTH --url_prefix=flower --persistent=true --db=/tmp/flower.db --max_tasks=10000'
     ```
   - Go to **Settings** → **Networking** → **Generate Domain** (or attach a custom domain)
3. Set service-level environment variables (or inherit from the project):
   - `CELERY_BROKER_URL` — same Redis URL the web/worker services use (Railway's shared-variables pattern handles this automatically)
   - `FLOWER_BASIC_AUTH` — `admin:SOME_STRONG_PASSWORD`, required to gate the dashboard behind HTTP basic auth. **Do not skip this** — Flower exposes task payloads including asset IDs and markdown content.
   - `FLOWER_UNAUTHENTICATED_API=false` — blocks the JSON API endpoints to anonymous callers
4. Visit `https://<flower-service>.up.railway.app/flower/` (note the `/flower/` prefix matches `--url_prefix`); log in with the credentials from `FLOWER_BASIC_AUTH`.

**What Flower gives you beyond the in-admin status page**:

- Persistent task history (the `--persistent=true --db=/tmp/flower.db` flags store up to `--max_tasks` task records, survives restarts of the Flower service but not the container's ephemeral disk)
- Graphs of success/failure rate over time
- Per-task click-through with full args, result, traceback, runtime breakdown
- Broadcast commands: revoke running tasks, rate-limit a queue, shut down a worker remotely

**What Flower does *not* give you**:

- Durable history across container restarts (use Sentry or the lightweight task-event log pattern for that)
- Per-asset filtering (the admin `processing_state` widget is better for that — it scopes by the asset you're viewing)

**Running Flower locally** (without a dedicated Railway service):

```bash
uv run celery -A ATProject flower --address=127.0.0.1 --port=5555 --basic_auth=admin:devpass
```
Visit `http://127.0.0.1:5555/` (no URL prefix locally).

---

## Part 3: Configure Environment Variables

### Step 3.1: Set Shared Variables

In Railway, you can set variables at the project level to share across services.

1. Go to your Railway project
2. Click **"Variables"** tab (project-level)
3. Add the following variables:

#### Required Variables

```bash
# Django Core
SECRET_KEY=your-secure-random-key-here-use-django-secret-key-generator
DEBUG=False
ALLOWED_HOSTS=your-app.up.railway.app,your-custom-domain.com

# Database (from Neon - use pooled connection)
DATABASE_URL=postgresql://username:password@ep-xxx-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require

# Neon-specific (extract from your endpoint hostname)
NEON_ENDPOINT_ID=ep-xxx-xxx

# Database connection settings for Neon serverless
# These are now the defaults in settings.py — only override if needed
# DB_CONN_MAX_AGE=0                    # default: 0 (close after each request; enables Neon auto-suspend)
# DB_DISABLE_SERVER_SIDE_CURSORS=True  # default: True (required for Neon pooler)
DB_HEALTH_CHECKS=True
DB_SSL_REQUIRE=True
DB_CONNECT_TIMEOUT_S=10
DB_APP_NAME=atproject-railway

# Redis (Railway provides this automatically when Redis is linked)
# REDIS_URL=redis://default:xxx@xxx.railway.internal:6379
```

#### R2/S3 Storage Variables (if using Cloudflare R2)

```bash
R2_ACCESS_KEY_ID=your-r2-access-key
R2_SECRET_ACCESS_KEY=your-r2-secret-key
R2_BUCKET_NAME=your-bucket-name
R2_S3_ENDPOINT_URL=https://your-account-id.r2.cloudflarestorage.com
R2_CUSTOM_DOMAIN=cdn.yourdomain.com
R2_SIGNED_URLS=False
```

### Step 3.2: Link Redis to Services

1. Click on each service (web, worker, beat)
2. Go to **Variables** → **Reference Variables**
3. Add reference to `REDIS_URL` from the Redis service

Alternatively, set `REDIS_URL` manually using the Redis connection string from Railway's Redis service.

---

## Part 4: Run Migrations

### Option A: Railway Console (Recommended)

1. Go to your **web** service in Railway
2. Click **"..."** menu → **"Open Shell"**
3. Run:
   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   ```

### Option B: Using Release Command

The `Procfile` includes a `release` command that runs migrations automatically on each deploy:

```
release: python manage.py migrate --noinput
```

To enable this in Railway:
1. Go to web service **Settings** → **Deploy**
2. Enable **"Run release command"**
3. Railway will run `python manage.py migrate --noinput` before each deployment

---

## Part 5: Configure Custom Domain (Optional)

### Step 5.1: Add Domain in Railway

1. Go to your **web** service
2. Click **Settings** → **Networking** → **"Generate Domain"** or **"Custom Domain"**
3. For custom domains, add your domain (e.g., `blog.yourdomain.com`)

### Step 5.2: Update DNS

Add a CNAME record pointing to Railway's domain:
```
blog.yourdomain.com  CNAME  your-app.up.railway.app
```

### Step 5.3: Update Environment Variables

Add your domain to `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`:

```bash
ALLOWED_HOSTS=your-app.up.railway.app,blog.yourdomain.com
CSRF_TRUSTED_ORIGINS=https://blog.yourdomain.com
```

---

## Part 6: Verify Deployment

### Step 6.1: Check Health Endpoint

```bash
curl https://your-app.up.railway.app/health/
# Should return: {"status": "ok"}
```

### Step 6.2: Check Admin Access

1. Visit `https://your-app.up.railway.app/admin/`
2. Log in with the superuser credentials you created

### Step 6.3: Check Celery Workers

1. Go to Railway dashboard → **worker** service → **Logs**
2. You should see: `celery@xxx ready.`

### Step 6.4: Test Background Tasks

1. Create or edit a Post in the admin
2. Check worker logs for `update_post_derived_content` task execution
3. Verify the table of contents is populated

---

## Environment Variables Reference

### Complete List

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SECRET_KEY` | Yes | - | Django secret key |
| `DEBUG` | No | `False` | Debug mode (never True in prod) |
| `ALLOWED_HOSTS` | Yes | - | Comma-separated hostnames |
| `DATABASE_URL` | Yes | - | Neon PostgreSQL connection string |
| `REDIS_URL` | Yes | - | Redis connection string |
| `NEON_ENDPOINT_ID` | No | - | Neon endpoint for pooled connections |
| `DB_CONN_MAX_AGE` | No | `0` | Connection lifetime in seconds (0 = close after each request, enables Neon auto-suspend) |
| `DB_HEALTH_CHECKS` | No | `True` | Verify connections before reuse |
| `DB_SSL_REQUIRE` | No | `True` | Require SSL for database |
| `DB_DISABLE_SERVER_SIDE_CURSORS` | No | `True` | Required for Neon pooler |
| `R2_ACCESS_KEY_ID` | Yes* | - | R2/S3 access key |
| `R2_SECRET_ACCESS_KEY` | Yes* | - | R2/S3 secret key |
| `R2_BUCKET_NAME` | Yes* | - | Storage bucket name |
| `R2_S3_ENDPOINT_URL` | Yes* | - | R2/S3 endpoint URL |
| `R2_CUSTOM_DOMAIN` | No | - | CDN domain for media |

*Required if using R2/S3 for media storage

---

## Troubleshooting

### Database Connection Issues

**Error**: `connection refused` or `timeout`

1. Verify `DATABASE_URL` is correct
2. Ensure using `-pooler` hostname for Neon
3. Check `DB_SSL_REQUIRE=True`
4. Set `DB_DISABLE_SERVER_SIDE_CURSORS=True` for pooled connections

### Static Files Not Loading

**Error**: 404 on CSS/JS files

1. Ensure `python manage.py collectstatic` ran during build
2. Check `STATIC_URL` and `STATIC_ROOT` settings
3. Verify WhiteNoise middleware is enabled

### Celery Tasks Not Running

**Symptoms**: Posts not generating TOC

1. Check worker logs in Railway
2. Verify `REDIS_URL` is accessible from worker service
3. Ensure Redis service is running
4. Test manually:
   ```bash
   # In Railway shell
   python manage.py shell
   >>> from engine.tasks import update_post_derived_content
   >>> result = update_post_derived_content.delay(1)
   >>> print(result.get(timeout=30))
   ```

### CSRF Errors on Forms

**Error**: `CSRF verification failed`

1. Add your domain to `CSRF_TRUSTED_ORIGINS`:
   ```bash
   CSRF_TRUSTED_ORIGINS=https://your-domain.com,https://your-app.up.railway.app
   ```

---

## Cost Optimization

### Neon Free Tier
- 0.5 GB storage
- 24/7 availability on primary branch
- Autoscaling compute

### Railway Pricing
- **Hobby Plan**: $5/month + usage
- **Pro Plan**: $20/month with team features

### Tips
1. Use Neon's **Auto-suspend** to reduce costs during low traffic
2. Scale down worker concurrency: `--concurrency=1`
3. Consider combining worker and beat into one service for small deployments:
   ```bash
   celery -A ATProject worker --beat --loglevel=info
   ```

---

## Security Checklist

- [ ] `DEBUG=False` in production
- [ ] Strong `SECRET_KEY` (use `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`)
- [ ] `ALLOWED_HOSTS` contains only your domains
- [ ] SSL/TLS enabled (Railway handles this)
- [ ] Database using SSL (`sslmode=require`)
- [ ] R2/S3 credentials are access-limited
- [ ] Admin URL optionally changed from `/admin/`
- [ ] HSTS enabled after confirming HTTPS works: `DJANGO_SECURE_HSTS_SECONDS=31536000`
