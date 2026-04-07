# PaddleOCR 3.x Server with GPU
FROM paddlepaddle/paddle:3.2.2-gpu-cuda12.6-cudnn9.5

RUN pip install --no-cache-dir \
    paddleocr \
    fastapi \
    uvicorn[standard] \
    python-multipart

WORKDIR /app
COPY api ./api

EXPOSE 8081

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
    CMD curl -f http://localhost:8081/health || exit 1

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8081"]
