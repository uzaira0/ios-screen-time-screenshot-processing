#!/bin/bash

echo "🚀 Starting Screenshot Annotation Platform - Frontend"
echo "====================================================="
echo ""

# Check if Bun is installed
if ! command -v bun &> /dev/null; then
    echo "❌ Error: Bun is not installed"
    echo "Please install Bun from https://bun.sh/"
    exit 1
fi

echo "✅ Bun found: $(bun --version)"
echo ""

# Navigate to frontend directory
cd frontend

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "📦 Installing frontend dependencies..."
    bun install
    echo ""
fi

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "⚙️  Creating .env file..."
    cp .env.example .env
    echo "✅ .env file created"
    echo ""
fi

echo "🌐 Starting React development server..."
echo "📍 Frontend: http://localhost:5173"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

bun run dev
