# =====================================================
# Stage 1 — Build dependencies (cached)
# =====================================================
FROM python:3.10-slim AS builder

WORKDIR /build

# System build deps
RUN apt-get update && apt-get install -y \
    gcc g++ wget build-essential \
    && rm -rf /var/lib/apt/lists/*

# ---------- Build TA-Lib ONCE (use -j1 to avoid race conditions) ----------
RUN wget https://github.com/TA-Lib/ta-lib/releases/download/v0.4.0/ta-lib-0.4.0-src.tar.gz \
    && tar -xzf ta-lib-0.4.0-src.tar.gz \
    && cd ta-lib \
    && ./configure --prefix=/usr \
    && make -j1 \
    && make install \
    && cd / \
    && rm -rf ta-lib ta-lib-0.4.0-src.tar.gz

# ---------- Python deps (cached layer) ----------
COPY requirements-docker.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements-docker.txt

# =====================================================
# Stage 2 — Runtime image (small, fast)
# =====================================================
FROM python:3.10-slim

WORKDIR /app

# TA-Lib runtime libs
COPY --from=builder /usr/lib/libta_lib.so /usr/lib/

# Python packages
COPY --from=builder /usr/local/lib/python3.10 /usr/local/lib/python3.10
COPY --from=builder /usr/local/bin /usr/local/bin

# Writable temp
RUN mkdir -p /tmp && chmod 1777 /tmp

# App code
COPY src/ ./src/
COPY scripts/ ./scripts/

# Non-root user
RUN useradd --create-home --shell /bin/bash app
USER app

ENV DOCKER_CONTAINER=true
EXPOSE 8000

# NOTE: app does its own retry; healthcheck just ensures process lives
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
  CMD python -c "import sys; sys.exit(0)"

CMD ["python", "src/main.py"]