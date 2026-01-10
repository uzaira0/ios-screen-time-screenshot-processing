#!/bin/bash

echo "🚀 Starting Screenshot Annotation Platform - Backend"
echo "=================================================="
echo ""

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 is not installed"
    exit 1
fi

echo "✅ Python 3 found: $(python3 --version)"
echo ""

# Check if dependencies are installed
if ! python3 -c "import fastapi" 2> /dev/null; then
    echo "📦 Installing backend dependencies..."
    pip3 install -e ".[web]"
    echo ""
fi

# Check if database exists
if [ ! -f "screenshot_annotation.db" ]; then
    echo "🗄️  Initializing database..."
    python3 -c "from src.screenshot_processor.web.database.database import init_db; init_db()"
    echo "✅ Database initialized"
    echo ""
fi

echo "🌐 Starting FastAPI server..."
echo "📍 API Documentation: http://localhost:8000/docs"
echo "📍 WebSocket endpoint: ws://localhost:8000/api/ws"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

uvicorn src.screenshot_processor.web.api.main:app --reload --host 0.0.0.0 --port 8000
