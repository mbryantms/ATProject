# syntax=docker/dockerfile:1

# -- Stage 1: Node.js builder --
# Builds frontend CSS/JS assets and installs citeproc-js production deps.
# This stage is discarded — only built artifacts are copied to production.
FROM node:24-slim AS node-builder

WORKDIR /app

# Install root frontend dependencies (esbuild, PostCSS, etc.)
COPY package.json package-lock.json ./
RUN npm ci

# Install citeproc-js (production runtime dependency, separate package.json)
COPY engine/bibliography/package.json engine/bibliography/package-lock.json engine/bibliography/
RUN cd engine/bibliography && npm ci --omit=dev

# Copy source files needed for frontend build
COPY static/ static/
COPY postcss.config.mjs ./

# Build CSS and JS
RUN npm run build


# -- Stage 2: Python production image --
FROM python:3.14-slim

# uv installs the locked Python dependencies straight from uv.lock, so there is
# no separately-maintained requirements.txt to drift out of sync (Dependabot
# bumps pyproject.toml + uv.lock and the image follows). Pinned so the build is
# reproducible; Dependabot's docker ecosystem tracks this tag.
COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /uvx /bin/

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Install into the image's system Python (no venv) so `python`, `gunicorn`,
# `celery` etc. resolve exactly as they did with pip, and never download a
# separate interpreter.
ENV UV_PROJECT_ENVIRONMENT=/usr/local \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy

# Set work directory
WORKDIR /app

# Install system dependencies
# - gcc / libpq-dev: build-time for psycopg
# - ffmpeg: provides `ffprobe`, used by the asset pipeline to extract video
#   dimensions / duration / bitrate / frame-rate on upload.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy Node.js runtime from builder stage (for citeproc-js subprocess only)
COPY --from=node-builder /usr/local/bin/node /usr/local/bin/node

# Install Python dependencies (production only, exact versions from uv.lock).
# --frozen fails the build if uv.lock is out of date with pyproject.toml rather
# than silently re-resolving. The project itself isn't a package, so nothing
# else is installed at this layer and it caches until the lock changes.
# No BuildKit cache mount here: Railway's builder rejects cache mounts without
# a service-scoped `id=` (GitHub's buildx accepts the anonymous form, so CI
# would not catch it). --no-cache keeps uv's download cache out of the layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --no-cache

# Create non-root user
RUN adduser --disabled-password --gecos '' appuser

# Copy project files
COPY --chown=appuser:appuser . .

# Copy built frontend assets from node-builder (overwrite any local dist files)
COPY --from=node-builder --chown=appuser:appuser /app/static/css/dist/ static/css/dist/
COPY --from=node-builder --chown=appuser:appuser /app/static/js/dist/ static/js/dist/

# Copy citeproc-js node_modules (production deps only, no devDependencies)
COPY --from=node-builder --chown=appuser:appuser /app/engine/bibliography/node_modules/ engine/bibliography/node_modules/

# Collect static files (uses dummy values for required env vars during build)
RUN SECRET_KEY=build-placeholder \
    DATABASE_URL=postgres://placeholder:placeholder@placeholder:5432/placeholder \
    REDIS_URL=redis://placeholder:6379 \
    python manage.py collectstatic --noinput

# Railway uses dynamic PORT env var
ENV PORT=8000
EXPOSE $PORT

# Switch to non-root user
USER appuser

# Run migrations then start gunicorn (shell form to expand $PORT)
# The -c flag loads gunicorn.conf.py which includes post_fork hooks
# to close inherited DB connections — critical for Neon auto-suspend.
CMD python manage.py migrate --noinput && gunicorn -c gunicorn.conf.py ATProject.wsgi:application
