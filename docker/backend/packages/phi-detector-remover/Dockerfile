# Multi-stage build for phi-detector-remover service
FROM python:3.11-slim as base

# Install system dependencies
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-eng \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy workspace configuration
COPY pyproject.toml uv.lock ./
COPY packages/phi-detector-remover ./packages/phi-detector-remover
COPY packages/shared-research-ontology ./packages/shared-research-ontology

# Install dependencies
RUN uv sync --frozen --no-dev --package phi-detector-remover --extra web

# Production stage
FROM python:3.11-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-eng \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed dependencies and application
COPY --from=base /app/.venv /app/.venv
COPY --from=base /app/packages/phi-detector-remover /app/packages/phi-detector-remover

# Set environment
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/packages/phi-detector-remover/src:$PYTHONPATH"

# Expose port
EXPOSE 8000

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

# Run FastAPI service
CMD ["uvicorn", "phi_detector_remover.web.main:app", "--host", "0.0.0.0", "--port", "8000"]
