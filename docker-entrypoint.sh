#!/bin/bash
set -e

echo "=== Celery Worker Starting ==="
echo "Working directory: $(pwd)"
echo "User: $(whoami)"
echo "Database file check:"

# The /app directory is owned by 'appuser'.
# The database file should be writable by this user.
# If using a host volume, ensure the host UID/GID matches or permissions are open.
if [ -f "/app/db.sqlite3" ]; then
    echo "✓ Database file exists at /app/db.sqlite3"
    ls -lh /app/db.sqlite3
else
    echo "✗ Database file NOT found at /app/db.sqlite3"
    echo "Available files in /app:"
    ls -la /app/ | head -20
    echo ""
    echo "ERROR: Database not found. Please ensure:"
    echo "  1. You have run migrations on the host."
    echo "  2. The volume mount is correct in docker-compose.yml."
    echo "  3. The database file exists on the host and has correct permissions for user 'appuser'."
    exit 1
fi

echo "=== Starting Celery ==="
exec "$@"
