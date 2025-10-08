#!/bin/bash
# Celery startup script for Linux/WSL

echo "Starting Celery worker..."
echo ""
echo "Platform: $(uname -s)"
echo ""

# Check if running on Windows (Git Bash, Cygwin, etc.)
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
    echo "Detected Windows environment - using --pool=solo"
    celery -A celery_app worker -l info --pool=solo
else
    echo "Detected Unix/Linux environment - using default pool"
    celery -A celery_app worker -l info
fi
