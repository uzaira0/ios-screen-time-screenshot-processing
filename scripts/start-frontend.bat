@echo off
echo.
echo 🚀 Starting Screenshot Annotation Platform - Frontend
echo =====================================================
echo.

REM Check if Node.js is installed
node --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Error: Node.js is not installed
    echo Please install Node.js 18+ from https://nodejs.org/
    pause
    exit /b 1
)

echo ✅ Node.js found
node --version
echo ✅ npm found
call npm --version
echo.

REM Navigate to frontend directory
cd frontend

REM Check if node_modules exists
if not exist "node_modules" (
    echo 📦 Installing frontend dependencies...
    call npm install
    echo.
)

REM Check if .env exists
if not exist ".env" (
    echo ⚙️  Creating .env file...
    copy .env.example .env
    echo ✅ .env file created
    echo.
)

echo 🌐 Starting React development server...
echo 📍 Frontend: http://localhost:5173
echo.
echo Press Ctrl+C to stop the server
echo.

call npm run dev
