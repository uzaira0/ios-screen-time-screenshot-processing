# Docker Testing Guide

This guide explains how to test the cross-platform refactoring implementation inside Docker containers to ensure all dependencies and configurations work correctly in a production-like environment.

## Overview

Testing inside Docker containers ensures:
- All system dependencies (Tesseract, libraries) are installed
- Python dependencies (PaddleOCR, etc.) work correctly
- Database migrations run successfully
- Environment variables are properly configured
- The application works in a Linux environment (production-like)

## Quick Start

### 1. Build and Test Everything

```bash
# Make script executable
chmod +x scripts/verify_docker.sh

# Run full verification
./scripts/verify_docker.sh
```

This will:
1. Build Docker images with all dependencies
2. Start containers
3. Run comprehensive test suite
4. Report results

### 2. Manual Step-by-Step Testing

```bash
# Build containers
docker-compose build backend

# Start containers
docker-compose up -d

# Wait for startup
sleep 10

# Run verification tests
docker-compose exec backend python scripts/test_phases_in_docker.py

# Check logs
docker-compose logs backend
```

## Docker Configuration Updates

### Changes Made for Complete Testing

#### 1. **pyproject.toml** - Added OCR Optional Dependencies

```toml
[project.optional-dependencies]
ocr = [
    "paddleocr>=2.7.0",
    "paddlepaddle>=2.6.0",
]
```

This allows installing PaddleOCR as an optional dependency:
```bash
pip install -e ".[ocr]"
```

#### 2. **Dockerfile.backend** - Enhanced Dependencies

**System packages added:**
- `libgomp1` - Required for PaddleOCR/Paddle
- `curl` - For healthchecks

**Python installation:**
```dockerfile
# Install web dependencies first, then OCR as optional
RUN pip install --no-cache-dir -e ".[web]" && \
    pip install --no-cache-dir -e ".[ocr]" || echo "PaddleOCR installation optional, continuing..."
```

Note: PaddleOCR installation is optional - if it fails, container continues with Tesseract only.

**Database migrations:**
```dockerfile
CMD alembic upgrade head && \
    uvicorn src.screenshot_processor.web.api.main:app --host 0.0.0.0 --port 8000
```

Now runs Alembic migrations automatically on startup.

#### 3. **docker-compose.yml** - Environment Variables

```yaml
environment:
  - SECRET_KEY=${SECRET_KEY:-your-secret-key-change-in-production}
  - PYTHONUNBUFFERED=1
```

- `SECRET_KEY` now reads from host environment or uses default
- `PYTHONUNBUFFERED=1` ensures logs appear immediately

## Running Specific Tests

### Test Phase 1 Only

```bash
docker-compose exec backend python -c "
from scripts.test_phases_in_docker import test_phase1
test_phase1()
"
```

### Test Phase 2 Only

```bash
docker-compose exec backend python -c "
from scripts.test_phases_in_docker import test_phase2
test_phase2()
"
```

### Test Phase 3 Only

```bash
docker-compose exec backend python -c "
from scripts.test_phases_in_docker import test_phase3
test_phase3()
"
```

### Check OCR Engines

```bash
docker-compose exec backend python -c "
from src.screenshot_processor.core.ocr_factory import OCREngineFactory

available = OCREngineFactory.get_available_engines()
print(f'Available engines: {available}')

for engine_type in available:
    engine = OCREngineFactory.create_engine(engine_type)
    print(f'{engine.get_engine_name()}:')
    print(f'  - Available: {engine.is_available()}')
"
```

### Test Database Migrations

```bash
# Check current migration
docker-compose exec backend alembic current

# Show migration history
docker-compose exec backend alembic history

# Run migrations manually
docker-compose exec backend alembic upgrade head
```

### Test Enum Serialization

```bash
docker-compose exec backend python -c "
from src.screenshot_processor.core.models import ImageType
import json

print('Python enum values:')
print(f'  BATTERY: {ImageType.BATTERY}')
print(f'  SCREEN_TIME: {ImageType.SCREEN_TIME}')

print('\nJSON serialization:')
data = {'type': ImageType.BATTERY}
print(json.dumps(data, default=str))
"
```

## Common Issues and Solutions

### Issue: PaddleOCR Not Installing

**Symptom:**
```
ERROR: Could not find a version that satisfies the requirement paddlepaddle
```

**Solution:**
This is expected in some environments. The Dockerfile is configured to continue without PaddleOCR:
```dockerfile
pip install --no-cache-dir -e ".[ocr]" || echo "PaddleOCR installation optional, continuing..."
```

Tesseract will be used as the fallback OCR engine.

### Issue: Database Migration Fails

**Symptom:**
```
alembic.util.exc.CommandError: Can't locate revision identified by 'xxxxx'
```

**Solution:**
Reset the database:
```bash
docker-compose down -v  # Remove volumes
docker-compose up -d    # Recreate with fresh database
```

### Issue: SECRET_KEY Validation Error

**Symptom:**
```
pydantic_core._pydantic_core.ValidationError: SECRET_KEY must be set to a secure value
```

**Solution:**
Set a proper SECRET_KEY:
```bash
# Generate a secure key
python -c "import secrets; print(secrets.token_hex(32))"

# Set it in environment
export SECRET_KEY="<generated-key>"

# Or create .env file
echo "SECRET_KEY=<generated-key>" > .env

# Restart containers
docker-compose restart backend
```

### Issue: Container Exits Immediately

**Symptom:**
```
backend exited with code 1
```

**Solution:**
Check logs for specific error:
```bash
docker-compose logs backend

# Common causes:
# 1. Missing SECRET_KEY - set environment variable
# 2. Migration error - check alembic setup
# 3. Import error - rebuild image after code changes
```

## Continuous Integration

### GitHub Actions Example

```yaml
name: Docker Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Generate SECRET_KEY
        run: echo "SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')" >> $GITHUB_ENV
      
      - name: Build containers
        run: docker-compose build backend
      
      - name: Start containers
        run: docker-compose up -d
      
      - name: Wait for startup
        run: sleep 15
      
      - name: Run tests
        run: docker-compose exec -T backend python scripts/test_phases_in_docker.py
      
      - name: Check logs
        if: failure()
        run: docker-compose logs backend
```

## Test Coverage Report

The `test_phases_in_docker.py` script tests:

### Phase 1: Critical Standardization (12 tests)
- ✅ ImageType enum values (battery, screen_time)
- ✅ StrEnum type usage
- ✅ JSON serialization
- ✅ Alembic configuration (alembic.ini, env.py)
- ✅ Migration versions (≥3 migrations)
- ✅ Database migration state
- ✅ Settings validation (short keys rejected)
- ✅ Settings validation (placeholder rejected)
- ✅ SECRET_KEY from environment
- ✅ .env.example exists

### Phase 2: OCR Abstraction (15 tests)
- ✅ IOCREngine protocol definition
- ✅ OCRResult dataclass (creation, immutability)
- ✅ TesseractOCREngine (protocol conformance, availability, name)
- ✅ PaddleOCREngine (protocol conformance, availability, name)
- ✅ OCREngineFactory (available engines, create specific, create best)
- ✅ Processor integration (ocr_engine attribute, initialization)

### Phase 3: Queue & Tagging (14 tests)
- ✅ ProcessingTag and ScreenshotQueue enums (StrEnum, count)
- ✅ ProcessingMetadata (creation, immutability, auto-queue, serialization)
- ✅ Tag validation (mutually exclusive tags)
- ✅ ProcessingPipeline existence
- ✅ QueueManager (creation, result tracking)
- ✅ Database schema (processing_metadata column)

**Total: 41 tests**

## Debugging

### Interactive Shell

```bash
# Open Python shell inside container
docker-compose exec backend python

# Or bash shell
docker-compose exec backend bash
```

### Check Installed Packages

```bash
docker-compose exec backend pip list | grep -E "paddle|tesseract|pydantic|alembic"
```

### Inspect Database

```bash
docker-compose exec backend python -c "
from src.screenshot_processor.web.database.models import Screenshot
from sqlalchemy import inspect

mapper = inspect(Screenshot)
print('Screenshot table columns:')
for col in mapper.columns:
    print(f'  - {col.key}: {col.type}')
"
```

### View Alembic Migrations

```bash
docker-compose exec backend ls -la alembic/versions/
```

## Production Deployment Checklist

Before deploying to production:

- [ ] Set strong SECRET_KEY via environment variable
- [ ] Review docker-compose.yml environment variables
- [ ] Ensure all migrations are committed to repository
- [ ] Test database backup/restore procedure
- [ ] Verify OCR engine availability (Tesseract minimum)
- [ ] Run full test suite: `docker-compose exec backend python scripts/test_phases_in_docker.py`
- [ ] Check healthcheck endpoint: `curl http://localhost:8002/health`
- [ ] Review logs for warnings: `docker-compose logs backend | grep -i warning`
- [ ] Test with real screenshot data
- [ ] Verify frontend can connect to backend
- [ ] Set up monitoring and alerting

## Next Steps

After verifying Phases 1-3 in Docker:

1. **Phase 4 Implementation** - Browser/WASM TypeScript interfaces
2. **Integration Tests** - Test with real screenshot data
3. **Performance Testing** - Benchmark OCR processing speed
4. **Load Testing** - Test concurrent users
5. **Security Audit** - Review authentication, secrets, CORS

## Additional Resources

- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [PaddleOCR Documentation](https://github.com/PaddlePaddle/PaddleOCR)
- [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
