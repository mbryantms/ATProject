# ==============================================================================
# Stage 1: Builder
#
# This stage installs all Python dependencies into a virtual environment.
# It's kept separate to leverage Docker caching and keep the final image small.
# ==============================================================================
FROM python:3.13-slim as builder

WORKDIR /app

# Create a non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser -d /home/appuser -s /bin/bash appuser
RUN mkdir -p /home/appuser && chown -R appuser:appuser /home/appuser /app

# Install uv for fast dependency management
RUN pip install uv

# Copy dependency files
COPY --chown=appuser:appuser pyproject.toml uv.lock* ./

# Install dependencies into a virtual environment
# This is owned by the appuser to avoid permission issues
USER appuser
RUN uv venv
RUN . .venv/bin/activate && uv pip install --no-cache -r pyproject.toml

# ==============================================================================
# Stage 2: Final Image
#
# This stage copies the pre-built virtual environment and application code
# into a clean image, resulting in a smaller and more secure final artifact.
# ==============================================================================
FROM python:3.13-slim

# Create the same non-root user as in the builder stage
RUN groupadd -r appuser && useradd -r -g appuser -d /home/appuser -s /bin/bash appuser
RUN mkdir -p /home/appuser && chown -R appuser:appuser /home/appuser

# Install system dependencies required at runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
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

# Set working directory
WORKDIR /app
RUN chown appuser:appuser /app

# Copy the virtual environment from the builder stage
COPY --from=builder --chown=appuser:appuser /app/.venv ./.venv

# Set path to use the virtual environment
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Copy the entrypoint script
COPY --chown=appuser:appuser docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Switch to the non-root user
USER appuser

# Copy application code as the non-root user
COPY --chown=appuser:appuser . .

# Set entrypoint and default command
ENTRYPOINT ["/entrypoint.sh"]
CMD ["celery", "-A", "ATProject.celery", "worker", "-l", "info", "--pool=solo"]
