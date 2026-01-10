# =============================================================================
# Backend Dockerfile - ios-screen-time-screenshot-processing
# =============================================================================
# Python 3.12 with FastAPI, Tesseract OCR, and async PostgreSQL support
#
# Build context: monorepo root (../../..)
# docker build -f apps/ios-screen-time-screenshot-processing/docker/backend/Dockerfile .

# --- Builder stage: compile PyO3 Rust extension ---
FROM python:3.12-slim AS rust-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl build-essential libtesseract-dev libleptonica-dev libclang-dev patchelf \
    && rm -rf /var/lib/apt/lists/*

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

RUN pip install --no-cache-dir maturin

COPY apps/ios-screen-time-screenshot-processing/crates/ /tmp/crates/
COPY apps/ios-screen-time-screenshot-processing/rust-python/ /tmp/rust-python/

RUN cd /tmp/rust-python && maturin build --release --interpreter python3.12

# --- Runtime stage ---
FROM python:3.12-slim

# Install system dependencies including Tesseract OCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libtesseract-dev \
    libleptonica-dev \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install uv for faster package installation
RUN pip install --no-cache-dir uv

# Copy shared monorepo packages first (for layer caching)
COPY packages/global-pass-honor-username-auth /app/packages/global-pass-honor-username-auth
COPY packages/fastapi-errors /app/packages/fastapi-errors
COPY packages/fastapi-logging /app/packages/fastapi-logging
COPY packages/fastapi-ratelimit /app/packages/fastapi-ratelimit
COPY packages/db-toolkit /app/packages/db-toolkit
COPY packages/fastapi-pagination /app/packages/fastapi-pagination
COPY packages/fastapi-files /app/packages/fastapi-files
COPY packages/fastapi-tasks /app/packages/fastapi-tasks

# Copy app dependency files
COPY apps/ios-screen-time-screenshot-processing/pyproject.toml ./

# Copy preprocessing packages (local dependencies from app's docker/backend/packages/)
COPY apps/ios-screen-time-screenshot-processing/docker/backend/packages/ios-device-detector /opt/packages/ios-device-detector
COPY apps/ios-screen-time-screenshot-processing/docker/backend/packages/ipad-screenshot-cropper /opt/packages/ipad-screenshot-cropper
COPY apps/ios-screen-time-screenshot-processing/docker/backend/packages/phi-detector-remover /opt/packages/phi-detector-remover

# Create minimal src structure needed for editable install
RUN mkdir -p src/screenshot_processor && \
    touch src/screenshot_processor/__init__.py

# Install shared packages by path (before app dependencies)
RUN uv pip install --system --no-cache-dir \
    /app/packages/global-pass-honor-username-auth \
    /app/packages/fastapi-errors \
    /app/packages/fastapi-logging \
    /app/packages/fastapi-ratelimit \
    /app/packages/db-toolkit \
    /app/packages/fastapi-pagination \
    /app/packages/fastapi-files \
    /app/packages/fastapi-tasks

# Install app dependencies (cached unless pyproject.toml changes)
RUN uv pip install --system --no-cache-dir -e ".[web,preprocessing]" alembic

# Install PyO3 Rust extension (screenshot_processor_rs — leptess OCR via C API)
COPY --from=rust-builder /tmp/rust-python/target/wheels/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm -f /tmp/*.whl

# Download NLP models for PHI detection (cache in Docker layer, not at runtime)
RUN python -m spacy download en_core_web_lg && \
    python -c "from gliner import GLiNER; GLiNER.from_pretrained('urchade/gliner_multi_pii-v1')"

# Copy application source code
COPY apps/ios-screen-time-screenshot-processing/src/ ./src/
COPY apps/ios-screen-time-screenshot-processing/alembic/ ./alembic/
COPY apps/ios-screen-time-screenshot-processing/alembic.ini ./

# Create necessary directories
RUN mkdir -p /app/db /app/output /app/debug /app/uploads

# Copy and set up entrypoint script (before USER switch so we can chmod)
COPY apps/ios-screen-time-screenshot-processing/docker/backend/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create non-root user and set ownership
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command - entrypoint handles migrations automatically
CMD ["/entrypoint.sh"]
