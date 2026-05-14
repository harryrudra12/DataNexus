# DataNexus Era 3 — API Service Dockerfile
# Local MVP-safe Dockerfile

# ─── STAGE 1: BUILDER ────────────────────────────────────────
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .

RUN pip install --upgrade pip setuptools wheel && \
    pip install --default-timeout=300 --retries 15 --prefer-binary --no-cache-dir -r requirements.txt


# ─── STAGE 2: RUNTIME ────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="DataNexus API"
LABEL org.opencontainers.image.description="DataNexus Era 3 API Service"
LABEL org.opencontainers.image.vendor="DataNexus"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system datanexus \
    && useradd --system --gid datanexus --no-create-home --shell /bin/false datanexus

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

COPY --chown=datanexus:datanexus app/ ./app/

USER datanexus

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl --fail --silent http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]