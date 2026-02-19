# ── Build stage ──────────────────────────────────────────────────────
FROM python:3.13-slim AS builder

WORKDIR /build

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip

# Copy package metadata + minimal source for hatchling discovery
COPY pyproject.toml README.md ./
COPY evidentia/__init__.py evidentia/__init__.py

# Install dependencies (cached unless pyproject.toml changes)
RUN pip install --no-cache-dir .[retrieval,pdf]

# Copy full source and reinstall (picks up all modules)
COPY . .
RUN pip install --no-cache-dir --no-deps .

# ── Runtime stage ────────────────────────────────────────────────────
FROM python:3.13-slim AS runtime

# Security: run as non-root user
RUN groupadd -r evidentia && useradd -r -g evidentia -d /app -s /sbin/nologin evidentia

WORKDIR /app

# Install runtime system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --from=builder /build /app

# Ensure correct ownership
RUN chown -R evidentia:evidentia /app

USER evidentia

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run with gunicorn in production
CMD ["gunicorn", "evidentia.api.server:app", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "-c", "gunicorn.conf.py"]
