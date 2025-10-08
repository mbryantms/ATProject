@echo off
REM Celery startup script for Windows
REM Uses solo pool to avoid Windows multiprocessing issues

echo Starting Celery worker for Windows...
echo.
echo Note: Using --pool=solo for Windows compatibility
echo For better performance, consider running in WSL or Linux
echo.

celery -A celery_app worker -l info --pool=solo

pause
