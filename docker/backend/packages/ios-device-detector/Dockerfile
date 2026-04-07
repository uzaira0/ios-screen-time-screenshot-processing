FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Copy package files
COPY pyproject.toml .
COPY src/ src/

# Install package with web dependencies
RUN pip install --no-cache-dir -e ".[web,image]"

# Expose port
EXPOSE 8000

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

# Run the service
CMD ["uvicorn", "ios_device_detector.web.main:app", "--host", "0.0.0.0", "--port", "8000"]
