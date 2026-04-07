#!/bin/bash
# Verify all phases in Docker container

set -e

echo "=================================="
echo "Building Docker containers..."
echo "=================================="
docker-compose build backend

echo ""
echo "=================================="
echo "Starting containers..."
echo "=================================="
docker-compose up -d backend

echo ""
echo "=================================="
echo "Waiting for backend to be ready..."
echo "=================================="
sleep 10

echo ""
echo "=================================="
echo "Running Phase Verification Tests"
echo "=================================="
docker-compose exec -T backend python scripts/test_phases_in_docker.py

echo ""
echo "=================================="
echo "Checking OCR engines availability"
echo "=================================="
docker-compose exec -T backend python -c "
from src.screenshot_processor.core.ocr_factory import OCREngineFactory
available = OCREngineFactory.get_available_engines()
print(f'Available OCR engines: {available}')
for engine_type in available:
    engine = OCREngineFactory.create_engine(engine_type)
    print(f'  - {engine.get_engine_name()}: available={engine.is_available()}')
"

echo ""
echo "=================================="
echo "Verification Complete!"
echo "=================================="
