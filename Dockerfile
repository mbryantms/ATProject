FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install system dependencies for Pillow, SQLite, and other libraries
RUN apt-get update && apt-get install -y \
    gcc \
    libjpeg-dev \
    zlib1g-dev \
    libfreetype6-dev \
    liblcms2-dev \
    libopenjp2-7-dev \
    libtiff5-dev \
    libwebp-dev \
    ffmpeg \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml uv.lock* ./

# Install uv for fast dependency management
RUN pip install uv

# Install Python dependencies
RUN uv pip install --system -r pyproject.toml

# Copy application code
COPY . .

# Set Python path
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Create entrypoint script to handle permissions and verify database
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
echo "=== Celery Worker Starting ==="\n\
echo "Working directory: $(pwd)"\n\
echo "Database file check:"\n\
if [ -f "/app/db.sqlite3" ]; then\n\
    echo "✓ Database file exists at /app/db.sqlite3"\n\
    ls -lh /app/db.sqlite3\n\
    # Set permissions\n\
    chmod 666 /app/db.sqlite3 2>/dev/null || echo "⚠ Could not change db.sqlite3 permissions"\n\
    chmod 666 /app/db.sqlite3-wal 2>/dev/null || echo "ℹ No WAL file yet"\n\
    chmod 666 /app/db.sqlite3-shm 2>/dev/null || echo "ℹ No SHM file yet"\n\
else\n\
    echo "✗ Database file NOT found at /app/db.sqlite3"\n\
    echo "Available files in /app:"\n\
    ls -la /app/ | head -20\n\
    echo ""\n\
    echo "ERROR: Database not found. Please ensure:"\n\
    echo "  1. You have run migrations on the host"\n\
    echo "  2. The volume mount is correct in docker-compose.yml"\n\
    echo "  3. The database file exists on the host"\n\
    exit 1\n\
fi\n\
\n\
echo "=== Starting Celery ==="\n\
exec "$@"\n' > /entrypoint.sh && chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]

# Default command (can be overridden in docker-compose)
CMD ["celery", "-A", "celery_app", "worker", "-l", "info", "--pool=solo"]
