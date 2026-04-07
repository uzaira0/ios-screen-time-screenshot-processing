@echo off
echo.
echo 🚀 Starting Screenshot Annotation Platform - Backend
echo ==================================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Error: Python is not installed
    pause
    exit /b 1
)

echo ✅ Python found
python --version
echo.

REM Check if dependencies are installed
python -c "import fastapi" >nul 2>&1
if errorlevel 1 (
    echo 📦 Installing backend dependencies...
    pip install -e .[web]
    echo.
)

REM Check if database exists
if not exist "screenshot_annotation.db" (
    echo 🗄️  Initializing database...
    python -c "from src.screenshot_processor.web.database.database import init_db; init_db()"
    echo ✅ Database initialized
    echo.
)

echo 🌐 Starting FastAPI server...
echo 📍 API Documentation: http://localhost:8000/docs
echo 📍 WebSocket endpoint: ws://localhost:8000/api/ws
echo.
echo Press Ctrl+C to stop the server
echo.

uvicorn src.screenshot_processor.web.api.main:app --reload --host 0.0.0.0 --port 8000
