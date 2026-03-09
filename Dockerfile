# ── ARMGUARD RDS V1 — Dockerfile ────────────────────────────────────────────
# Multi-stage build: builder installs wheels, runner copies only what's needed.
# Base image: Python 3.12-slim (Debian Bookworm slim).
#
# Build & run:
#   docker build -t armguard-rds .
#   docker run --env-file .env -p 8000:8000 armguard-rds

# ── Stage 1: builder ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# System deps needed only for wheel compilation (Pillow, lxml, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libmupdf-dev \
        libjpeg-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt


# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS runner

# Non-root user: principle of least privilege.
RUN useradd --no-log-init -r -m armguard
WORKDIR /app

# Runtime libs for Pillow / PyMuPDF.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libmupdf-dev \
        libjpeg62-turbo \
    && rm -rf /var/lib/apt/lists/*

# Install pre-built wheels from the builder stage.
COPY --from=builder /wheels /wheels
RUN pip install --no-index --find-links=/wheels /wheels/*.whl \
 && rm -rf /wheels

# Copy application source.
COPY project/ .

# Collect static files so WhiteNoise can serve them.
RUN python manage.py collectstatic --noinput --settings=armguard.settings.production 2>/dev/null || true

USER armguard

EXPOSE 8000

# Gunicorn: 2 workers per CPU core.  Override CMD in docker-compose for dev.
CMD ["python", "-m", "gunicorn", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "2", \
     "--timeout", "60", \
     "armguard.wsgi:application"]
