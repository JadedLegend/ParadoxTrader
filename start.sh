#!/bin/bash
set -e

echo "=== Paradox Edge Trader v2 — Starting ==="

# Build the React frontend
echo "Building frontend..."
cd frontend
npm install --silent
npm run build
cd ..

echo "Frontend built."

# Start the FastAPI server
echo "Starting API server..."
exec uvicorn api.app:app --host 0.0.0.0 --port "${PORT:-8000}"
