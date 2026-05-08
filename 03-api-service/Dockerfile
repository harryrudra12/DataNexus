# DataNexus Era 3 — API Service Dockerfile
# Multi-stage build: builder installs dependencies, runtime copies only what's needed.
# Final image: ~180 MB, runs as non-root user.

# ─── STAGE 1: BUILDER ────────────────────────────────────────
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies into a virtualenv we'll copy to the runtime image
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ─── STAGE 2: RUNTIME ────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Metadata
LABEL org.opencontainers.image.title="DataNexus API"
LABEL org.opencontainers.image.description="DataNexus Era 3 — open-source data fabric"
LABEL org.opencontainers.image.vendor="DataNexus"
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/datanexus/core"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app

# Install runtime essentials only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user — never run as root in production
RUN groupadd --system --gid 1000 datanexus \
    && useradd --system --uid 1000 --gid datanexus --no-create-home --shell /bin/false datanexus

# Copy virtualenv from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application code
WORKDIR /app
COPY --chown=datanexus:datanexus app/ ./app/

# Drop privileges
USER datanexus

EXPOSE 8000

# Healthcheck — Kubernetes will use this if liveness probes are not configured
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl --fail --silent http://localhost:8000/health || exit 1

# Run with uvicorn — production should use gunicorn-uvicorn workers behind a load balancer
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--loop", "uvloop", \
     "--http", "httptools", \
     "--log-config", "/dev/null", \
     "--no-access-log"]
